"""Applying the user's edits to the proposed statements, and the falsifiability check of edited ones."""

from pydantic import BaseModel

from fact_checker.contracts import ConfirmedStatements, Edit, Statement
from fact_checker.llm.base import LLMClient, Usage
from fact_checker.services.loader import load_prompt
from fact_checker.services.schemas import FalsifiabilityOutput

CHECKED_MARKS = ("user_edited", "user_added")


class Issue(BaseModel):
    """Why one statement failed the falsifiability check."""

    statement_id: int
    reason: str


def _target(statements: list[Statement], edit: Edit) -> Statement:
    match = next((s for s in statements if s.id == edit.id), None)
    if match is None:
        raise ValueError(f"edit {edit.op} names unknown statement id {edit.id}")
    return match


def _added(claim: str, text: str, statement_id: int) -> Statement:
    return Statement(
        id=statement_id,
        text=text,
        load_bearing=True,
        implied_by=claim,
        query=text,
        kind="explicit",
        mark="user_added",
    )


def _apply(claim: str, statements: list[Statement], edit: Edit, next_id: int) -> tuple[list[Statement], int]:
    if edit.op == "add":
        return [*statements, _added(claim, edit.value or "", next_id)], next_id + 1
    if edit.op == "feedback":
        return statements, next_id
    target = _target(statements, edit)
    if edit.op == "drop":
        return [s for s in statements if s is not target], next_id
    if edit.op == "flip_load_bearing":
        change = {"load_bearing": not target.load_bearing}
    else:
        change = {"text": edit.value or "", "mark": "user_added" if target.mark == "user_added" else "user_edited"}
    return [s.model_copy(update=change) if s is target else s for s in statements], next_id


def apply_edits(claim: str, proposed: list[Statement], edits: list[Edit]) -> ConfirmedStatements:
    """Return the confirmed statements after applying edits in order to a copy of proposed.

    drop removes a statement, edit sets its text and marks it user_edited, flip_load_bearing inverts its
    flag, feedback changes nothing, and add appends a user_added statement (explicit, load-bearing,
    implied_by the whole claim, the next free id). proposed is kept as given and edits are recorded;
    rounds is 1 and source "chat". Raises ValueError for an edit naming an unknown id, and pydantic's
    ValidationError if the result is not a valid ConfirmedStatements.
    """
    statements = list(proposed)
    next_id = max((s.id for s in proposed), default=-1) + 1
    for edit in edits:
        statements, next_id = _apply(claim, statements, edit, next_id)
    return ConfirmedStatements(
        claim=claim, statements=statements, proposed=proposed, edits=edits, rounds=1, source="chat"
    )


def check_statements(
    confirmed: ConfirmedStatements, client: LLMClient, model: str, effort: str | None
) -> tuple[ConfirmedStatements, list[Issue], list[Usage]]:
    """Run the falsifiability check on each user_edited or user_added statement, one call each.

    Returns the confirmed statements with the query of every passing statement replaced by the model's, one
    Issue per failing statement, and the usage of each call. Raises LLMError if a call fails.
    """
    system = load_prompt("falsifiable")
    statements: list[Statement] = []
    issues: list[Issue] = []
    usages: list[Usage] = []
    for s in confirmed.statements:
        if s.mark not in CHECKED_MARKS:
            statements.append(s)
            continue
        output, usage = client.complete(system, s.text, FalsifiabilityOutput, model, effort)
        usages.append(usage)
        if output.falsifiable:
            statements.append(s.model_copy(update={"query": output.query}))
        else:
            statements.append(s)
            issues.append(Issue(statement_id=s.id, reason=output.reason))
    return confirmed.model_copy(update={"statements": statements}), issues, usages
