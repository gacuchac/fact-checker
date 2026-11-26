import sqlite3
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pipeline_helpers import COMMITTED, review_output, v6_confirmed, v6_output

from fact_checker.api.app import Clients, create_app
from fact_checker.contracts import Edit
from fact_checker.corpus import load_corpus
from fact_checker.index import build_index
from fact_checker.llm.base import LLMError
from fact_checker.llm.config import Settings
from fact_checker.llm.fake import FakeClient
from fact_checker.services.schemas import DecomposedStatement, DecomposeOutput
from fact_checker.store import create_run, init_store, list_spans

CLAIM = v6_confirmed().claim
CODE = {"X-Access-Code": "sesame"}


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


def settings(**fields):
    return Settings(
        decompose_model="opus", verify_model="sonnet", review_model="sol", access_code="sesame", **fields
    )


def decompose_output():
    return DecomposeOutput(
        statements=[
            DecomposedStatement(
                text=s.text, kind="explicit", load_bearing=True, implied_by=s.implied_by, query=s.query
            )
            for s in v6_confirmed().statements
        ]
    )


def fake_clients(decompose=(), check=(), verify=(), review=()):
    clients = Clients(FakeClient(list(decompose)), FakeClient(list(check)), FakeClient(list(verify)), FakeClient(list(review)))
    return lambda _settings: clients


def make_client(db, cfg=None, clients=None, static_dir=None):
    app = create_app(cfg or settings(), db, clients or fake_clients(), static_dir)
    return TestClient(app)


def happy_clients():
    return fake_clients([decompose_output()], [], [v6_output()], [review_output()])


def propose(client):
    response = client.post("/api/claims", json={"claim": CLAIM}, headers=CODE)
    assert response.status_code == 201
    return response.json()


def test_health_needs_no_code_and_counts_docs(db):
    with make_client(db) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True and body["docs"] > 0


def test_auth_required_and_checked(db):
    with make_client(db) as client:
        missing = client.get("/api/runs")
        wrong = client.get("/api/runs", headers={"X-Access-Code": "nope"})
        right = client.get("/api/runs", headers=CODE)
    assert missing.status_code == 401 and missing.json() == {"detail": "access code required"}
    assert wrong.status_code == 401
    assert right.status_code == 200 and right.json() == []


def test_auth_is_off_without_a_configured_code(db):
    with make_client(db, Settings()) as client:
        assert client.get("/api/runs").status_code == 200


def test_full_flow_claim_confirm_verify(db):
    with make_client(db, clients=happy_clients()) as client:
        created = propose(client)
        run_id = created["run_id"]
        assert created["claim"] == CLAIM and len(created["proposed"]) == len(v6_confirmed().statements)
        assert client.get(f"/api/claims/{run_id}", headers=CODE).json()["status"] == "proposed"

        confirm = client.post(f"/api/claims/{run_id}/confirm", json={"edits": []}, headers=CODE)
        assert confirm.status_code == 200 and confirm.json()["confirmed"]["claim"] == CLAIM
        assert client.get(f"/api/claims/{run_id}", headers=CODE).json()["status"] == "confirmed"

        verify = client.post(f"/api/claims/{run_id}/verify", headers=CODE)
        assert verify.status_code == 202 and verify.json() == {"run_id": run_id, "status": "verifying"}

        run = client.get(f"/api/claims/{run_id}", headers=CODE).json()
        runs = client.get("/api/runs?limit=5", headers=CODE).json()
    assert run["status"] == "done" and run["error"] is None
    assert run["result"]["revised"] is False and run["result"]["final_message"].startswith("Claim:")
    assert run["confirmed"]["claim"] == CLAIM and run["proposed"]
    assert [r["id"] for r in runs] == [run_id] and runs[0]["status"] == "done"


def test_trace_spans_in_order(db):
    with make_client(db, clients=happy_clients()) as client:
        run_id = propose(client)["run_id"]
        client.post(f"/api/claims/{run_id}/confirm", json={"edits": []}, headers=CODE)
        client.post(f"/api/claims/{run_id}/verify", headers=CODE)
        trace = client.get(f"/api/runs/{run_id}/trace", headers=CODE).json()
    assert trace["run_id"] == run_id
    pairs = [(s["kind"], s["name"]) for s in trace["spans"]]
    assert [s["seq"] for s in trace["spans"]] == sorted(s["seq"] for s in trace["spans"])
    assert pairs[:4] == [("user", "claim"), ("llm", "decompose"), ("user", "edits"), ("user", "approval")]
    assert ("llm", "verify") in pairs and pairs[-1] == ("system", "final_message")
    approval = trace["spans"][3]
    assert approval["input"] == {"statement_ids": [s.id for s in v6_confirmed().statements]}


