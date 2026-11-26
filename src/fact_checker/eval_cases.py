"""Read-only view model of the eval case files, for the Evals tab."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class EvalStatementView(BaseModel):
    """One gold statement of a statements-mode case."""

    text: str
    gold_verdict: str
    load_bearing: bool


class EvalCaseView(BaseModel):
    """What the Evals tab shows for one case file; `error` is set when the file is unreadable."""

    id: str
    mode: str
    claim: str | None = None
    expected: list[str] = []
    statements: list[EvalStatementView] = []
    must_cite_docs: list[str] = []
    must_find_docs: list[str] = []
    owasp: list[str] = []
    checks: list[str] = []
    budgets: dict[str, Any] = {}
    has_edits: bool = False
    has_planted_docs: bool = False
    error: str | None = None


def _statements_fields(factcheck: dict[str, Any]) -> dict[str, Any]:
    raw_statements = factcheck.get("statements")
    if not isinstance(raw_statements, list):
        raise TypeError("missing factcheck.statements")
    return {
        "claim": factcheck.get("claim"),
        "expected": [str(factcheck["label"])] if "label" in factcheck else [],
        "statements": [
            EvalStatementView(
                text=s["text"],
                gold_verdict=s["gold_verdict"],
                load_bearing=s["load_bearing"],
            )
            for s in raw_statements
        ],
        "must_cite_docs": [str(d) for d in factcheck.get("gold_doc_ids") or []],
    }


def _mode_fields(mode: str, raw: dict[str, Any]) -> dict[str, Any]:
    factcheck = raw.get("factcheck")
    if not isinstance(factcheck, dict):
        if mode == "statements":
            raise TypeError("missing factcheck")
        return {}
    if mode == "statements":
        return _statements_fields(factcheck)
    claim = factcheck.get("claim")
    return {"claim": claim if isinstance(claim, str) else None}


def case_view(raw: object, case_id: str) -> EvalCaseView:
    """Map one parsed YAML case to an EvalCaseView; never raises, sets `error` on bad input."""
    if not isinstance(raw, dict):
        return EvalCaseView(id=case_id, mode="unknown", error="not a mapping")
    raw_id = raw.get("id")
    view_id = raw_id if isinstance(raw_id, str) else case_id
    mode = str(raw.get("mode", "unknown"))
    try:
        fields = _mode_fields(mode, raw)
        owasp = [str(t) for t in raw.get("owasp") or []]
        budgets = dict(raw.get("budgets") or {})
        return EvalCaseView(id=view_id, mode=mode, owasp=owasp, budgets=budgets, **fields)
    except (ValueError, TypeError, KeyError) as exc:
        return EvalCaseView(id=view_id, mode=mode, error=str(exc) or "invalid case")


def load_case_views(folder: Path) -> list[EvalCaseView]:
    """Return one EvalCaseView per `*.yaml` in `folder`, sorted by file name; [] if missing."""
    if not folder.is_dir():
        return []
    views = []
    for path in sorted(folder.glob("*.yaml"), key=lambda p: p.name):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
            error = f"invalid YAML: {path.name}: {type(exc).__name__}"
            views.append(EvalCaseView(id=path.stem, mode="unknown", error=error))
            continue
        views.append(case_view(raw, path.stem))
    return views
