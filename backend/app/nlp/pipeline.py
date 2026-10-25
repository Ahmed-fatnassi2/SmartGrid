"""French question -> intent + entities + SPARQL, with classic NLP libraries.

Pipeline (no LLM, no external API):
 1. spaCy (fr_core_news_sm): tokenisation, lemmatisation, POS tags, dependencies.
 2. Normalisation of every token: spaCy lemma -> NLTK Snowball French stem -> no accents.
 3. spaCy PhraseMatcher on those normalised forms: ontology classes, individuals,
    data properties and object properties (vocabulary generated from the OWL file
    + French synonyms in lexicon.py).
 4. Numbers (spaCy like_num), units, comparators, status words, aggregates.
 5. Intent: scikit-learn classifier (TF-IDF char + word n-grams, logistic regression)
    trained on intent_data.py; questions are "delexicalised" first (ontology words
    replaced by CLASSE, INDIVIDU, NOMBRE…) so the model learns the question shape.
 6. Coherence rules between the predicted intent and the extracted slots.
 7. SPARQL built from templates and slots, then executed by RDFLib (read only).
"""
from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass, field

import spacy
from nltk.stem.snowball import FrenchStemmer
from rdflib import OWL, RDF, RDFS, URIRef
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import FeatureUnion, Pipeline
from spacy.matcher import PhraseMatcher
from spacy.tokens import Doc, Span
from spacy.util import filter_spans

from ..rdf_utils import all_individuals, inverse_map, label_of, local_name, pick_main_type, individual_types
from ..store import SG, store
from . import lexicon as lx
from .intent_data import INTENT_LABELS, TRAINING_DATA

SPACY_MODEL = "fr_core_news_sm"
PREFIXES = (
    "PREFIX sg: <http://www.esprit.tn/ontologies/smartgrid#>\n"
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
    "PREFIX owl: <http://www.w3.org/2002/07/owl#>\n"
)
FAMILY_VAR = {
    "SourceProduction": "source",
    "Stockage": "stockage",
    "Batiment": "batiment",
    "LigneTransport": "ligne",
    "MobiliteElectrique": "mobilite",
    "SystemeIntelligent": "systeme",
}
AGG_NAMES = {"SUM": "total", "AVG": "moyenne", "MAX": "maximum", "MIN": "minimum"}

_stemmer = FrenchStemmer()


def fold(text: str) -> str:
    """Lowercase, accents removed, same length as the input (keeps char offsets)."""
    out = []
    for ch in text.lower():
        f = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
        out.append(f[:1] if f else ch)
    return "".join(out)


def normalise(token) -> str:
    """spaCy lemma -> Snowball stem -> no accents ("alimentent" -> "alimenter" -> "aliment")."""
    base = token.lemma_ or token.text
    return fold(_stemmer.stem(base.lower().strip("'’")))


# --------------------------------------------------------------- data types


@dataclass
class Mention:
    kind: str  # CLASS | IND | PROP | REL
    id: str
    text: str
    start: int  # token index
    end: int
    char: int


@dataclass
class NumberValue:
    value: float
    text: str
    token: int
    char: int
    unit: str | None = None
    comparator: str | None = None
    comparator_text: str | None = None
    prop: str | None = None


@dataclass
class Slots:
    target: Mention | None = None
    other: Mention | None = None
    relation: Mention | None = None
    properties: list[Mention] = field(default_factory=list)
    numbers: list[NumberValue] = field(default_factory=list)
    statuses: list[tuple[str, object, str]] = field(default_factory=list)
    aggregate: tuple[str, str] | None = None
    superlative: tuple[str, str] | None = None  # (DESC|ASC, text)


# ----------------------------------------------------------------- analyzer


