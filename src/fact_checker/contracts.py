"""The five JSON contracts of the fact checker, as pydantic models."""

from types import MappingProxyType
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

Stance = Literal["supports", "contradicts"]
Verdict = Literal["supported", "contradicted", "unknown"]
Dimension = Literal[
    "evidence_relevance",
    "statement_verdicts",
    "overreach",
    "conflict_handling",
    "aggregation",
    "unknown_calibration",
]


class Strict(BaseModel):
    """Base model that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


class Statement(Strict):
    """One statement the claim implies."""

    id: int
    text: str
    load_bearing: bool
    implied_by: str
    query: str
    kind: Literal["explicit", "implicit_assumption", "framing_bias"]
    mark: Literal["confirmed", "user_edited", "user_added"]


class Edit(Strict):
    """One change the user made to the proposed statements."""

    op: Literal["drop", "edit", "add", "flip_load_bearing", "feedback"]
    id: int | None
    value: str | None


class ConfirmedStatements(Strict):
    """The statements the user confirmed for a claim."""

    schema_version: Literal[1] = 1
    claim: str
    statements: list[Statement] = Field(min_length=1, max_length=5)
    proposed: list[Statement]
    edits: list[Edit]
    rounds: int = Field(ge=0, le=3)
    source: Literal["chat", "case"]

    @model_validator(mode="after")
    def _check_statements(self) -> Self:
        """Require unique ids and an implied_by span of the claim, except for user_added."""
        ids = [s.id for s in self.statements]
        if len(ids) != len(set(ids)):
            raise ValueError("statement ids must be unique")
        for s in self.statements:
            if s.mark != "user_added" and s.implied_by not in self.claim:
                raise ValueError(f"implied_by of statement {s.id} is not in the claim")
        return self


class Hit(Strict):
    """One retrieved passage."""

    passage_id: str
    doc_id: str
    title: str
    score: float
    text: str


class RetrievalResult(Strict):
    """The passages retrieved for a query."""

    query: str
    k: int
    per_doc: int
    hits: list[Hit]


class Evidence(Strict):
    """A quote from a passage and the stance it takes."""

    passage_id: str
    quote: str
    stance: Stance

    @field_validator("quote")
    @classmethod
    def _quote_has_5_words(cls, quote: str) -> str:
        """Reject quotes shorter than 5 words."""
        if len(quote.split()) < 5:
            raise ValueError("quote must be at least 5 words")
        return quote


class StatementVerdict(Strict):
    """The model's verdict on one statement."""

    id: int
    queries: list[str]
    evidence: list[Evidence]
    verdict: Verdict
    reason: str


class Verdicts(Strict):
    """One verdict per confirmed statement."""

    schema_version: Literal[1] = 1
    statements: list[StatementVerdict]

    @model_validator(mode="after")
    def _check_ids(self, info: ValidationInfo) -> Self:
        """Reject duplicate ids, and with context confirmed_ids any missing or extra id."""
        ids = [s.id for s in self.statements]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate statement ids")
        confirmed = (info.context or {}).get("confirmed_ids")
        if confirmed is not None and set(ids) != set(confirmed):
            raise ValueError(f"verdict ids {sorted(ids)} must equal confirmed ids {sorted(confirmed)}")
        return self


class Overall(Strict):
    """The overall verdict and the aggregation rule that fired."""

    verdict: Verdict
    rule: int = Field(ge=0, le=4)


class FinalEvidence(Strict):
    """A verified quote with its paper."""

    doc_id: str
    title: str
    authors: list[str]
    published: str
    quote: str
    stance: Stance


class FinalStatement(Strict):
    """One statement of the final answer."""

    id: int
    text: str
    load_bearing: bool
    mark: Literal["confirmed", "user_edited", "user_added"]
    model_verdict: Verdict
    verdict: Verdict
    downgrade_reason: Literal["quote_failed", "no_hits", "conflict"] | None
    evidence: list[FinalEvidence]
    dropped_quotes: list[Evidence]


class Counts(Strict):
    """How many statements came from each mark, and how many were dropped."""

    confirmed: int
    user_edited: int
    user_added: int
    dropped: int


class FinalAnswer(Strict):
    """The checked answer for a claim."""

    schema_version: Literal[1] = 1
    claim: str
    overall: Overall
    statements: list[FinalStatement]
    counts: Counts


class DimensionScore(Strict):
    """A 1 to 5 score with its evidence."""

    score: int = Field(ge=1, le=5)
    evidence: str


class Dimensions(Strict):
    """The six judged dimensions."""

    evidence_relevance: DimensionScore
    statement_verdicts: DimensionScore
    overreach: DimensionScore
    conflict_handling: DimensionScore
    aggregation: DimensionScore
    unknown_calibration: DimensionScore


class Flag(Strict):
    """A problem the judge flagged on one statement."""

    statement_id: int
    dimension: Dimension
    reason: str


class JudgeScores(Strict):
    """The judge's scores for a final answer."""

    schema_version: Literal[1] = 1
    model: str
    seconds: float
    dimensions: Dimensions
    flagged: list[Flag]
    needs_attention: bool


SCHEMAS = MappingProxyType(
    {
        "confirmed": ConfirmedStatements,
        "retrieval": RetrievalResult,
        "verdicts": Verdicts,
        "final": FinalAnswer,
        "scores": JudgeScores,
    }
)
