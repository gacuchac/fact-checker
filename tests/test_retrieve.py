import json
from pathlib import Path

import pytest
from fact_checker.cli import main
from fact_checker.contracts import RetrievalResult
from fact_checker.corpus import Corpus, Doc
from fact_checker.index import build_index
from fact_checker.retrieve import match_query, retrieve

COMMITTED = Path(__file__).parent.parent / "data" / "corpus.json"
QUERY = "relevant information in the middle of long contexts"


def doc(doc_id, title, abstract):
    return Doc(
        doc_id=doc_id,
        base_id=doc_id.split("v")[0],
        title=title,
        authors=["Ann One"],
        published="2023-07-06T00:00:00Z",
        updated="2023-07-06T00:00:00Z",
        abstract=abstract,
    )


BUSY = doc(
    "1111.00001v1",
    "Busy Paper",
    "The middle position matters a lot. Models fail in the middle of context. "
    "The middle of the input is ignored. Middle placement hurts recall. "
    "The middle is where accuracy drops.",
)
SECOND = doc(
    "2222.00002v1",
    "Second Paper",
    "Recall in the middle is mentioned once here. Other things are discussed too.",
)
THIRD = doc(
    "3333.00003v1",
    "Third Paper",
    "Graph neural networks are studied. Nothing relevant appears in this text.",
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "index.sqlite"
    c = Corpus(
        kept_ids=[BUSY.doc_id, SECOND.doc_id, THIRD.doc_id],
        dropped_ids=[],
        fetched_at="t",
        docs=[BUSY, SECOND, THIRD],
    )
    build_index(c, path)
    return path


def test_us4_match_query_quotes_tokens_and_drops_stopwords():
    assert match_query("The Middle of a long-context") == '"middle" OR "long" OR "context"'


def test_us4_match_query_dedupes_in_order():
    assert match_query("middle long middle") == '"middle" OR "long"'


def test_us5_match_query_empty_for_stopwords_only():
    assert match_query("the of and a") == ""


def test_us5_match_query_empty_for_empty_and_punctuation():
    assert match_query("") == ""
    assert match_query('"*(') == ""


def test_us4_per_doc_cap(db):
    r = retrieve(db, "middle", k=10, per_doc=2)
    ids = [h.doc_id for h in r.hits]
    assert ids.count(BUSY.doc_id) == 2
    assert SECOND.doc_id in ids


def test_us4_per_doc_default_is_2_and_k_default_is_5(db):
    r = retrieve(db, "middle")
    assert (r.k, r.per_doc) == (5, 2)
    assert [h.doc_id for h in r.hits].count(BUSY.doc_id) <= 2


def test_us4_per_doc_1(db):
    r = retrieve(db, "middle", k=10, per_doc=1)
    ids = [h.doc_id for h in r.hits]
    assert len(ids) == len(set(ids))


def test_us4_k_cap(db):
    r = retrieve(db, "middle", k=1)
    assert len(r.hits) == 1
    assert r.k == 1


def test_us4_result_echoes_query(db):
    assert retrieve(db, "middle recall").query == "middle recall"


def test_us4_hits_sorted_by_score_desc(db):
    scores = [h.score for h in retrieve(db, "middle recall", k=10).hits]
    assert len(scores) >= 2
    assert scores == sorted(scores, reverse=True)


def test_us4_hit_fields_come_from_the_passage(db):
    h = retrieve(db, "graph neural networks").hits[0]
    assert h.doc_id == THIRD.doc_id
    assert h.title == "Third Paper"
    assert h.passage_id.startswith("3333.00003v1#")
    assert "Graph neural networks" in h.text


def test_us4_same_input_same_result(db):
    a = retrieve(db, "middle recall", k=10)
    b = retrieve(db, "middle recall", k=10)
    assert a == b


@pytest.mark.parametrize("q", ['"middle" AND (NEAR* ^title: OR - {x}', '"', "*", "AND OR NOT", ""])
def test_us5_fts_syntax_chars_do_not_raise(db, q):
    assert isinstance(retrieve(db, q), RetrievalResult)


def test_us5_unrelated_query_returns_no_hits(db):
    assert retrieve(db, "photosynthesis in plants").hits == []


def test_us5_missing_db_raises_and_creates_no_file(tmp_path):
    missing = tmp_path / "nope.sqlite"
    with pytest.raises(FileNotFoundError):
        retrieve(missing, "middle")
    assert not missing.exists()


def test_us4_cli_json_is_deterministic_and_parses(db, capsys):
    argv = ["retrieve", "middle recall", "--json", "--db", str(db)]
    assert main(argv) == 0
    first = capsys.readouterr().out
    assert main(argv) == 0
    assert capsys.readouterr().out == first
    r = RetrievalResult.model_validate_json(first)
    assert r.hits


def test_us4_cli_k_flag(db, capsys):
    assert main(["retrieve", "middle", "--k", "1", "--json", "--db", str(db)]) == 0
    assert len(json.loads(capsys.readouterr().out)["hits"]) == 1


def test_us4_cli_plain_output_one_line_per_hit(db, capsys):
    assert main(["retrieve", "graph neural networks", "--db", str(db)]) == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert lines
    assert "3333.00003v1" in lines[0] and "Third Paper" in lines[0]


def test_us5_cli_no_hits_exit_0_with_empty_hits(db, capsys):
    assert main(["retrieve", "photosynthesis in plants", "--json", "--db", str(db)]) == 0
    assert RetrievalResult.model_validate_json(capsys.readouterr().out).hits == []


def test_us5_cli_syntax_chars_exit_0(db):
    assert main(["retrieve", '"(NEAR* ^x: OR -', "--json", "--db", str(db)]) == 0


def test_us4_cli_missing_index_exits_1_and_creates_no_file(tmp_path, capsys):
    missing = tmp_path / "nope.sqlite"
    assert main(["retrieve", "middle", "--db", str(missing)]) == 1
    assert not missing.exists()
    assert "index not found" in capsys.readouterr().err


@pytest.fixture
def full_db(tmp_path):
    from fact_checker.corpus import load_corpus

    path = tmp_path / "index.sqlite"
    build_index(load_corpus(COMMITTED), path)
    return path


@pytest.mark.integration
def test_us4_lost_in_the_middle_top1(full_db):
    hits = retrieve(full_db, QUERY).hits
    assert hits[0].doc_id == "2307.03172v3"
    assert len(hits) <= 5
    ids = [h.doc_id for h in hits]
    assert all(ids.count(i) <= 2 for i in ids)


@pytest.mark.integration
def test_us4_retrieve_cli_json_is_deterministic_on_full_corpus(full_db, capsys):
    argv = ["retrieve", QUERY, "--json", "--db", str(full_db)]
    assert main(argv) == 0
    first = capsys.readouterr().out
    assert main(argv) == 0
    assert capsys.readouterr().out == first
    assert RetrievalResult.model_validate_json(first).hits[0].doc_id == "2307.03172v3"


@pytest.mark.integration
def test_us5_photosynthesis_zero_hits_exit_0_on_full_corpus(full_db, capsys):
    assert main(["retrieve", "photosynthesis in plants", "--json", "--db", str(full_db)]) == 0
    assert RetrievalResult.model_validate_json(capsys.readouterr().out).hits == []
