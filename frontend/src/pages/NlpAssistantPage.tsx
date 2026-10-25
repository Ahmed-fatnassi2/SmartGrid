import { AlertTriangle, Bot, Brain, Cpu, ExternalLink, Lightbulb, Microscope, SendHorizontal, Sparkles, Trash2, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ResultView } from "../components/sparql/ResultView";
import { SparqlBlock } from "../components/sparql/SparqlEditor";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, PageHeader } from "../components/ui/Card";
import { CopyButton } from "../components/ui/CopyButton";
import { BackendRequired, EmptyState } from "../components/ui/States";
import { useBackend } from "../context/BackendContext";
import { nlpService } from "../services/nlpService";
import type { NlpAnalysis, NlpResponse } from "../types";
import { errorMessage } from "../utils/errors";
import { formatNumber, humanize } from "../utils/format";

const EXAMPLES = [
  "Quelles centrales solaires produisent plus de 100 kW ?",
  "Quels bâtiments consomment plus de 300 kWh ?",
  "Quelles batteries ont une charge inférieure à 20 % ?",
  "Quelles sources alimentent l'université ?",
  "Combien de lignes de transport sont en bon état ?",
  "Quelles sources injectent dans la Ligne 01 ?",
  "Quelle est la centrale la plus puissante ?",
  "Quelle est la consommation moyenne des bâtiments ?",
  "Est-ce que la Ferme Solaire 01 alimente l'Ecole 01 ?",
];

const ENTITY_TONES: Record<string, "info" | "success" | "warning" | "neutral" | "danger"> = {
  classe: "info",
  individu: "success",
  propriete: "warning",
  comparateur: "neutral",
  valeur: "neutral",
  unite: "neutral",
  relation: "danger",
  statut: "success",
  agregation: "info",
  superlatif: "info",
};

const POS_LABELS: Record<string, string> = {
  NOUN: "nom", VERB: "verbe", ADJ: "adjectif", DET: "déterminant", ADP: "préposition", ADV: "adverbe",
  PRON: "pronom", PROPN: "nom propre", NUM: "nombre", AUX: "auxiliaire", PUNCT: "ponctuation", CCONJ: "conjonction",
  SCONJ: "subordonnant",
};

