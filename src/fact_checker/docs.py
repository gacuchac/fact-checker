"""Read access to the abstracts database: one paper by id, and paper search over the FTS5 index."""

import json
import sqlite3
from pathlib import Path

from pydantic import BaseModel

from fact_checker.retrieve import match_query


class Doc(BaseModel):
    """One paper as stored in the docs table."""

    doc_id: str
    base_id: str
    title: str
    authors: list[str]
    published: str
    abstract: str


class DocSummary(BaseModel):
    """A paper in a search result list."""

    doc_id: str
    title: str
    authors: list[str]
    published: str


RANKED_SQL = "SELECT doc_id FROM passages WHERE passages MATCH ? ORDER BY bm25(passages), rowid"
ALL_SQL = "SELECT doc_id, title, authors, published FROM docs ORDER BY published DESC, doc_id LIMIT ?"


def _connect(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def get_doc(db: Path, doc_id: str) -> Doc | None:
    """Return the paper with doc_id from the docs table, or None if there is none.

    Raises FileNotFoundError if db does not exist; never creates it.
    """
    if not db.exists():
        raise FileNotFoundError(db)
    con = _connect(db)
    try:
        row = con.execute(
            "SELECT doc_id, base_id, title, authors, published, abstract FROM docs WHERE doc_id = ?", (doc_id,)
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return None
    return Doc(doc_id=row[0], base_id=row[1], title=row[2], authors=json.loads(row[3]), published=row[4], abstract=row[5])


def search_docs(db: Path, query: str, limit: int = 20) -> list[DocSummary]:
    """Return at most limit papers matching query, one per paper, ranked by the paper's best passage.

    The query is turned into a safe FTS5 query as in retrieve. A query with no usable token lists all
    papers, newest published first. Raises FileNotFoundError if db does not exist; never creates it.
    """
    if not db.exists():
        raise FileNotFoundError(db)
    match = match_query(query)
    con = _connect(db)
    try:
        if match:
            ranked = list(dict.fromkeys(r[0] for r in con.execute(RANKED_SQL, (match,))))[:limit]
            rows = [_summary_row(con, doc_id) for doc_id in ranked]
        else:
            rows = con.execute(ALL_SQL, (limit,)).fetchall()
    finally:
        con.close()
    return [DocSummary(doc_id=r[0], title=r[1], authors=json.loads(r[2]), published=r[3]) for r in rows]


def _summary_row(con: sqlite3.Connection, doc_id: str) -> tuple[str, str, str, str]:
    return con.execute("SELECT doc_id, title, authors, published FROM docs WHERE doc_id = ?", (doc_id,)).fetchone()