def test_trace_of_unknown_run_is_404(db):
    with make_client(db) as client:
        assert client.get("/api/runs/nope/trace", headers=CODE).status_code == 404
        assert client.get("/api/claims/nope", headers=CODE).status_code == 404


def test_confirm_twice_is_409(db):
    with make_client(db, clients=happy_clients()) as client:
        run_id = propose(client)["run_id"]
        url = f"/api/claims/{run_id}/confirm"
        assert client.post(url, json={"edits": []}, headers=CODE).status_code == 200
        again = client.post(url, json={"edits": []}, headers=CODE)
    assert again.status_code == 409 and "detail" in again.json()


def test_verify_before_confirm_is_409(db):
    with make_client(db, clients=happy_clients()) as client:
        run_id = propose(client)["run_id"]
        response = client.post(f"/api/claims/{run_id}/verify", headers=CODE)
    assert response.status_code == 409


def test_confirm_and_verify_unknown_run_are_404(db):
    with make_client(db) as client:
        assert client.post("/api/claims/nope/confirm", json={"edits": []}, headers=CODE).status_code == 404
        assert client.post("/api/claims/nope/verify", headers=CODE).status_code == 404


def test_confirm_with_unfalsifiable_statement_is_422_issues_and_stays_proposed(db):
    from fact_checker.services.schemas import FalsifiabilityOutput

    clients = fake_clients(
        [decompose_output()], [FalsifiabilityOutput(falsifiable=False, reason="hedge", query="")]
    )
    edit = Edit(op="add", id=None, value="It is probably good.").model_dump()
    with make_client(db, clients=clients) as client:
        run_id = propose(client)["run_id"]
        response = client.post(f"/api/claims/{run_id}/confirm", json={"edits": [edit]}, headers=CODE)
        status = client.get(f"/api/claims/{run_id}", headers=CODE).json()["status"]
    assert response.status_code == 422
    assert response.json() == {"issues": [{"statement_id": len(v6_confirmed().statements), "reason": "hedge"}]}
    assert status == "proposed"


def test_confirm_with_unknown_statement_id_is_422(db):
    edit = Edit(op="drop", id=99, value=None).model_dump()
    with make_client(db, clients=happy_clients()) as client:
        run_id = propose(client)["run_id"]
        response = client.post(f"/api/claims/{run_id}/confirm", json={"edits": [edit]}, headers=CODE)
    assert response.status_code == 422 and "detail" in response.json()


def test_claim_too_long_or_empty_is_422(db):
    with make_client(db) as client:
        long = client.post("/api/claims", json={"claim": "x" * 501}, headers=CODE)
        empty = client.post("/api/claims", json={"claim": ""}, headers=CODE)
        exact = client.post("/api/claims", json={"claim": "x" * 500}, headers=CODE)
    assert long.status_code == 422 and empty.status_code == 422
    assert exact.status_code == 502


def test_decompose_failure_is_502(db):
    clients = fake_clients([LLMError("api down")])
    with make_client(db, clients=clients) as client:
        response = client.post("/api/claims", json={"claim": CLAIM}, headers=CODE)
    assert response.status_code == 502 and "api down" in response.json()["detail"]


def test_verify_failure_shows_as_failed_claim(db):
    clients = fake_clients([decompose_output()], [], [LLMError("api down")])
    with make_client(db, clients=clients) as client:
        run_id = propose(client)["run_id"]
        client.post(f"/api/claims/{run_id}/confirm", json={"edits": []}, headers=CODE)
        client.post(f"/api/claims/{run_id}/verify", headers=CODE)
        run = client.get(f"/api/claims/{run_id}", headers=CODE).json()
    assert run["status"] == "failed" and "api down" in run["error"] and run["result"] is None


def test_daily_cap_blocks_new_claims(db):
    clients = fake_clients([decompose_output(), decompose_output()])
    with make_client(db, settings(daily_run_cap=1), clients) as client:
        first = client.post("/api/claims", json={"claim": CLAIM}, headers=CODE)
        second = client.post("/api/claims", json={"claim": CLAIM}, headers=CODE)
        runs = client.get("/api/runs", headers=CODE).json()
    assert first.status_code == 201
    assert second.status_code == 429 and "detail" in second.json()
    assert len(clients(None).decompose.calls) == 1
    assert len(runs) == 1


