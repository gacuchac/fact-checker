import re
from pathlib import Path

import pytest

from fact_checker.cli import main

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "agents" / "claim-verifier.md"
RUNBOOK = ROOT / "docs" / "RUNBOOK.md"


def _between(text: str, name: str) -> str:
    begin, end = f"<!-- schema:{name}:begin -->", f"<!-- schema:{name}:end -->"
    assert text.count(begin) == 1 and text.count(end) == 1
    body = text.split(begin, 1)[1].split(end, 1)[0]
    body = re.sub(r"^\s*```\w*\s*\n", "", body)
    body = re.sub(r"\n\s*```\s*$", "", body.strip())
    return body.strip()


@pytest.mark.parametrize(
    ("path", "name"),
    [(VERIFIER, "verdicts"), (RUNBOOK, "confirmed")],
)
def test_us13_embedded_schema_equals_fc_schema_output(path, name, capsys):
    assert main(["schema", name]) == 0
    expected = capsys.readouterr().out.strip()
    assert _between(path.read_text(), name) == expected


def test_us13_verifier_prompt_names_its_tools_and_the_unknown_rule():
    text = VERIFIER.read_text()
    for needle in ("fc retrieve", "fc finalize", "fc judge", "Missing information is never a contradiction"):
        assert needle in text


def test_us13_runbook_names_validate_show_and_verifier_path():
    text = RUNBOOK.read_text()
    for needle in ("fc validate", "fc show", "agents/claim-verifier.md"):
        assert needle in text


def test_us13_runbook_allows_statement_zero_to_entail_its_parts_and_preflights_the_judge():
    runbook = (Path(__file__).resolve().parents[1] / "docs" / "RUNBOOK.md").read_text()
    assert "except that statement 0" in runbook
    assert "tests/fixtures/spike6/V4" in runbook


def test_us13_verifier_prompt_has_no_machine_specific_path():
    prompt = (Path(__file__).resolve().parents[1] / "agents" / "claim-verifier.md").read_text()
    assert "/Users/" not in prompt
    assert "<root>" in prompt
