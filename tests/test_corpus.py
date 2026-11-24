import json
from pathlib import Path

import pytest

from fact_checker import corpus as corpus_mod
from fact_checker.cli import main
from fact_checker.corpus import (
    ARXIV_IDS,
    Corpus,
    build_corpus,
    keep_latest,
    load_corpus,
    parse_feed,
)

FEED = (Path(__file__).parent / "fixtures" / "arxiv_feed.xml").read_bytes()
COMMITTED = Path(__file__).parent.parent / "data" / "corpus.json"
LOST = "2307.03172v3"
OTHER = "2312.05934v3"


def test_us2_keep_latest_on_listed_ids():
    kept, dropped = keep_latest(ARXIV_IDS)
    assert len(kept) == 48
    assert dropped == ["2307.03172v1", "2403.01432v1"]


def test_us2_keep_latest_preserves_listed_order():
    kept, dropped = keep_latest(["b.1v1", "a.1v2", "b.1v2", "a.1v1"])
    assert kept == ["a.1v2", "b.1v2"]
    assert dropped == ["b.1v1", "a.1v1"]


def test_us2_parse_feed_fields():
    docs = {d.doc_id: d for d in parse_feed(FEED)}
    assert set(docs) == {LOST, OTHER}
    d = docs[LOST]
    assert d.base_id == "2307.03172"
    assert d.title == "Lost in the Middle: How Language Models Use Long Contexts"
    assert d.abstract == (
        "While recent language models have the ability to take long contexts as "
        "input, relatively little is known about how well they use longer context. "
        "We analyze performance on two tasks."
    )
    assert d.authors == ["Nelson F. Liu", "Kevin Lin", "John Hewitt"]
    assert d.published.startswith("2023-07-06")
    assert d.updated.startswith("2023-11-20")


def test_us2_build_corpus_keeps_latest_and_orders_by_kept():
    c = build_corpus(["2312.05934v3", "2307.03172v1", LOST], FEED, "2026-01-01T00:00:00Z")
    assert c.dropped_ids == ["2307.03172v1"]
    assert c.kept_ids == [OTHER, LOST]
    assert [d.doc_id for d in c.docs] == [OTHER, LOST]
    assert c.fetched_at == "2026-01-01T00:00:00Z"


def test_us2_build_corpus_raises_on_missing_entry():
    with pytest.raises(ValueError, match="9999.99999v1"):
        build_corpus([LOST, "9999.99999v1"], FEED, "t")


def test_us2_fetch_cli_writes_corpus_with_mocked_feed(monkeypatch, tmp_path):
    monkeypatch.setattr(corpus_mod, "fetch_feed", lambda kept, *a, **k: FEED)
    monkeypatch.setattr(corpus_mod, "ARXIV_IDS", (LOST, OTHER))
    out = tmp_path / "corpus.json"
    assert main(["fetch", "--corpus", str(out)]) == 0
    c = load_corpus(out)
    assert isinstance(c, Corpus)
    assert [d.doc_id for d in c.docs] == [LOST, OTHER]
    assert c.dropped_ids == []


def test_us2_fetch_cli_failure_exits_1_and_keeps_file(monkeypatch, tmp_path):
    def boom(kept, *a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(corpus_mod, "fetch_feed", boom)
    monkeypatch.setattr(corpus_mod, "ARXIV_IDS", (LOST, OTHER))
    out = tmp_path / "corpus.json"
    out.write_text("old content")
    assert main(["fetch", "--corpus", str(out)]) == 1
    assert out.read_text() == "old content"


def test_us2_fetch_cli_failure_creates_no_file(monkeypatch, tmp_path):
    def boom(kept, *a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(corpus_mod, "fetch_feed", boom)
    monkeypatch.setattr(corpus_mod, "ARXIV_IDS", (LOST, OTHER))
    out = tmp_path / "corpus.json"
    assert main(["fetch", "--corpus", str(out)]) == 1
    assert not out.exists()


def test_us2_committed_corpus_has_48_docs():
    c = load_corpus(COMMITTED)
    assert len(c.docs) == 48
    assert c.dropped_ids == ["2307.03172v1", "2403.01432v1"]
    assert [d.doc_id for d in c.docs] == c.kept_ids
    assert json.loads(COMMITTED.read_text())["kept_ids"] == c.kept_ids


class _Body:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self) -> bytes:
        return self.data


def test_us2_fetch_feed_malformed_xml_raises_runtime_error(monkeypatch):
    monkeypatch.setattr(corpus_mod.urllib.request, "urlopen", lambda *a, **k: _Body(b"<feed><entry>"))
    with pytest.raises(RuntimeError, match="fetch failed after 1 attempts"):
        corpus_mod.fetch_feed(["2307.03172v3"], attempts=1)


def test_us2_fetch_cli_malformed_feed_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(corpus_mod.urllib.request, "urlopen", lambda *a, **k: _Body(b"not xml"))
    monkeypatch.setattr(corpus_mod, "RETRY_PAUSE_SECONDS", 0)
    out = tmp_path / "corpus.json"
    assert main(["fetch", "--corpus", str(out)]) == 1
    assert not out.exists()
    assert "fetch failed" in capsys.readouterr().err