class Analyzer:
    def __init__(self) -> None:
        self.nlp = spacy.load(SPACY_MODEL, exclude=["ner"])
        self.model_version = self.nlp.meta.get("version", "?")
        self.lexicon_matcher = PhraseMatcher(self.nlp.vocab, attr="NORM")
        self.individual_matcher = PhraseMatcher(self.nlp.vocab, attr="NORM")
        self._graph_signature: tuple | None = None
        self._lock = threading.Lock()
        with store.lock:
            self._build_schema_lexicon(store.graph)
            self._refresh_individuals()
        self.classifier, self.training_size, self.cv_accuracy = self._train_classifier()

    # ------------------------------------------------------------ lexicon

    def _pattern(self, phrase: str) -> Doc:
        doc = self.nlp(phrase)
        for t in doc:
            t.norm_ = normalise(t)
        return doc

    def _add(self, matcher: PhraseMatcher, key: str, phrases) -> None:
        docs = [self._pattern(p) for p in {p.strip() for p in phrases if p and p.strip()}]
        if docs:
            matcher.add(key, docs)

    def _build_schema_lexicon(self, g) -> None:
        classes = {local_name(c) for c in g.subjects(RDF.type, OWL.Class) if isinstance(c, URIRef)}
        for cid in classes:
            self._add(self.lexicon_matcher, f"CLASS|{cid}", [lx.split_camel(cid), *lx.CLASS_SYNONYMS.get(cid, [])])
        for p in g.subjects(RDF.type, OWL.DatatypeProperty):
            pid = local_name(p)
            if pid == "nom":
                continue
            self._add(self.lexicon_matcher, f"PROP|{pid}", [lx.split_camel(pid), *lx.DATA_PROPERTY_SYNONYMS.get(pid, [])])
        for p in g.subjects(RDF.type, OWL.ObjectProperty):
            pid = local_name(p)
            self._add(self.lexicon_matcher, f"REL|{pid}", [*lx.RELATION_SYNONYMS.get(pid, [])])
        # Extra adjectives used in superlatives
        self._add(self.lexicon_matcher, "PROP|longueur", ["longue", "longues"])
        self._add(self.lexicon_matcher, "PROP|emissionCO2", ["polluant", "polluante"])
        self._add(self.lexicon_matcher, "PROP|tauxCharge", ["chargée", "chargées"])

    def _refresh_individuals(self) -> None:
        """Individuals change with CRUD operations: rebuild their patterns when the graph changes."""
        g = store.graph
        signature = (id(g), len(g))
        if signature == self._graph_signature:
            return
        self.individual_matcher = PhraseMatcher(self.nlp.vocab, attr="NORM")
        for ind in all_individuals(g):
            iid = local_name(ind)
            self._add(self.individual_matcher, f"IND|{iid}", [label_of(g, ind), iid.replace("_", " ")])
        self._graph_signature = signature

    # --------------------------------------------------------- processing

    def parse(self, text: str) -> Doc:
        doc = self.nlp(text)
        for t in doc:
            t.norm_ = normalise(t)
        return doc

    def mentions(self, doc: Doc) -> list[Mention]:
        spans = []
        for matcher in (self.individual_matcher, self.lexicon_matcher):
            for match_id, start, end in matcher(doc):
                spans.append(Span(doc, start, end, label=self.nlp.vocab.strings[match_id]))
        # Longest match wins ("centrale solaire" beats "centrale", "Ferme Solaire 01" beats both)
        kept = sorted(filter_spans(spans), key=lambda s: s.start)
        out = []
        for s in kept:
            kind, _, ident = s.label_.partition("|")
            out.append(Mention(kind, ident, s.text, s.start, s.end, s.start_char))
        return out

    # ------------------------------------------------------ classification

    def delexicalise(self, doc: Doc, mentions: list[Mention]) -> str:
        labels: dict[int, str] = {}
        names = {"CLASS": "CLASSE", "IND": "INDIVIDU", "PROP": "PROPRIETE", "REL": "RELATION"}
        for m in mentions:
            for i in range(m.start, m.end):
                labels[i] = names[m.kind]
        words: list[str] = []
        for t in doc:
            if t.is_punct and t.text != "?":
                continue
            if t.i in labels:
                w = labels[t.i]
            elif t.like_num:
                w = "NOMBRE"
            elif fold(t.text) in lx.UNITS:
                w = "UNITE"
            else:
                w = fold(t.text)
            if not words or words[-1] != w or w not in names.values():
                words.append(w)
        return " ".join(words)

    def _train_classifier(self):
        texts, labels = [], []
        for intent, examples in TRAINING_DATA.items():
            for ex in examples:
                doc = self.parse(ex)
                texts.append(self.delexicalise(doc, self.mentions(doc)))
                labels.append(intent)
        model = Pipeline(
            [
                (
                    "features",
                    FeatureUnion(
                        [
                            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)),
                            ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), token_pattern=r"[\w']+")),
                        ]
                    ),
                ),
                ("clf", LogisticRegression(max_iter=3000, C=8.0)),
            ]
        )
        # 5-fold cross-validation, reported in /api/nlp/info
        folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        cv = float(cross_val_score(model, texts, labels, cv=folds).mean())
        model.fit(texts, labels)
        return model, len(texts), cv

    def classify(self, delex: str) -> list[tuple[str, float]]:
        probs = self.classifier.predict_proba([delex])[0]
        ranked = sorted(zip(self.classifier.classes_, probs), key=lambda x: -x[1])
        return [(str(k), float(p)) for k, p in ranked]


