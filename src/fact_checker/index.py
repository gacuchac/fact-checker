"""The abstracts database built from the corpus: the docs table and the FTS5 passage index."""

import json
import re
import sqlite3
from pathlib import Path

from pydantic import BaseModel

from fact_checker.corpus import Corpus, Doc

ABBREVIATION = re.compile(r"\b(e\.g|i\.e|vs|et al|etc|Fig|cf)\.$", re.IGNORECASE)
WINDOW = 2


class IndexStats(BaseModel):
    """How many docs and passages an index holds."""

    docs: int
    passages: int


def sentences(text: str) -> list[str]:
    """Split text into sentences, keeping common abbreviations inside their sentence."""
    out: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+(?=[A-Z(\[0-9])", text):
        if out and ABBREVIATION.search(out[-1]):
            out[-1] += " " + part
        else:
            out.append(part)
    return out


def passages(doc: Doc) -> list[tuple[str, str, str, str]]:
    """Return (passage_id, doc_id, title, text) rows: the metadata passage, then 2-sentence windows with stride 1."""
    parts = sentences(doc.abstract)
    meta = f"{doc.title}. Authors: {', '.join(doc.authors)}. Published {doc.published[:10]}."
    rows = [(f"{doc.doc_id}#meta", doc.doc_id, doc.title, meta)]
    for i in range(max(1, len(parts) - WINDOW + 1)):
        text = f"{doc.title}. " + " ".join(parts[i : i + WINDOW])
        rows.append((f"{doc.doc_id}#{i}", doc.doc_id, doc.title, text))
    return rows


def build_index(corpus: Corpus, db: Path) -> IndexStats:
    """Build the docs table and the FTS5 passage index at db from the corpus.

    Replaces only the docs and passages tables; any other table in db (the app's runs and events) is kept.
    """
    db.parent.mkdir(parents=True, exist_ok=True)
    rows = [row for doc in corpus.docs for row in passages(doc)]
    con = sqlite3.connect(db)
    try:
        con.execute("DROP TABLE IF EXISTS docs")
        con.execute("DROP TABLE IF EXISTS passages")
        con.execute(
            "CREATE TABLE docs (doc_id TEXT PRIMARY KEY, base_id TEXT, title TEXT, authors TEXT, "
            "published TEXT, abstract TEXT)"
        )
        con.executemany(
            "INSERT INTO docs VALUES (?, ?, ?, ?, ?, ?)",
            [
                (d.doc_id, d.base_id, d.title, json.dumps(d.authors), d.published, d.abstract)
                for d in corpus.docs
            ],
        )
        con.execute(
            "CREATE VIRTUAL TABLE passages USING fts5("
            "passage_id UNINDEXED, doc_id UNINDEXED, title UNINDEXED, text, tokenize='porter unicode61')"
        )
        con.executemany("INSERT INTO passages VALUES (?, ?, ?, ?)", rows)
        con.commit()
    finally:
        con.close()
    return IndexStats(docs=len(corpus.docs), passages=len(rows))
