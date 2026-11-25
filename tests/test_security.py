"""OWASP LLM Top 10 security cases (S06, S08, S13-S16) against the API with fake models."""

import pytest
from fastapi.testclient import TestClient
from pipeline_helpers import COMMITTED

from fact_checker.api.app import Clients, create_app
from fact_checker.corpus import load_corpus
from fact_checker.index import build_index
from fact_checker.llm.base import LLMError
from fact_checker.llm.config import Settings
from fact_checker.llm.fake import FakeClient
from fact_checker.retrieve import retrieve
from fact_checker.services.schemas import (
    DecomposedStatement,
    DecomposeOutput,
    FalsifiabilityOutput,
)
from fact_checker.store import list_spans

CODE = "sesame"
HEADERS = {"X-Access-Code": CODE}
CLAIM = "LongAlign improves long context tasks"


@pytest.fixture(scope="module")
def corpus_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "f.sqlite"
    build_index(load_corpus(COMMITTED), path)
    return path


@pytest.fixture
def db(corpus_db, tmp_path):
    path = tmp_path / "f.sqlite"
    path.write_bytes(corpus_db.read_bytes())
    return path


def decompose_output(claim=CLAIM):
    statement = DecomposedStatement(
        text=CLAIM, kind="explicit", load_bearing=True, implied_by=claim, query="LongAlign long context"
    )
    return DecomposeOutput(statements=[statement])


def make_app(db, decompose=(), check=(), verify=(), review=(), **fields):
    clients = Clients(
        FakeClient(list(decompose)), FakeClient(list(check)), FakeClient(list(verify)), FakeClient(list(review))
    )
    cfg = Settings(decompose_model="opus", verify_model="sonnet", review_model="sol", access_code=CODE, **fields)
    return create_app(cfg, db, lambda _settings: clients), clients


HOSTILE = ["\" OR passages MATCH '*'; DROP TABLE docs; --", "NEAR(lost middle) *"]


def test_s08_hostile_fts_text_is_searched_safely(db):
    app, _ = make_app(db, decompose=[decompose_output(h) for h in HOSTILE])
    with TestClient(app) as client:
        codes = [client.post("/api/claims", json={"claim": h}, headers=HEADERS).status_code for h in HOSTILE]
        for text in HOSTILE:
            retrieve(db, text)
        assert client.get("/api/health").json()["docs"] == 48
    assert codes == [201, 201]


def test_s16a_no_data_route_answers_without_the_code(db):
    app, _ = make_app(db, decompose=[decompose_output()])
    with TestClient(app) as client:
        run_id = client.post("/api/claims", json={"claim": CLAIM}, headers=HEADERS).json()["run_id"]
        paths = [
            "/api/runs",
            f"/api/claims/{run_id}",
            f"/api/runs/{run_id}/trace",
            "/api/docs",
            "/api/docs/2307.03172v3",
            "/API/runs",
            "/api/runs/",
            "/api/../api/runs",
            "/api%2Fruns",
            "/api/runs?limit=100000",
        ]
        variants = [
            {},
            {"X-Access-Code": ""},
            {"X-Access-Code": CODE.upper()},
            {"X-Access-Code": CODE + " "},
            {"x-access-code": "wrong"},
        ]
        leaks = []
        for path in paths:
            for headers in variants:
                response = client.get(path, headers=headers)
                if response.status_code == 200 and ("claim" in response.text or "abstract" in response.text):
                    leaks.append((path, headers))
    assert leaks == []


LEAKY = LLMError("OpenAI API call failed: Incorrect API key provided: sk-proj-****abcd")


def _everything_visible(client, extra=""):
    texts = [extra, client.get("/api/runs", headers=HEADERS).text]
    for run in client.get("/api/runs", headers=HEADERS).json():
        run_id = run["run_id"] if "run_id" in run else run["id"]
        texts.append(client.get(f"/api/claims/{run_id}", headers=HEADERS).text)
        texts.append(client.get(f"/api/runs/{run_id}/trace", headers=HEADERS).text)
    return "\n".join(texts)


def test_s06_decompose_error_shows_no_key_fragment(db):
    app, _ = make_app(db, decompose=[LEAKY])
    with TestClient(app) as client:
        response = client.post("/api/claims", json={"claim": CLAIM}, headers=HEADERS)
        seen = _everything_visible(client, response.text)
    assert response.status_code == 502
    assert "sk-proj-" not in seen and "****abcd" not in seen


def test_s06_verify_error_shows_no_key_fragment(db):
    app, _ = make_app(db, decompose=[decompose_output()], verify=[LEAKY])
    with TestClient(app) as client:
        run_id = client.post("/api/claims", json={"claim": CLAIM}, headers=HEADERS).json()["run_id"]
        client.post(f"/api/claims/{run_id}/confirm", json={"edits": []}, headers=HEADERS)
        client.post(f"/api/claims/{run_id}/verify", headers=HEADERS)
        run = client.get(f"/api/claims/{run_id}", headers=HEADERS).json()
        seen = _everything_visible(client)
    assert run["status"] == "failed"
    assert "sk-proj-" not in seen and "****abcd" not in seen


def _confirm(client, run_id, op, value):
    edit = {"op": op, "id": 0 if op == "edit" else None, "value": value}
    return client.post(f"/api/claims/{run_id}/confirm", json={"edits": [edit]}, headers=HEADERS)


def _edit_spans(db, run_id):
    return [s for s in list_spans(db, run_id) if s.kind == "user" and s.name == "edits"]


def test_s13a_long_statement_text_is_rejected_before_any_model_call(db):
    ok = FalsifiabilityOutput(falsifiable=True, reason="", query="LongAlign long context")
    app, clients = make_app(db, decompose=[decompose_output()], check=[ok])
    with TestClient(app) as client:
        run_id = client.post("/api/claims", json={"claim": CLAIM}, headers=HEADERS).json()["run_id"]
        too_long_edit = _confirm(client, run_id, "edit", "x" * 501)
        huge_add = _confirm(client, run_id, "add", "y" * 200_000)
        status = client.get(f"/api/claims/{run_id}", headers=HEADERS).json()["status"]
        spans_after_refusals = _edit_spans(db, run_id)
        calls_after_refusals = len(clients.check.calls)
        exact = _confirm(client, run_id, "edit", "z" * 500)
    assert too_long_edit.status_code == 422 and isinstance(too_long_edit.json()["detail"], str)
    assert huge_add.status_code == 422 and isinstance(huge_add.json()["detail"], str)
    assert "500" in too_long_edit.json()["detail"]
    assert calls_after_refusals == 0 and status == "proposed" and spans_after_refusals == []
    assert exact.status_code == 200


def test_s13b_a_run_gets_at_most_3_confirm_rounds(db):
    no = FalsifiabilityOutput(falsifiable=False, reason="hedge", query="")
    app, clients = make_app(db, decompose=[decompose_output()], check=[no] * 5)
    with TestClient(app) as client:
        run_id = client.post("/api/claims", json={"claim": CLAIM}, headers=HEADERS).json()["run_id"]
        codes = [_confirm(client, run_id, "add", "It is probably good.").status_code for _ in range(5)]
    assert codes == [422, 422, 422, 409, 409]
    assert len(clients.check.calls) == 3