_analyzer: Analyzer | None = None
_init_lock = threading.Lock()


def get_analyzer() -> Analyzer:
    global _analyzer
    with _init_lock:
        if _analyzer is None:
            _analyzer = Analyzer()
        return _analyzer


# ------------------------------------------------------------ slot filling


def _ancestors(g, cls_id: str) -> list[str]:
    return [local_name(c) for c in g.transitive_objects(SG[cls_id], RDFS.subClassOf)]


def _class_of(g, m: Mention) -> str | None:
    if m.kind == "CLASS":
        return m.id
    if m.kind == "IND":
        t = pick_main_type(g, individual_types(g, SG[m.id]))
        return local_name(t) if t is not None else None
    return None


def _family(g, cls_id: str | None) -> str | None:
    """Top-level class of the hierarchy (SourceProduction, Stockage, Batiment…)."""
    if not cls_id:
        return None
    for c in _ancestors(g, cls_id):
        if not any(isinstance(p, URIRef) for p in g.objects(SG[c], RDFS.subClassOf)):
            return c
    return cls_id


def _domains(g, prop_id: str) -> list[str]:
    return [local_name(d) for d in g.objects(SG[prop_id], RDFS.domain)]


def _resolve_property(g, prop_id: str, cls_id: str | None) -> str:
    """'capacité' of a line is capaciteTransport, of a battery capacite."""
    if not cls_id:
        return prop_id
    ancestors = set(_ancestors(g, cls_id))
    candidates = lx.PROPERTY_ALTERNATIVES.get(prop_id, [prop_id])
    for c in candidates:
        doms = _domains(g, c)
        if not doms or ancestors & set(doms):
            return c
    return prop_id