def test_daily_cap_counts_claims_that_were_never_verified(db):
    init_store(db)
    for _ in range(3):
        create_run(db, "only proposed")
    clients = happy_clients()
    with make_client(db, settings(daily_run_cap=3), clients) as client:
        response = client.post("/api/claims", json={"claim": CLAIM}, headers=CODE)
    assert response.status_code == 429


def test_daily_cap_counts_only_today(db):
    init_store(db)
    old = create_run(db, "old")
    with sqlite3.connect(db) as con:
        con.execute("UPDATE runs SET created_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (old,))
    assert datetime.now(UTC).year > 2000
    with make_client(db, settings(daily_run_cap=2), happy_clients()) as client:
        run_id = propose(client)["run_id"]
        client.post(f"/api/claims/{run_id}/confirm", json={"edits": []}, headers=CODE)
        assert client.post(f"/api/claims/{run_id}/verify", headers=CODE).status_code == 202


def test_rate_limit_is_30_posts_a_minute(db):
    with make_client(db) as client:
        codes = [client.post("/api/claims/nope/verify", headers=CODE).status_code for _ in range(31)]
        read = client.get("/api/runs", headers=CODE).status_code
    assert codes[:30] == [404] * 30 and codes[30] == 429
    assert read == 200


def test_rate_limit_state_is_per_app(db):
    with make_client(db) as first:
        for _ in range(30):
            first.post("/api/claims/nope/verify", headers=CODE)
    with make_client(db) as second:
        assert second.post("/api/claims/nope/verify", headers=CODE).status_code == 404


def test_docs_search_and_detail(db):
    with make_client(db) as client:
        listing = client.get("/api/docs", params={"q": "language model", "limit": 3}, headers=CODE).json()
        doc_id = listing[0]["doc_id"]
        detail = client.get(f"/api/docs/{doc_id}", headers=CODE)
        missing = client.get("/api/docs/does-not-exist", headers=CODE)
    assert 0 < len(listing) <= 3 and set(listing[0]) == {"doc_id", "title", "authors", "published"}
    assert detail.status_code == 200 and detail.json()["doc_id"] == doc_id and detail.json()["abstract"]
    assert missing.status_code == 404


def test_startup_builds_docs_when_missing(tmp_path):
    path = tmp_path / "fresh.sqlite"
    with make_client(path) as client:
        assert client.get("/api/health").json()["docs"] > 0


def test_startup_keeps_existing_docs(db):
    with make_client(db) as client:
        before = client.get("/api/health").json()["docs"]
    with make_client(db) as client:
        assert client.get("/api/health").json()["docs"] == before


@pytest.fixture
def static_dir(tmp_path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>app</html>")
    (root / "assets" / "app.js").write_text("console.log(1)")
    return root


def test_spa_fallback_and_static_files(db, static_dir):
    with make_client(db, static_dir=static_dir) as client:
        root = client.get("/")
        deep = client.get("/traces/abc")
        asset = client.get("/assets/app.js")
        unknown_api = client.get("/api/unknown")
        escape = client.get("/..%2f..%2fetc/passwd")
    assert root.status_code == 200 and "app" in root.text
    assert deep.status_code == 200 and deep.text == "<html>app</html>"
    assert asset.status_code == 200 and "console.log" in asset.text
    assert unknown_api.status_code == 404
    assert escape.text == "<html>app</html>"


def test_no_static_dir_leaves_root_404(db):
    with make_client(db) as client:
        assert client.get("/").status_code == 404


def test_cors_allows_only_the_vite_origin(db):
    with make_client(db) as client:
        ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        other = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in other.headers


def test_spans_are_stored_in_the_db(db):
    with make_client(db, clients=happy_clients()) as client:
        run_id = propose(client)["run_id"]
    assert [s.name for s in list_spans(db, run_id)] == ["claim", "decompose"]


def test_create_app_from_env_honours_path_overrides(monkeypatch, tmp_path, corpus_db):
    from fact_checker.api.app import create_app_from_env

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<p>spa</p>")
    db = tmp_path / "env.sqlite"
    monkeypatch.setenv("FC_DB", str(db))
    monkeypatch.setenv("FC_WEB_DIST", str(dist))
    monkeypatch.setenv("FC_CORPUS", str(COMMITTED))
    monkeypatch.delenv("FC_ACCESS_CODE", raising=False)
    with TestClient(create_app_from_env()) as client:
        assert client.get("/api/health").json() == {"ok": True, "docs": 48}
        assert "spa" in client.get("/somewhere").text
