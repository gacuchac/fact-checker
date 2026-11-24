import json
from pathlib import Path

from fact_checker.contracts import (
    ConfirmedStatements,
    Dimensions,
    DimensionScore,
    Evidence,
    Flag,
)
from fact_checker.services.schemas import (
    ReviewOutput,
    VerdictOutputItem,
    VerdictsOutput,
)

ROOT = Path(__file__).parent
V6 = ROOT / "fixtures" / "spike6" / "V6"
COMMITTED = ROOT.parent / "data" / "corpus.json"


def v6_confirmed():
    return ConfirmedStatements.model_validate_json((V6 / "confirmed.json").read_text())


def v6_output():
    verdicts = json.loads((V6 / "verdicts.json").read_text())
    items = [
        VerdictOutputItem(
            id=s["id"],
            evidence=[Evidence(**e) for e in s["evidence"]],
            verdict=s["verdict"],
            reason=s["reason"],
        )
        for s in verdicts["statements"]
    ]
    return VerdictsOutput(statements=items)


def revised_output():
    first = v6_output().statements
    unknown = VerdictOutputItem(id=1, evidence=[], verdict="unknown", reason="The quote does not settle it.")
    return VerdictsOutput(statements=[first[0], unknown])


def dimensions(score=5):
    d = DimensionScore(score=score, evidence="e")
    return Dimensions(
        evidence_relevance=d,
        statement_verdicts=d,
        overreach=d,
        conflict_handling=d,
        aggregation=d,
        unknown_calibration=d,
    )


def review_output(flagged=()):
    return ReviewOutput(dimensions=dimensions(), flagged=list(flagged))


def flag(statement_id=1):
    return Flag(statement_id=statement_id, dimension="overreach", reason="the quote is about maintaining, not degrading")