def _numbers(doc: Doc, mentions: list[Mention], folded: str) -> list[NumberValue]:
    inside_names = {i for m in mentions if m.kind == "IND" for i in range(m.start, m.end)}
    nums: list[NumberValue] = []
    i = 0
    while i < len(doc):
        t = doc[i]
        if t.like_num and i not in inside_names:
            raw = t.text
            j = i + 1
            # "100 000" -> 100000
            while j < len(doc) and doc[j].like_num and len(doc[j].text) == 3 and doc[j].text.isdigit():
                raw += doc[j].text
                j += 1
            try:
                value = float(raw.replace(",", ".").replace(" ", "").replace(" ", ""))
            except ValueError:
                i += 1
                continue
            unit = None
            if j < len(doc) and fold(doc[j].text) in lx.UNITS:
                unit_name, mult = lx.UNITS[fold(doc[j].text)]
                unit, value = unit_name, value * mult
            nums.append(NumberValue(value, raw, i, t.idx, unit))
            i = j
        else:
            i += 1
    # comparators before each number
    found = []
    for pattern, op in lx.COMPARATORS + [(r"\bapres\b|\bdepuis\b", ">"), (r"\bavant\b", "<")]:
        for m in re.finditer(pattern, folded):
            found.append((m.start(), m.end(), op, m.group(0)))
    for n in nums:
        before = [c for c in found if c[1] <= n.char and n.char - c[1] <= 30]
        if before:
            c = max(before, key=lambda c: (c[1], c[1] - c[0]))
            n.comparator, n.comparator_text = c[2], c[3]
    # "entre 100 et 500"
    m = re.search(r"entre\s+(\S+)\s+(?:\S+\s+)?et\s+(\S+)", folded)
    if m and len(nums) >= 2:
        nums[0].comparator, nums[0].comparator_text = ">=", "entre"
        nums[1].comparator, nums[1].comparator_text = "<=", "et"
    return nums


def fill_slots(g, doc: Doc, mentions: list[Mention], question: str) -> Slots:
    folded = fold(question)
    slots = Slots()
    entities = [m for m in mentions if m.kind in ("CLASS", "IND")]
    relations = [m for m in mentions if m.kind == "REL"]
    slots.properties = [m for m in mentions if m.kind == "PROP"]
    slots.relation = relations[0] if relations else None

    if entities:
        slots.target = entities[0]
        rest = entities[1:]
        if slots.relation and slots.target.start > slots.relation.start:
            # "Qui alimente l'hôpital ?" : the only entity is after the verb -> it is the object;
            # the target is the class at the other end of the relation.
            rel = slots.relation.id
            obj = slots.target
            obj_cls = _class_of(g, obj)
            dom = _domains(g, rel)
            rng = [local_name(r) for r in g.objects(SG[rel], RDFS.range)]
            anc = set(_ancestors(g, obj_cls)) if obj_cls else set()
            other_end = dom if anc & set(rng) else rng
            if other_end:
                slots.other = obj
                slots.target = Mention("CLASS", other_end[0], "", -1, -1, -1)
                rest = []
        if rest and slots.other is None:
            slots.other = rest[0]

    target_cls = _class_of(g, slots.target) if slots.target else None
    if target_cls is None and slots.properties:
        # "Quelle est la consommation totale ?" -> class from the property domain
        doms = _domains(g, _resolve_property(g, slots.properties[0].id, None))
        if doms:
            slots.target = Mention("CLASS", doms[0], "", -1, -1, -1)
            target_cls = doms[0]
    family = _family(g, target_cls)

    # numbers -> property (closest property word, else unit, else family default)
    slots.numbers = [n for n in _numbers(doc, mentions, folded) if n.comparator]
    for n in slots.numbers:
        if slots.properties:
            closest = min(slots.properties, key=lambda p: abs(p.start - n.token))
            n.prop = _resolve_property(g, closest.id, target_cls)
        elif n.unit and family and family in lx.UNIT_PROPERTY.get(n.unit, {}):
            n.prop = lx.UNIT_PROPERTY[n.unit][family]
        elif family:
            n.prop = lx.DEFAULT_PROPERTY.get(family)

    # status words
    for pattern, prop, value in lx.STATUS_PATTERNS:
        m = re.search(pattern, folded)
        if not m:
            continue
        if prop == "actif" and family == "LigneTransport" and value is False:
            prop, value = "etatLigne", "Hors service"
        doms = _domains(g, prop)
        if family and doms and family not in doms:
            continue
        if not any(s[0] == prop for s in slots.statuses):
            slots.statuses.append((prop, value, m.group(0)))

    for pattern, func in lx.AGGREGATES:
        m = re.search(pattern, folded)
        if m:
            slots.aggregate = (func, m.group(0))
            break
    m = re.search(r"\b(le|la|les|l')\s*(plus|moins)\b|\bmeilleure?\b", folded)
    if m:
        slots.superlative = ("ASC" if "moins" in m.group(0) else "DESC", m.group(0))
    return slots


