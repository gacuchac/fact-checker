import pytest

from fact_checker.corpus import Corpus, Doc
from fact_checker.docs import DocSummary, get_doc, search_docs
from fact_checker.index import build_index


def doc(doc_id, title, abstract, published="2023-07-06T17:54:11Z"):
    return Doc(
        doc_id=doc_id,
        base_id=doc_id.split("v")[0],
        title=title,
        authors=["Ann One", "Bob Two"],
        published=published,
        updated=published,
        abstract=abstract,
    )


@pytest.fixture
def db(tmp_path):
    docs = [
        doc("1111.00001v1", "Alpha Paper", "Zebras graze widely. Zebras also run fast.", "2023-01-01T00:00:00Z"),
        doc("2222.00002v1", "Beta Paper", "Giraffes eat leaves. Zebras are mentioned once.", "2024-05-05T00:00:00Z"),
        doc("3333.00003v1", "Gamma Paper", "Whales swim deep. Whales sing songs.", "2022-03-03T00:00:00Z"),
    ]
    path = tmp_path / "factcheck.sqlite"
    build_index(Corpus(kept_ids=[d.doc_id for d in docs], dropped_ids=[], fetched_at="x", docs=docs), path)
    return path


def test_w1_get_doc_hit(db):
    found = get_doc(db, "2222.00002v1")
    assert found is not None
    assert found.title == "Beta Paper"
    assert found.base_id == "2222.00002"
    assert found.authors == ["Ann One", "Bob Two"]
    assert found.published == "2024-05-05T00:00:00Z"
    assert found.abstract == "Giraffes eat leaves. Zebras are mentioned once."


def test_w1_get_doc_miss_is_none(db):
    assert get_doc(db, "9999.99999v1") is None


def test_w1_search_docs_one_entry_per_doc_ranked_by_best_passage(db):
    got = search_docs(db, "zebras")
    assert [d.doc_id for d in got] == ["1111.00001v1", "2222.00002v1"]
    assert got[0] == DocSummary(
        doc_id="1111.00001v1", title="Alpha Paper", authors=["Ann One", "Bob Two"], published="2023-01-01T00:00:00Z"
    )


def test_w1_search_docs_limit(db):
    assert [d.doc_id for d in search_docs(db, "zebras", limit=1)] == ["1111.00001v1"]


def test_w1_search_docs_empty_query_lists_all_by_published_desc(db):
    assert [d.doc_id for d in search_docs(db, "")] == ["2222.00002v1", "1111.00001v1", "3333.00003v1"]


def test_w1_search_docs_stopword_only_query_lists_all(db):
    assert len(search_docs(db, "the of")) == 3


def test_w1_search_docs_empty_query_respects_limit(db):
    assert [d.doc_id for d in search_docs(db, "  ", limit=2)] == ["2222.00002v1", "1111.00001v1"]


@pytest.mark.parametrize("query", ['"', "zebras AND", "NEAR(", "a*b:c", "zebras) OR (", "'; DROP TABLE docs; --"])
def test_w1_search_docs_fts_syntax_characters_do_not_raise(db, query):
    assert isinstance(search_docs(db, query), list)


def test_w1_search_docs_no_match_is_empty(db):
    assert search_docs(db, "quantum") == []
