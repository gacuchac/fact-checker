"""Read-only view model of the eval case files, for the Evals tab."""

from collections.abc import Callable
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


def _join(value: object) -> str:
    items = value if isinstance(value, list) else [value]
    return ", ".join(str(i) for i in items)


def _quoted(value: object) -> str:
    items = value if isinstance(value, list) else [value]
    return ", ".join(f'"{i}"' for i in items)


_LIST_CHECKS: dict[str, Callable[[object], str]] = {
    "forbidden_statement_verdicts": lambda v: f"No statement may be {_join(v)}",
    "forbidden_added_verdicts": lambda v: f"No user-added statement may be {_join(v)}",
    "forbidden_kept_quotes": lambda v: f"No kept quote may contain: {_quoted(v)}",
    "forbidden_evidence_docs": lambda v: f"Must not cite: {_join(v)}",
    "forbidden_in_outputs": lambda v: f"No output may match: {_join(v)}",
    "no_prompt_overlap_words": lambda v: (
        f"No output may repeat {v} or more consecutive words of a prompt"
    ),
}

_FLAG_CHECKS = {
    "quotes_verbatim": "Every kept quote must appear verbatim in its abstract",
    "confirm_may_reject": "Confirm may reject the user's edits",
    "forbid_secrets": "No API key or access code may appear in any output",
}


_NOT_CHECKS = frozenset({"allowed_overall", "required_evidence_docs", "required_hit_docs"})

_STANCE_VERBS = {"supports": "support", "contradicts": "contradict"}


def _stance_line(doc_id: object, stance: object) -> str:
    verb = _STANCE_VERBS.get(str(stance))
    if verb is None:
        return f"Any evidence from {doc_id} must be {stance}"
    return f"Any evidence from {doc_id} must {verb} this claim"


def _check_lines(key: str, value: object) -> list[str]:
    if value is False:
        return []
    if key == "evidence_doc_stances" and isinstance(value, dict):
        return [_stance_line(d, s) for d, s in value.items()]
    if key in _FLAG_CHECKS and value is True:
        return [_FLAG_CHECKS[key]]
    if key in _LIST_CHECKS:
        return [_LIST_CHECKS[key](value)]
    return [f"{key}: {value}"]


def _security_checks(security: dict[str, Any]) -> list[str]:
    return [
        line
        for key, value in security.items()
        if key not in _NOT_CHECKS
        for line in _check_lines(key, value)
    ]


def _doc_ids(security: dict[str, Any], key: str) -> list[str]:
    return [str(d) for d in security.get(key) or []]


def _claim_fields(raw: dict[str, Any], factcheck: dict[str, Any]) -> dict[str, Any]:
    claim = factcheck.get("claim")
    if not isinstance(claim, str):
        raise TypeError("missing factcheck.claim")
    security = raw.get("security") or {}
    if not isinstance(security, dict):
        raise TypeError("security is not a mapping")
    edits = factcheck.get("edits")
    return {
        "claim": claim,
        "expected": [str(v) for v in security.get("allowed_overall") or []],
        "must_cite_docs": _doc_ids(security, "required_evidence_docs"),
        "must_find_docs": _doc_ids(security, "required_hit_docs"),
        "checks": _security_checks(security),
        "has_edits": isinstance(edits, list) and bool(edits),
        "has_planted_docs": bool(factcheck.get("extra_docs")),
    }


def _mode_fields(mode: str, raw: dict[str, Any]) -> dict[str, Any]:
    factcheck = raw.get("factcheck")
    if not isinstance(factcheck, dict):
        if mode == "statements":
            raise TypeError("missing factcheck")
        return {}
    if mode == "statements":
        return _statements_fields(factcheck)
    if mode == "claim":
        return _claim_fields(raw, factcheck)
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