# ----------------------------------------------------------- intent rules


def decide_intent(ranked: list[tuple[str, float]], slots: Slots) -> tuple[str, list[str]]:
    notes: list[str] = []
    intent = ranked[0][0]
    has_entity = slots.target is not None
    if not has_entity:
        if intent != "hors_sujet":
            notes.append("Aucune classe ni individu de l'ontologie reconnu → hors sujet.")
        return "hors_sujet", notes
    if intent == "hors_sujet":
        intent = next(k for k, _ in ranked if k != "hors_sujet")
        notes.append(f"Des termes de l'ontologie ont été reconnus → intention « {intent} » retenue.")
    if intent == "detail_individu" and slots.target.kind != "IND":
        intent = "lister_entites"
        notes.append("Aucun individu nommé → liste des entités.")
    if intent == "filtre_numerique" and not slots.numbers:
        intent = "relation" if slots.relation else "lister_entites"
        notes.append(f"Aucune valeur numérique comparée → « {intent} ».")
    if intent == "lister_entites" and slots.numbers:
        intent = "filtre_numerique"
        notes.append("Une valeur numérique comparée a été trouvée → filtre numérique.")
    if intent == "lister_entites" and slots.relation and slots.other:
        intent = "relation"
        notes.append("Une relation entre deux entités a été trouvée → relation.")
    if intent == "superlatif" and not slots.superlative:
        slots.superlative = ("DESC", "")
    if intent == "agregation" and not slots.aggregate:
        slots.aggregate = ("SUM", "")
        notes.append("Fonction d'agrégation non précisée → somme.")
    return intent, notes


# --------------------------------------------------------------- SPARQL


