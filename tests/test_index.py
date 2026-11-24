import json
import sqlite3
from pathlib import Path

import pytest

from fact_checker.cli import main
from fact_checker.corpus import Corpus, Doc, load_corpus, save_corpus
from fact_checker.index import IndexStats, build_index, passages, sentences

COMMITTED = Path(__file__).parent.parent / "data" / "corpus.json"


def doc(doc_id="1111.00001v1", title="Alpha Title", abstract=None):
    return Doc(
        doc_id=doc_id,
        base_id=doc_id.split("v")[0],
        title=title,
        authors=["Ann One", "Bob Two"],
        published="2023-07-06T17:54:11Z",
        updated="2023-08-01T00:00:00Z",
        abstract=abstract or "First one. Second two. Third three. Fourth four.",
    )


def corpus(*docs):
    return Corpus(
        kept_ids=[d.doc_id for d in docs],
        dropped_ids=[],
        fetched_at="2026-01-01T00:00:00Z",
        docs=list(docs),
    )


def rows(db):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT passage_id, doc_id, title, text FROM passages ORDER BY rowid").fetchall()
    finally:
        con.close()


def test_us3_sentences_splits_on_sentence_boundaries():
    assert sentences("One is here. Two is there! Three? Yes.") == [
        "One is here.",
        "Two is there!",
        "Three?",
        "Yes.",
    ]


@pytest.mark.parametrize("abbr", ["e.g.", "i.e.", "vs.", "et al.", "etc.", "Fig.", "cf."])
def test_us3_sentences_keeps_abbreviations(abbr):
    text = f"We study models {abbr} Transformers in depth. Next comes more."
    assert sentences(text) == [
        f"We study models {abbr} Transformers in depth.",
        "Next comes more.",
    ]


def test_us3_passages_meta_first_then_2_sentence_windows():
    p = passages(doc())
    assert len(p) == 4
    meta, w0, w1, w2 = p
    assert meta == (
        "1111.00001v1#meta",
        "1111.00001v1",
        "Alpha Title",
        "Alpha Title. Authors: Ann One, Bob Two. Published 2023-07-06.",
    )
    assert w0 == (
        "1111.00001v1#0",
        "1111.00001v1",
        "Alpha Title",
        "Alpha Title. First one. Second two.",
    )
    assert w1[0] == "1111.00001v1#1"
    assert w1[3] == "Alpha Title. Second two. Third three."
    assert w2[3] == "Alpha Title. Third three. Fourth four."
    assert all(t[3].startswith("Alpha Title. ") for t in p)


def test_us3_passages_one_sentence_abstract_gives_one_window():
    p = passages(doc(abstract="Only one sentence here."))
    assert [t[0] for t in p] == ["1111.00001v1#meta", "1111.00001v1#0"]
    assert p[1][3] == "Alpha Title. Only one sentence here."


def test_us3_passages_two_sentence_abstract_gives_one_window():
    p = passages(doc(abstract="One here. Two there."))
    assert [t[0] for t in p] == ["1111.00001v1#meta", "1111.00001v1#0"]
    assert p[1][3] == "Alpha Title. One here. Two there."


def test_us3_build_index_stats_and_rows(tmp_path):
    d1 = doc()
    d2 = doc("2222.00002v3", "Beta Title", "Alone sentence here.")
    db = tmp_path / "sub" / "index.sqlite"
    stats = build_index(corpus(d1, d2), db)
    assert stats == IndexStats(docs=2, passages=6)
    assert rows(db) == [tuple(t) for t in passages(d1) + passages(d2)]


def test_us3_build_index_rebuild_does_not_duplicate(tmp_path):
    db = tmp_path / "index.sqlite"
    c = corpus(doc())
    build_index(c, db)
    stats = build_index(c, db)
    assert stats.passages == 4
    assert len(rows(db)) == 4


def test_us3_index_uses_porter_tokenizer(tmp_path):
    db = tmp_path / "index.sqlite"
    build_index(corpus(doc(abstract="A study of context. Another line.")), db)
    con = sqlite3.connect(db)
    try:
        hit = con.execute("SELECT passage_id FROM passages WHERE passages MATCH '\"contexts\"'").fetchall()
    finally:
        con.close()
    assert hit


def test_us3_index_cli_builds_index_and_reports(tmp_path, capsys):
    src, db = tmp_path / "corpus.json", tmp_path / "index.sqlite"
    save_corpus(corpus(doc()), src)
    assert main(["index", "--corpus", str(src), "--db", str(db)]) == 0
    assert "indexed 1 docs, 4 passages" in capsys.readouterr().out
    assert len(rows(db)) == 4


def test_us3_index_cli_missing_corpus_exits_1(tmp_path):
    db = tmp_path / "index.sqlite"
    assert main(["index", "--corpus", str(tmp_path / "none.json"), "--db", str(db)]) == 1


@pytest.mark.integration
def test_us3_full_index_has_one_meta_per_doc(tmp_path):
    db = tmp_path / "index.sqlite"
    stats = build_index(load_corpus(COMMITTED), db)
    assert stats.docs == 48
    assert sum(r[0].endswith("#meta") for r in rows(db)) == 48


@pytest.mark.integration
def test_us3_full_index_passage_count(tmp_path):
    stats = build_index(load_corpus(COMMITTED), tmp_path / "index.sqlite")
    assert stats.passages == 365


@pytest.mark.integration
def test_us3_index_cli_exit_0_on_committed_corpus(tmp_path):
    db = tmp_path / "index.sqlite"
    assert main(["index", "--corpus", str(COMMITTED), "--db", str(db)]) == 0
    assert db.exists()


def doc_rows(db):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT doc_id, base_id, title, authors, published, abstract FROM docs ORDER BY doc_id").fetchall()
    finally:
        con.close()


def test_w1_build_index_writes_docs_table(tmp_path):
    d1 = doc()
    d2 = doc("2222.00002v3", "Beta Title", "Alone sentence here.")
    db = tmp_path / "factcheck.sqlite"
    build_index(corpus(d1, d2), db)
    assert doc_rows(db) == [
        (d.doc_id, d.base_id, d.title, json.dumps(d.authors), d.published, d.abstract) for d in (d1, d2)
    ]


def test_w1_docs_doc_id_is_primary_key(tmp_path):
    db = tmp_path / "factcheck.sqlite"
    build_index(corpus(doc()), db)
    con = sqlite3.connect(db)
    try:
        pk = [r[1] for r in con.execute("PRAGMA table_info(docs)") if r[5]]
    finally:
        con.close()
    assert pk == ["doc_id"]


def test_w1_db_build_cli_same_as_index(tmp_path, capsys):
    src, db = tmp_path / "corpus.json", tmp_path / "factcheck.sqlite"
    save_corpus(corpus(doc()), src)
    assert main(["db", "build", "--corpus", str(src), "--db", str(db)]) == 0
    assert "indexed 1 docs, 4 passages" in capsys.readouterr().out
    assert len(doc_rows(db)) == 1


def test_w1_db_build_cli_missing_corpus_exits_1(tmp_path):
    assert main(["db", "build", "--corpus", str(tmp_path / "none.json"), "--db", str(tmp_path / "x.sqlite")]) == 1


def test_w1_default_db_is_factcheck_sqlite():
    from fact_checker.cli import DEFAULT_DB

    assert DEFAULT_DB.name == "factcheck.sqlite"


@pytest.mark.integration
def test_w1_full_docs_table_has_48_rows(tmp_path):
    db = tmp_path / "factcheck.sqlite"
    build_index(load_corpus(COMMITTED), db)
    assert len(doc_rows(db)) == 48
