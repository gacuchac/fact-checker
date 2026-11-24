"""Keyword retrieval of passages from the FTS5 index."""

import re
import sqlite3
from pathlib import Path

from fact_checker.contracts import Hit, RetrievalResult

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "for",
        "to",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "by",
        "with",
        "as",
        "at",
        "from",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "their",
        "they",
        "them",
        "than",
        "then",
        "which",
        "who",
        "whom",
        "what",
        "when",
        "where",
        "why",
        "how",
        "do",
        "does",
        "did",
        "can",
        "could",
        "may",
        "might",
        "will",
        "would",
        "should",
        "not",
        "no",
        "more",
        "most",
        "less",
        "very",
        "into",
        "over",
        "under",
        "about",
        "between",
        "both",
        "each",
        "other",
        "such",
        "only",
        "also",
        "has",
        "have",
        "had",
        "our",
        "we",
        "you",
    }
)
SEARCH_SQL = (
    "SELECT passage_id, doc_id, title, -bm25(passages), text FROM passages "
    "WHERE passages MATCH ? ORDER BY bm25(passages), rowid"
)


def match_query(text: str) -> str:
    """Turn free text into a safe FTS5 OR query of quoted tokens, or "" when no token is left."""
    tokens = [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS and len(t) > 1]
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(tokens))


def retrieve(db: Path, query: str, k: int = 5, per_doc: int = 2) -> RetrievalResult:
    """Return at most k hits for query, at most per_doc per paper, best score first and deterministic.

    Raises FileNotFoundError if db does not exist; never creates it.
    """
    if not db.exists():
        raise FileNotFoundError(db)
    match = match_query(query)
    hits: list[Hit] = []
    if match:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            rows = con.execute(SEARCH_SQL, (match,)).fetchall()
        finally:
            con.close()
        per_doc_count: dict[str, int] = {}
        for passage_id, doc_id, title, score, text in rows:
            if per_doc_count.get(doc_id, 0) >= per_doc:
                continue
            per_doc_count[doc_id] = per_doc_count.get(doc_id, 0) + 1
            hits.append(Hit(passage_id=passage_id, doc_id=doc_id, title=title, score=score, text=text))
            if len(hits) == k:
                break
    return RetrievalResult(query=query, k=k, per_doc=per_doc, hits=hits)
