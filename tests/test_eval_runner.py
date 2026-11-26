import json
import sqlite3

from fact_checker.eval_runner import run_claim_case
from pipeline_helpers import COMMITTED, review_output, v6_confirmed, v6_output
from test_api import decompose_output

from fact_checker.api.app import Clients
from fact_checker.llm.base import LLMError
from fact_checker.llm.config import Settings
from fact_checker.llm.fake import FakeClient
from fact_checker.services.schemas import FalsifiabilityOutput

ROOT = COMMITTED.parent.parent
CLAIM = v6_confirmed().claim


def cfg():
    return Settings(decompose_model="opus", verify_model="sonnet", review_model="sol")


def clients(decompose=(), check=(), verify=(), review=()):
    return Clients(FakeClient(list(decompose)), FakeClient(list(check)), FakeClient(list(verify)), FakeClient(list(review)))


def happy():
    return clients([decompose_output()], [], [v6_output()], [review_output()])


def case(**factcheck):
    return {"id": "X", "mode": "claim", "factcheck": {"claim": CLAIM, "edits": [], **factcheck}}


def test_run_claim_case_happy_path_returns_result_and_spans(tmp_path):
    outcome = run_claim_case(case(), ROOT, happy(), cfg(), ["k"], tmp_path)
    assert outcome.rejected is None and outcome.error is None
    assert isinstance(outcome.result, dict) and "final" in outcome.result
    names = {s["name"] for s in outcome.spans}
    assert {"decompose", "verify"} <= names
    assert "verify.md" in outcome.prompts and outcome.prompts["verify.md"].strip()
    assert outcome.secrets == ["k"]
    assert len(outcome.abstracts) == 48


def test_run_claim_case_appends_extra_docs_without_touching_the_corpus(tmp_path):
    doc = {
        "doc_id": "9999.00001v1",
        "base_id": "9999.00001",
        "title": "Planted",
        "authors": ["A"],
        "published": "2026-01-01",
        "updated": "2026-01-01",
        "abstract": "A planted   abstract\nabout nothing.",
    }
    before = COMMITTED.read_bytes()
    work = tmp_path / "work"
    work.mkdir()
    root = tmp_path / "root"
    (root / "data").mkdir(parents=True)
    (root / "data" / "corpus.json").write_bytes(before)
    (root / "extra.json").write_text(json.dumps({"docs": [doc]}))
    outcome = run_claim_case(case(extra_docs="extra.json"), root, happy(), cfg(), [], work)
    assert len(outcome.abstracts) == 49
    assert outcome.abstracts["9999.00001v1"] == "A planted abstract about nothing."
    with sqlite3.connect(work / "db.sqlite") as con:
        assert con.execute("SELECT COUNT(*) FROM docs").fetchone()[0] == 49
    assert (root / "data" / "corpus.json").read_bytes() == before
    assert COMMITTED.read_bytes() == before


def test_run_claim_case_rejected_at_confirm(tmp_path):
    check = FalsifiabilityOutput(falsifiable=False, reason="hedge", query="")
    edit = {"op": "add", "id": None, "value": "It is probably good."}
    outcome = run_claim_case(
        case(edits=[edit]), ROOT, clients([decompose_output()], [check]), cfg(), [], tmp_path
    )
    assert outcome.rejected
    assert outcome.result is None


def test_run_claim_case_decompose_error_is_recorded(tmp_path):
    failing = clients([LLMError("decompose boom")])
    outcome = run_claim_case(case(), ROOT, failing, cfg(), [], tmp_path)
    assert outcome.error and "decompose boom" in outcome.error
    assert outcome.result is None