def build_sparql(g, intent: str, slots: Slots) -> tuple[str | None, str]:
    t = slots.target
    if t is None:
        return None, "Aucune ressource de l'ontologie n'a été reconnue."
    target_cls = _class_of(g, t)
    family = _family(g, target_cls)
    x = "?" + FAMILY_VAR.get(family or "", "element")
    nom_x = "?nom" + x[1:].capitalize()
    where: list[str] = []
    select: list[str] = [x, nom_x]
    explain: list[str] = []

    if intent == "detail_individu" and t.kind == "IND":
        q = PREFIXES + f"SELECT ?propriete ?valeur WHERE {{\n  sg:{t.id} ?propriete ?valeur .\n}}\nORDER BY ?propriete"
        return q, f"Toutes les propriétés de l'individu sg:{t.id}."

    if t.kind == "IND":
        where.append(f"VALUES {x} {{ sg:{t.id} }}")
        explain.append(f"l'individu sg:{t.id}")
    else:
        where.append(f"{x} a/rdfs:subClassOf* sg:{t.id} .")
        explain.append(f"les instances de sg:{t.id} (sous-classes incluses)")

    # numeric filters
    bound: set[str] = set()
    for n in slots.numbers:
        if not n.prop:
            continue
        var = "?" + n.prop
        if var not in bound:
            where.append(f"{x} sg:{n.prop} {var} .")
            bound.add(var)
            select.append(var)
        value = int(n.value) if n.value.is_integer() else n.value
        where.append(f"FILTER({var} {n.comparator} {value})")
        explain.append(f"sg:{n.prop} {n.comparator} {value}{' ' + n.unit if n.unit else ''}")

    # status filters
    for prop, value, _ in slots.statuses:
        var = "?" + prop
        where.append(f"{x} sg:{prop} {var} .")
        if isinstance(value, bool):
            where.append(f"FILTER({var} = {'true' if value else 'false'})")
        else:
            where.append(f'FILTER(LCASE(STR({var})) = "{str(value).lower()}")')
        select.append(var)
        explain.append(f"sg:{prop} = {value}")

    # relation
    if slots.relation:
        rel = slots.relation.id
        o = slots.other
        o_cls = _class_of(g, o) if o else None
        o_family = _family(g, o_cls) if o_cls else None
        y = "?" + FAMILY_VAR.get(o_family or "", "cible")
        if y == x:
            y = x + "2"
        nom_y = "?nom" + y[1:].capitalize()
        dom = set(_domains(g, rel))
        rng = {local_name(r) for r in g.objects(SG[rel], RDFS.range)}
        t_anc = set(_ancestors(g, target_cls)) if target_cls else set()
        symmetric = (SG[rel], RDF.type, OWL.SymmetricProperty) in g
        inverses = [local_name(q) for q in inverse_map(g).get(SG[rel], set())]
        if symmetric:
            where.append(f"{{ {x} sg:{rel} {y} }} UNION {{ {y} sg:{rel} {x} }}")
        elif t_anc & dom or not (t_anc & rng):
            alt = f" UNION {{ {y} sg:{inverses[0]} {x} }}" if inverses else ""
            where.append(f"{{ {x} sg:{rel} {y} }}{alt}")
        else:
            alt = f" UNION {{ {x} sg:{inverses[0]} {y} }}" if inverses else ""
            where.append(f"{{ {y} sg:{rel} {x} }}{alt}")
        if o and o.kind == "IND":
            where.append(f"VALUES {y} {{ sg:{o.id} }}")
            explain.append(f"reliés par sg:{rel} à sg:{o.id}")
        elif o:
            where.append(f"{y} a/rdfs:subClassOf* sg:{o.id} .")
            explain.append(f"reliés par sg:{rel} à une instance de sg:{o.id}")
        else:
            explain.append(f"avec leur relation sg:{rel}")
        select += [y, nom_y]
        where.append(f"OPTIONAL {{ {y} sg:nom {nom_y} }}")
    elif slots.other and intent == "verification":
        pass

    where.append(f"OPTIONAL {{ {x} sg:nom {nom_x} }}")

    def block(lines: list[str]) -> str:
        return "\n".join("  " + line for line in lines)

    if intent == "verification":
        core = [w for w in where if not w.startswith("OPTIONAL")]
        return PREFIXES + "ASK {\n" + block(core) + "\n}", "Vérifie s'il existe " + ", ".join(explain) + "."

    if intent == "comptage":
        q = PREFIXES + f"SELECT (COUNT(DISTINCT {x}) AS ?nombre) WHERE {{\n" + block(where) + "\n}"
        return q, "Compte " + ", ".join(explain) + "."

    if intent in ("agregation", "superlatif"):
        prop = None
        if slots.properties:
            prop = _resolve_property(g, slots.properties[0].id, target_cls)
        elif family:
            prop = lx.DEFAULT_PROPERTY.get(family)
        if not prop:
            return None, "Impossible de déterminer la propriété à agréger."
        var = "?" + prop
        if var not in bound:
            where.insert(1, f"{x} sg:{prop} {var} .")
        if intent == "agregation":
            func = slots.aggregate[0] if slots.aggregate else "SUM"
            core = [w for w in where if not w.startswith("OPTIONAL")]
            q = PREFIXES + f"SELECT ({func}({var}) AS ?{AGG_NAMES[func]}) (COUNT(DISTINCT {x}) AS ?nombre) WHERE {{\n" + block(core) + "\n}"
            return q, f"{AGG_NAMES[func].capitalize()} de sg:{prop} pour " + ", ".join(explain) + "."
        order = slots.superlative[0] if slots.superlative else "DESC"
        cols = " ".join(dict.fromkeys([x, nom_x, var] + [s for s in select if s not in (x, nom_x)]))
        q = PREFIXES + f"SELECT {cols} WHERE {{\n" + block(where) + f"\n}}\nORDER BY {order}({var})\nLIMIT 1"
        return q, f"{'Plus grande' if order == 'DESC' else 'Plus petite'} valeur de sg:{prop} parmi " + ", ".join(explain) + "."

    # lister_entites / filtre_numerique / relation / detail without individual
    if t.kind == "CLASS" and not slots.relation:
        where.insert(1, f"{x} a ?type . ?type rdfs:subClassOf* sg:{t.id} .")
        select.insert(2, "?type")
    cols = " ".join(dict.fromkeys(select))
    order_var = next((s for s in select if s.startswith("?") and s[1:] in {n.prop for n in slots.numbers}), nom_x)
    order = f"DESC({order_var})" if order_var != nom_x else nom_x
    q = PREFIXES + f"SELECT DISTINCT {cols} WHERE {{\n" + block(where) + f"\n}}\nORDER BY {order}"
    return q, "Recherche " + ", ".join(explain) + "."


