"""Code checks that each grounded verdict follows from its own kept quotes."""

from fact_checker.contracts import FinalAnswer, Flag


def one_sided_unknowns(final: FinalAnswer) -> list[Flag]:
    """Return an unknown_calibration flag per statement left unknown although all its kept quotes take one stance.

    Only the model's own unknown counts: a statement code downgraded (conflict, failed quote, no hits) is not
    flagged, and neither is one without kept quotes or with quotes of both stances. The reason names the stance
    and asks for the verdict to change or for the part of the statement no quote covers.
    """
    flags = []
    for statement in final.statements:
        stances = {evidence.stance for evidence in statement.evidence}
        if statement.verdict != "unknown" or statement.downgrade_reason is not None or len(stances) != 1:
            continue
        flags.append(
            Flag(
                statement_id=statement.id,
                dimension="unknown_calibration",
                reason=(
                    f"Code check: every kept quote {stances.pop()} the statement, yet the verdict is unknown. "
                    "Read the quotes together: change the verdict if they establish the statement, or keep unknown "
                    "and name the part of the statement that no quote covers."
                ),
            )
        )
    return flags
