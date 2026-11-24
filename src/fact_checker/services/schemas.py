"""LLM-facing output models: no defaults and no schema_version, so strict JSON schemas work."""

from typing import Literal

from fact_checker.contracts import Dimensions, Evidence, Flag, Strict, Verdict


class DecomposedStatement(Strict):
    """One statement the decomposition model proposes."""

    text: str
    kind: Literal["explicit", "implicit_assumption", "framing_bias"]
    load_bearing: bool
    implied_by: str
    query: str


class DecomposeOutput(Strict):
    """The decomposition model's statements, statement 0 first."""

    statements: list[DecomposedStatement]


class FalsifiabilityOutput(Strict):
    """The falsifiability verdict on one user-written statement."""

    falsifiable: bool
    reason: str
    query: str


class VerdictOutputItem(Strict):
    """The verifier's verdict on one statement."""

    id: int
    evidence: list[Evidence]
    verdict: Verdict
    reason: str


class VerdictsOutput(Strict):
    """The verifier's verdicts, one per statement."""

    statements: list[VerdictOutputItem]


class ReviewOutput(Strict):
    """The reviewer's six scores and flags."""

    dimensions: Dimensions
    flagged: list[Flag]
