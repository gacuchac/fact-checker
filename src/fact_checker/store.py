"""The run store: runs and their trace spans, in the same SQLite file as the abstracts."""

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

STATUSES = ("proposed", "confirmed", "verifying", "done", "failed")
JSON_FIELDS = ("proposed", "confirmed", "result")
UPDATABLE = ("status", "error", *JSON_FIELDS)
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, claim TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, proposed TEXT, confirmed TEXT, result TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS spans (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, parent_id TEXT, seq INTEGER NOT NULL, kind TEXT NOT NULL,
    name TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT NOT NULL, status TEXT NOT NULL, model TEXT,
    input TEXT, output TEXT, usage TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS spans_run_seq ON spans (run_id, seq);
"""
RUN_COLUMNS = "id, claim, status, created_at, updated_at, proposed, confirmed, result, error"
SPAN_COLUMNS = "id, run_id, parent_id, seq, kind, name, started_at, ended_at, status, model, input, output, usage, error"


class RunSummary(BaseModel):
    """One run in a listing."""

    id: str
    claim: str
    status: str
    created_at: str
    updated_at: str
    error: str | None = None


class RunRecord(RunSummary):
    """One run with its stored JSON: the proposed and confirmed statements and the check result."""

    proposed: Any = None
    confirmed: Any = None
    result: Any = None


class Span(BaseModel):
    """One step of a run's trace; input, output and usage hold JSON values."""

    id: str
    run_id: str
    parent_id: str | None
    seq: int
    kind: str
    name: str
    started_at: str
    ended_at: str
    status: str
    model: str | None
    input: Any
    output: Any
    usage: Any
    error: str | None


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string, which sorts as time does."""
    return datetime.now(UTC).isoformat()


def _dump(value: Any) -> str | None:
    return None if value is None else json.dumps(to_jsonable_python(value))


def _load(text: str | None) -> Any:
    return None if text is None else json.loads(text)


@contextmanager
def _connect(db: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(db, timeout=30)) as con, con:
        yield con


def init_store(db: Path) -> None:
    """Create the runs and spans tables in db if they are missing; docs and passages are never touched."""
    db.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db) as con:
        con.executescript(SCHEMA)


def create_run(db: Path, claim: str) -> str:
    """Insert a run for claim with status proposed and return its id (a uuid4 hex)."""
    run_id = uuid.uuid4().hex
    now = now_iso()
    with _connect(db) as con:
        con.execute(
            f"INSERT INTO runs ({RUN_COLUMNS}) VALUES (?, ?, 'proposed', ?, ?, NULL, NULL, NULL, NULL)",
            (run_id, claim, now, now),
        )
    return run_id


def get_run(db: Path, run_id: str) -> RunRecord | None:
    """Return the run with its JSON columns decoded, or None when there is no such run."""
    with _connect(db) as con:
        row = con.execute(f"SELECT {RUN_COLUMNS} FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    id_, claim, status, created, updated, proposed, confirmed, result, error = row
    return RunRecord(
        id=id_,
        claim=claim,
        status=status,
        created_at=created,
        updated_at=updated,
        proposed=_load(proposed),
        confirmed=_load(confirmed),
        result=_load(result),
        error=error,
    )


def list_runs(db: Path, limit: int = 50) -> list[RunSummary]:
    """Return the newest `limit` runs, newest first, without their JSON columns."""
    with _connect(db) as con:
        rows = con.execute(
            "SELECT id, claim, status, created_at, updated_at, error FROM runs "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
    keys = ("id", "claim", "status", "created_at", "updated_at", "error")
    return [RunSummary(**dict(zip(keys, row, strict=True))) for row in rows]


def update_run(db: Path, run_id: str, **fields: Any) -> None:
    """Set status, error, proposed, confirmed or result on a run and refresh its updated_at.

    JSON columns accept any JSON-serialisable value or pydantic model. Raises ValueError for another field
    or a status outside proposed|confirmed|verifying|done|failed, and KeyError when there is no such run.
    """
    unknown = set(fields) - set(UPDATABLE)
    if unknown:
        raise ValueError(f"cannot update {sorted(unknown)}")
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError(f"unknown status {fields['status']!r}")
    values = {k: _dump(v) if k in JSON_FIELDS else v for k, v in fields.items()}
    values["updated_at"] = now_iso()
    assignments = ", ".join(f"{name} = ?" for name in values)
    with _connect(db) as con:
        cursor = con.execute(f"UPDATE runs SET {assignments} WHERE id = ?", (*values.values(), run_id))
    if cursor.rowcount == 0:
        raise KeyError(run_id)


def add_span(db: Path, span: Span) -> None:
    """Insert one span of a run's trace."""
    values = [span.model_dump()[c.strip()] for c in SPAN_COLUMNS.split(",")]
    json_at = [SPAN_COLUMNS.split(", ").index(c) for c in ("input", "output", "usage")]
    for i in json_at:
        values[i] = _dump(values[i])
    marks = ", ".join("?" * len(values))
    with _connect(db) as con:
        con.execute(f"INSERT INTO spans ({SPAN_COLUMNS}) VALUES ({marks})", values)


def list_spans(db: Path, run_id: str) -> list[Span]:
    """Return the spans of a run ordered by seq; empty for an unknown run."""
    with _connect(db) as con:
        rows = con.execute(f"SELECT {SPAN_COLUMNS} FROM spans WHERE run_id = ? ORDER BY seq", (run_id,)).fetchall()
    keys = SPAN_COLUMNS.split(", ")
    spans = []
    for row in rows:
        data = dict(zip(keys, row, strict=True))
        spans.append(Span(**{**data, **{k: _load(data[k]) for k in ("input", "output", "usage")}}))
    return spans


def next_seq(db: Path, run_id: str) -> int:
    """Return the seq the next span of the run takes: 0 for a run without spans."""
    with _connect(db) as con:
        (top,) = con.execute("SELECT MAX(seq) FROM spans WHERE run_id = ?", (run_id,)).fetchone()
    return 0 if top is None else top + 1


def count_runs_since(db: Path, iso_ts: str, statuses: tuple[str, ...] | None = None) -> int:
    """Return how many runs were created at or after iso_ts (an ISO 8601 UTC timestamp).

    With statuses, only runs whose status is one of them are counted.
    """
    sql, params = "SELECT COUNT(*) FROM runs WHERE created_at >= ?", [iso_ts]
    if statuses:
        sql += f" AND status IN ({', '.join('?' for _ in statuses)})"
        params.extend(statuses)
    with _connect(db) as con:
        (count,) = con.execute(sql, params).fetchone()
    return count


def transition_status(db: Path, run_id: str, expected: str, new: str) -> bool:
    """Atomically move the run from status expected to new; return False if the run was not in expected."""
    with _connect(db) as con:
        changed = con.execute(
            "UPDATE runs SET status = ?, error = NULL, updated_at = ? WHERE id = ? AND status = ?",
            (new, now_iso(), run_id, expected),
        ).rowcount
    return changed == 1