# ------------------------------------------------------------------ public


ENTITY_TYPES = {"CLASS": "classe", "IND": "individu", "PROP": "propriete", "REL": "relation"}


def analyse(question: str) -> dict:
    analyzer = get_analyzer()
    with store.lock:
        g = store.graph
        with analyzer._lock:
            analyzer._refresh_individuals()
            doc = analyzer.parse(question)
            mentions = analyzer.mentions(doc)
            delex = analyzer.delexicalise(doc, mentions)
            ranked = analyzer.classify(delex)
        slots = fill_slots(g, doc, mentions, question)
        intent, notes = decide_intent(ranked, slots)
        sparql, explanation = (None, "La question ne porte pas sur l'ontologie Smart Grid.")
        if intent != "hors_sujet":
            sparql, explanation = build_sparql(g, intent, slots)

    target_cls = _class_of(g, slots.target) if slots.target else None
    entities = [
        {
            "type": ENTITY_TYPES[m.kind],
            "value": _resolve_property(g, m.id, target_cls) if m.kind == "PROP" else m.id,
            "text": m.text,
        }
        for m in mentions
    ]
    if slots.target and slots.target.start == -1:
        entities.insert(0, {"type": "classe", "value": slots.target.id, "text": "(déduit de la relation)"})
    for n in slots.numbers:
        entities.append({"type": "comparateur", "value": n.comparator, "text": n.comparator_text or ""})
        entities.append({"type": "valeur", "value": f"{n.value:g}", "text": n.text})
        if n.unit:
            entities.append({"type": "unite", "value": n.unit, "text": n.unit})
    for prop, value, text in slots.statuses:
        entities.append({"type": "statut", "value": f"{prop} = {value}", "text": text})
    if slots.aggregate and intent == "agregation":
        entities.append({"type": "agregation", "value": slots.aggregate[0], "text": slots.aggregate[1]})
    if slots.superlative and intent == "superlatif":
        entities.append({"type": "superlatif", "value": slots.superlative[0], "text": slots.superlative[1]})

    return {
        "intent": intent,
        "intent_label": INTENT_LABELS.get(intent, intent),
        "entities": entities,
        "sparql": sparql,
        "explanation": explanation,
        "analysis": {
            "tokens": [
                {"text": t.text, "lemma": t.lemma_, "pos": t.pos_, "dep": t.dep_, "head": t.head.text, "norm": t.norm_}
                for t in doc
            ],
            "delexicalised": delex,
            "classifier": [
                {"intent": k, "label": INTENT_LABELS.get(k, k), "score": round(p, 4)} for k, p in ranked[:4]
            ],
            "rules": notes,
        },
    }


def engine_info() -> dict:
    a = _analyzer
    return {
        "engine": "spacy",
        "spacy_model": f"{SPACY_MODEL} {a.model_version}" if a else SPACY_MODEL,
        "stemmer": "NLTK Snowball (français)",
        "classifier": "scikit-learn : TF-IDF (n-grammes) + régression logistique",
        "training_examples": a.training_size if a else sum(len(v) for v in TRAINING_DATA.values()),
        "cv_accuracy": round(a.cv_accuracy, 3) if a else None,
        "intents": list(INTENT_LABELS.keys()),
        "loaded": a is not None,
    }