/** What the NLP pipeline computed: spaCy tokens, classifier scores, coherence rules. */
function AnalysisPanel({ a }: { a: NlpAnalysis }) {
  return (
    <details className="analysis">
      <summary>
        <Microscope size={14} />
        Analyse linguistique (spaCy · NLTK · scikit-learn)
      </summary>
      <div className="analysis-body">
        <h5>1. Tokens, lemmes et étiquettes (spaCy fr_core_news_sm)</h5>
        <div className="table-wrap">
          <table className="table table-compact">
            <thead>
              <tr>
                <th>Token</th>
                <th>Lemme</th>
                <th>Catégorie</th>
                <th>Dépendance</th>
                <th>Forme normalisée</th>
              </tr>
            </thead>
            <tbody>
              {a.tokens.map((t, i) => (
                <tr key={i}>
                  <td><strong>{t.text}</strong></td>
                  <td className="mono">{t.lemma}</td>
                  <td>
                    <span className="mono">{t.pos}</span> <small className="muted">{POS_LABELS[t.pos] ?? ""}</small>
                  </td>
                  <td className="mono muted">
                    {t.dep} → {t.head}
                  </td>
                  <td className="mono">{t.norm}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">Forme normalisée = lemme spaCy → racine (stemmer Snowball NLTK) → sans accents. Elle sert à reconnaître les termes de l'ontologie.</p>

        <h5>2. Entrée du classifieur d'intention</h5>
        <code className="uri-line">{a.delexicalised}</code>

        <h5>3. Probabilités du classifieur (TF-IDF + régression logistique)</h5>
        <ul className="score-list">
          {a.classifier.map((c) => (
            <li key={c.intent}>
              <span>{c.label}</span>
              <div className="score-track">
                <div className="score-fill" style={{ width: `${Math.max(2, c.score * 100)}%` }} />
              </div>
              <strong className="num">{(c.score * 100).toFixed(1)} %</strong>
            </li>
          ))}
        </ul>

        {a.rules.length > 0 && (
          <>
            <h5>4. Règles de cohérence appliquées</h5>
            <ul className="how-list">
              {a.rules.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </>
        )}
      </div>
    </details>
  );
}

interface Turn {
  id: number;
  question: string;
  pending: boolean;
  response?: NlpResponse;
  networkError?: string;
}

/** One-sentence French summary of the result, built from the returned rows. */
function answerSummary(r: NlpResponse): string | null {
  const res = r.result;
  if (!res) return null;
  if (res.query_type === "ask") return res.boolean ? "Oui." : "Non.";
  if (res.count === 0) return null;
  const countCol = res.columns.find((c) => /nombre|count|total/i.test(c));
  if (res.count === 1 && countCol) return `Résultat : ${res.rows[0][countCol]?.value ?? "—"}.`;
  const nameCol = res.columns.find((c) => /^nom/i.test(c)) ?? res.columns[0];
  const names = [...new Set(res.rows.map((row) => row[nameCol]?.short).filter(Boolean))] as string[];
  const shown = names.slice(0, 6).join(", ");
  return `${res.count} résultat${res.count > 1 ? "s" : ""} : ${shown}${names.length > 6 ? "…" : ""}.`;
}

function AnswerCard({ r, onOpenConsole }: { r: NlpResponse; onOpenConsole: (q: string) => void }) {
  const summary = answerSummary(r);
  return (
    <div className="answer">
      <div className="answer-meta">
        <Badge tone="info">
          <Cpu size={12} />
          spaCy · NLTK · scikit-learn
        </Badge>
        {r.intent && (
          <Badge tone="success">
            <Brain size={12} />
            Intention : {r.intent_label ?? r.intent}
            {r.analysis?.classifier[0] && r.analysis.classifier[0].intent === r.intent && (
              <> ({(r.analysis.classifier[0].score * 100).toFixed(0)} %)</>
            )}
          </Badge>
        )}
        {r.duration_ms !== undefined && <span className="muted">{formatNumber(r.duration_ms)} ms</span>}
      </div>

      {r.warnings.map((w, i) => (
        <div key={i} className="alert alert-warning">
          <AlertTriangle size={16} />
          <span>{w}</span>
        </div>
      ))}

      {summary && <p className="answer-summary">{summary}</p>}
      {r.explanation && <p className="muted">{r.explanation}</p>}

      <div className="answer-section">
        <h4>Entités extraites</h4>
        {r.entities.length === 0 ? (
          <span className="muted">Aucune entité reconnue.</span>
        ) : (
          <div className="chips">
            {r.entities.map((e, i) => (
              <span key={i} className={`entity-chip badge badge-${ENTITY_TONES[e.type] ?? "neutral"}`} title={`« ${e.text} »`}>
                <small>{e.type}</small>
                <strong className="mono">{e.type === "classe" ? humanize(e.value) : e.value}</strong>
              </span>
            ))}
          </div>
        )}
      </div>

      {r.analysis && <AnalysisPanel a={r.analysis} />}

      {r.sparql && (
        <div className="answer-section">
          <div className="row space-between">
            <h4>Requête SPARQL générée</h4>
            <div className="row gap-sm">
              <CopyButton text={r.sparql} label="Copier la requête" />
              <Button variant="ghost" size="sm" icon={<ExternalLink size={14} />} onClick={() => onOpenConsole(r.sparql!)}>
                Ouvrir dans la console
              </Button>
            </div>
          </div>
          <SparqlBlock query={r.sparql} />
        </div>
      )}

      <div className="answer-section">
        <h4>Résultats</h4>
        {r.error ? (
          <div className="alert alert-danger">
            <AlertTriangle size={16} />
            <span>{r.error}</span>
          </div>
        ) : r.result ? (
          r.result.count === 0 && r.result.query_type === "select" ? (
            <EmptyState
              title="Aucun résultat dans l'ontologie"
              message="La requête est valide, mais aucun individu du graphe ne correspond. Essayez un autre seuil ou une autre classe."
            />
          ) : (
            <ResultView result={r.result} />
          )
        ) : (
          <span className="muted">Aucune requête exécutée pour cette question.</span>
        )}
      </div>
    </div>
  );
}

export default function NlpAssistantPage() {
  const { demo } = useBackend();
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const endRef = useRef<HTMLDivElement>(null);
  const busy = turns.some((t) => t.pending);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const ask = async (q: string) => {
    const text = q.trim();
    if (!text || busy) return;
    const id = Date.now();
    setTurns((t) => [...t, { id, question: text, pending: true }]);
    setQuestion("");
    try {
      const response = await nlpService.ask(text);
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, pending: false, response } : x)));
    } catch (err) {
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, pending: false, networkError: errorMessage(err) } : x)));
    }
  };

  const openConsole = (q: string) => {
    try {
      window.localStorage.setItem("sparql.current", JSON.stringify(q));
    } catch {
      /* ignore */
    }
    navigate("/sparql");
  };

  if (demo) {
    return (
      <div className="page">
        <PageHeader title="Assistant NLP" icon={<Bot size={22} />} description="Posez vos questions en français sur le réseau." />
        <BackendRequired feature="L'assistant NLP" />
      </div>
    );
  }

  return (
    <div className="page">
      <PageHeader
        title="Assistant NLP"
        icon={<Bot size={22} />}
        description="Posez une question en français : l'assistant détecte l'intention et les entités, génère une requête SPARQL et l'exécute sur l'ontologie."
        actions={
          turns.length > 0 && (
            <Button variant="secondary" icon={<Trash2 size={16} />} onClick={() => setTurns([])} disabled={busy}>
              Effacer la conversation
            </Button>
          )
        }
      />

      <div className="assistant-layout">
        <Card className="chat-card" padded={false}>
          <div className="chat-scroll">
            {turns.length === 0 ? (
              <div className="chat-empty">
                <div className="chat-empty-icon">
                  <Sparkles size={26} />
                </div>
                <h3>Interrogez l'ontologie en langage naturel</h3>
                <p className="muted">Choisissez un exemple ou écrivez votre propre question.</p>
                <div className="example-chips">
                  {EXAMPLES.slice(0, 4).map((ex) => (
                    <button key={ex} className="example-chip" onClick={() => ask(ex)}>
                      « {ex} »
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              turns.map((t) => (
                <div key={t.id} className="turn">
                  <div className="bubble bubble-user">
                    <User size={16} />
                    <span>{t.question}</span>
                  </div>
                  <div className="bubble bubble-bot">
                    <div className="bot-avatar">
                      <Bot size={16} />
                    </div>
                    {t.pending ? (
                      <div className="thinking">
                        <span />
                        <span />
                        <span />
                        <em className="muted">Analyse de la question et génération de la requête…</em>
                      </div>
                    ) : t.networkError ? (
                      <div className="alert alert-danger">
                        <AlertTriangle size={16} />
                        <span>{t.networkError}</span>
                        <Button variant="ghost" size="sm" onClick={() => ask(t.question)}>
                          Réessayer
                        </Button>
                      </div>
                    ) : (
                      t.response && <AnswerCard r={t.response} onOpenConsole={openConsole} />
                    )}
                  </div>
                </div>
              ))
            )}
            <div ref={endRef} />
          </div>
          <form
            className="chat-input"
            onSubmit={(e) => {
              e.preventDefault();
              void ask(question);
            }}
          >
            <input
              className="input"
              value={question}
              maxLength={500}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ex. Quelles centrales éoliennes ont une puissance supérieure à 500 kW ?"
              aria-label="Votre question"
              disabled={busy}
            />
            <Button type="submit" icon={<SendHorizontal size={16} />} loading={busy} disabled={!question.trim()}>
              Envoyer
            </Button>
          </form>
        </Card>

        <div className="stack">
          <Card title="Exemples de questions">
            <ul className="example-list compact">
              {EXAMPLES.map((ex) => (
                <li key={ex}>
                  <button onClick={() => ask(ex)} disabled={busy}>
                    <Lightbulb size={14} />
                    <span>{ex}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Fonctionnement">
            <ol className="how-list">
              <li>La question est envoyée au backend FastAPI.</li>
              <li><strong>spaCy</strong> découpe la question (tokens, lemmes, catégories, dépendances) ; <strong>NLTK</strong> réduit chaque mot à sa racine.</li>
              <li>Des <em>PhraseMatchers</em> spaCy reconnaissent les classes, individus et propriétés, générés depuis le fichier OWL ; les nombres, unités et comparateurs sont extraits.</li>
              <li>Un classifieur <strong>scikit-learn</strong> (TF-IDF + régression logistique) prédit l'intention ; la requête SPARQL est construite à partir de modèles.</li>
              <li>La requête est vérifiée (lecture seule : SELECT ou ASK uniquement).</li>
              <li>RDFLib l'exécute sur le graphe : les résultats proviennent toujours de l'ontologie.</li>
            </ol>
          </Card>
        </div>
      </div>
    </div>
  );
}
