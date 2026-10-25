# SmartGrid Semantic

Application web sémantique pour la gestion d'un réseau électrique intelligent (énergies renouvelables).
L'ontologie OWL `SmartGrid (2).owl` est chargée par un backend **FastAPI + RDFLib** et explorée par un frontend **React + TypeScript + Vite**.

```
web semantique/
├── SmartGrid (2).owl        # ontologie d'origine (jamais modifiée par l'API)
├── SmartGrid_new.owl        # nouvelle ontologie avec vos ajouts/suppressions (créée à la 1re modification)
├── backend/                 # FastAPI + RDFLib
│   ├── app/
│   │   ├── main.py          # routes /api/...
│   │   ├── store.py         # graphe RDF en mémoire + sauvegarde dans SmartGrid_new.owl
│   │   ├── entities.py      # CRUD piloté par l'ontologie (sources, stockage, bâtiments, lignes)
│   │   ├── ontology.py      # classes, propriétés, individus, graphe réseau
│   │   ├── sparql_service.py
│   │   ├── nlp/             # assistant NLP : spaCy + NLTK + scikit-learn (aucune API de LLM)
│   │   │   ├── pipeline.py      # analyse, extraction d'entités, classification, génération SPARQL
│   │   │   ├── lexicon.py       # vocabulaire français ↔ ontologie (synonymes, unités, comparateurs)
│   │   │   └── intent_data.py   # questions annotées pour entraîner le classifieur d'intention
│   │   └── dashboard.py
│   ├── requirements.txt
└── frontend/                # React + TypeScript + Vite
    └── src/{components,pages,services,types,hooks,utils,context}
```

## Installation

Prérequis : Python 3.10+ et Node.js 18+.

### Backend

```bash
cd backend
python -m venv .venv
# Windows : .venv\Scripts\activate    |    macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt   # installe aussi le modèle spaCy fr_core_news_sm
uvicorn app.main:app --reload --port 8000
```

Documentation interactive de l'API : http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
npm run build               # build de production dans dist/
```

L'URL de l'API se règle dans `frontend/.env` : `VITE_API_BASE_URL=http://localhost:8000/api`.

## Points importants

- **Persistance** : le fichier OWL n'est jamais modifié. Toute création, modification, suppression ou requête SPARQL UPDATE est enregistrée immédiatement dans **`SmartGrid_new.owl`** (RDF/XML, à côté du fichier d'origine, ouvrable dans Protégé). Au démarrage, le backend charge `SmartGrid_new.owl` s'il existe, sinon le fichier d'origine. *Paramètres → Réinitialiser* supprime `SmartGrid_new.owl` et recharge l'ontologie d'origine.
- **Assistant NLP (sans API de LLM)** : la conversion question → SPARQL repose uniquement sur des bibliothèques de TALN :
  1. **spaCy** (`fr_core_news_sm`) : tokenisation, lemmatisation, étiquetage morpho-syntaxique, analyse en dépendances ;
  2. **NLTK** (stemmer Snowball français) : chaque mot est ramené à sa racine (lemme → racine → sans accents), donc « centrales », « alimentent », « alimentés » sont reconnus ;
  3. **PhraseMatcher spaCy** : reconnaissance des classes, individus, propriétés et relations, à partir d'un vocabulaire généré depuis le fichier OWL et complété par des synonymes français (`lexicon.py`) ; extraction des nombres, unités (MW → kW…), comparateurs, statuts et agrégations ;
  4. **scikit-learn** : classifieur d'intention (TF-IDF n-grammes + régression logistique) entraîné sur 122 questions annotées, 9 intentions, ≈ 90 % de précision en validation croisée 5 plis ; la question est « délexicalisée » (CLASSE, INDIVIDU, NOMBRE…) avant classification ;
  5. **Génération SPARQL** par modèles (SELECT, COUNT, SUM/AVG/MAX/MIN, ORDER BY … LIMIT 1, ASK), vérification lecture seule, exécution par RDFLib.
  L'interface affiche toutes ces étapes (« Analyse linguistique »).
- **SPARQL** : les requêtes de modification sont refusées par l'API (HTTP 409) tant qu'elles ne sont pas confirmées dans l'interface.
- **Mode démo** : si le backend est injoignable, le frontend affiche un bandeau « Mode démo : données fictives », désactive les modifications et n'affiche ni ontologie, ni SPARQL, ni NLP (pas de données inventées).

## API

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/health`, `/api/info` | état du serveur, configuration |
| POST | `/api/system/reset` | recharger le fichier OWL d'origine |
| GET | `/api/dashboard/stats`, `/api/activity` | indicateurs, activité récente |
| GET/POST | `/api/{sources,storage,buildings,lines}` | liste (search, type, status, sort, order, page, page_size) / création |
| GET/PUT/DELETE | `/api/{entité}/{id}` | lecture / modification / suppression |
| GET | `/api/{entité}/types` | sous-classes OWL autorisées |
| GET | `/api/grid` | nœuds (individus) et arêtes (ObjectProperties) |
| GET | `/api/ontology/summary`, `/classes`, `/object-properties`, `/data-properties` | schéma OWL |
| GET | `/api/ontology/individuals[?class=]`, `/individuals/{id}` | individus |
| GET | `/api/ontology/export?format=turtle\|xml\|json-ld\|nt` | export du graphe |
| POST | `/api/sparql` `{query, allow_update}` | exécution SPARQL |
| POST | `/api/sparql/analyze` | type de requête (lecture / modification) |
| POST | `/api/nlp/ask` `{question}` | assistant en langage naturel |

## Limites connues (liées au contenu de l'ontologie)

- L'ontologie n'a pas de propriété de **localisation** pour les sources : seule l'adresse des bâtiments (`sg:adresse`) est affichée.
- Il n'y a pas de **séries temporelles** : les graphiques utilisent les valeurs de l'ontologie (`sg:puissance`, `sg:productionAnnuelle`, `sg:consommation`), pas un historique.
- Les unités ne sont pas déclarées dans l'OWL ; l'interface suppose kW (puissance, capacité de transport), kWh (capacité, consommation), km, kV et %.
- Aucun individu `Universite` n'existe dans l'OWL : la question « Quelles sources alimentent l'université ? » renvoie donc un résultat vide tant qu'une université n'est pas ajoutée.
