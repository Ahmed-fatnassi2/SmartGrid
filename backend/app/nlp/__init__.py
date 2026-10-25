"""Natural-language assistant: French question -> SPARQL -> results.

Built only with NLP libraries (spaCy, NLTK, scikit-learn); no LLM API is used.
"""
import re
import time

from .. import sparql_service
from .pipeline import analyse, engine_info, get_analyzer

__all__ = ["ask", "engine_info", "warm_up"]


def warm_up() -> None:
    """Load the spaCy model and train the intent classifier (called at startup)."""
    get_analyzer()


def _run_read_only(query: str) -> dict:
    qtype = sparql_service.analyze(query)
    if qtype not in ("select", "ask"):
        raise sparql_service.SparqlError(f"Requête générée de type {qtype.upper()} refusée : lecture seule.")
    code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', query)  # ignore string literals such as "Hors service"
    if re.search(r"\bSERVICE\b", code, re.IGNORECASE):
        raise sparql_service.SparqlError("Les requêtes fédérées (SERVICE) ne sont pas autorisées.")
    return sparql_service.execute(query, read_only=True)


def ask(question: str) -> dict:
    started = time.perf_counter()
    question = (question or "").strip()
    info = engine_info()
    response: dict = {
        "question": question,
        "engine": "spacy",
        "model": f"{info['spacy_model']} · NLTK · scikit-learn",
        "intent": None,
        "intent_label": None,
        "entities": [],
        "sparql": None,
        "explanation": None,
        "result": None,
        "error": None,
        "warnings": [],
        "analysis": None,
    }
    if not question:
        response["error"] = "La question est vide."
        return response

    out = analyse(question)
    response.update(out)
    response["model"] = f"{engine_info()['spacy_model']} · NLTK · scikit-learn"
    if out["intent"] == "hors_sujet":
        response["warnings"].append(
            "La question ne semble pas porter sur l'ontologie Smart Grid (aucune classe ni individu reconnu)."
        )
    elif out["sparql"]:
        try:
            response["result"] = _run_read_only(out["sparql"])
        except sparql_service.SparqlError as exc:
            response["error"] = str(exc)
    response["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return response
