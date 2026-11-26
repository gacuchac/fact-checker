from pathlib import Path

from fact_checker.eval_cases import case_view, load_case_views


def v7_raw() -> dict:
    return {
        "id": "V7",
        "mode": "statements",
        "factcheck": {
            "claim": "Long context hurts retrieval.",
            "label": "supported",
            "statements": [
                {"text": "s1", "gold_verdict": "supported", "load_bearing": True},
                {"text": "s2", "gold_verdict": "supported", "load_bearing": True},
            ],
            "gold_doc_ids": ["2307.03172v3", "2406.16008v2"],
        },
    }


def test_us1_statements_case_is_mapped():
    v = case_view(v7_raw(), "V7")
    assert v.id == "V7"
    assert v.mode == "statements"
    assert v.claim == "Long context hurts retrieval."
    assert v.expected == ["supported"]
    assert [s.text for s in v.statements] == ["s1", "s2"]
    assert all(s.gold_verdict == "supported" and s.load_bearing is True for s in v.statements)
    assert v.must_cite_docs == ["2307.03172v3", "2406.16008v2"]
    assert v.must_find_docs == []
    assert v.checks == []
    assert v.has_edits is False
    assert v.has_planted_docs is False
    assert v.error is None


def test_us1_owasp_and_budgets_pass_through():
    raw = v7_raw()
    raw["owasp"] = ["LLM01"]
    raw["budgets"] = {"max_cost": 1.5}
    v = case_view(raw, "V7")
    assert v.owasp == ["LLM01"]
    assert v.budgets == {"max_cost": 1.5}


def test_us1_unknown_mode_keeps_mode_and_claim():
    v = case_view({"id": "Z1", "mode": "future", "factcheck": {"claim": "c"}}, "Z1")
    assert v.mode == "future"
    assert v.claim == "c"
    assert v.error is None


def test_us1_missing_mode_is_unknown():
    raw = v7_raw()
    del raw["mode"]
    assert case_view(raw, "V7").mode == "unknown"


def test_us1_non_mapping_raw_sets_error():
    for raw in (["a"], "text"):
        v = case_view(raw, "stem")
        assert v.id == "stem"
        assert v.error


def test_us1_statements_without_statements_sets_error():
    raw = v7_raw()
    del raw["factcheck"]["statements"]
    v = case_view(raw, "V7")
    assert v.error
    assert v.id == "V7"


def test_us1_numeric_doc_id_is_coerced_to_str():
    raw = v7_raw()
    raw["factcheck"]["gold_doc_ids"] = [2307.0317]
    v = case_view(raw, "V7")
    assert v.must_cite_docs == ["2307.0317"]
    assert isinstance(v.must_cite_docs[0], str)


def test_us1_loader_sorts_by_file_name_and_flags_only_malformed(tmp_path: Path):
    (tmp_path / "B.yaml").write_text("id: B\nmode: future\nfactcheck:\n  claim: c\n")
    (tmp_path / "A.yaml").write_text(
        "id: A\nmode: statements\nfactcheck:\n  claim: c\n  label: supported\n"
        "  statements:\n    - {text: t, gold_verdict: supported, load_bearing: true}\n"
        "  gold_doc_ids: []\n"
    )
    (tmp_path / "bad.yaml").write_text("id: [unclosed")
    views = load_case_views(tmp_path)
    assert [v.id for v in views] == ["A", "B", "bad"]
    assert [v.error is None for v in views] == [True, True, False]
    assert str(tmp_path) not in views[2].error


def test_us1_loader_missing_folder_is_empty(tmp_path: Path):
    assert load_case_views(tmp_path / "missing") == []
