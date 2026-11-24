"""The fc command line: a thin layer over the library functions."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from fact_checker import corpus
from fact_checker.contracts import (
    SCHEMAS,
    ConfirmedStatements,
    FinalAnswer,
    JudgeScores,
    Verdicts,
)
from fact_checker.finalize import finalize, rerun_queries
from fact_checker.index import build_index
from fact_checker.report import render_answer, run_files
from fact_checker.retrieve import retrieve

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_CORPUS = DATA_DIR / "corpus.json"
DEFAULT_DB = DATA_DIR / "index.sqlite"


def _schema(args: argparse.Namespace) -> int:
    print(json.dumps(SCHEMAS[args.name].model_json_schema(), indent=2))
    return 0


def _fetch(args: argparse.Namespace) -> int:
    try:
        kept, _ = corpus.keep_latest(corpus.ARXIV_IDS)
        fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        built = corpus.build_corpus(corpus.ARXIV_IDS, corpus.fetch_feed(kept), fetched_at)
    except (RuntimeError, ValueError) as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1
    corpus.save_corpus(built, args.corpus)
    print(f"{len(built.docs)} docs, dropped_ids={built.dropped_ids}", file=sys.stderr)
    return 0


def _index(args: argparse.Namespace) -> int:
    if not args.corpus.exists():
        print(f"corpus not found: {args.corpus}: run fc fetch", file=sys.stderr)
        return 1
    stats = build_index(corpus.load_corpus(args.corpus), args.db)
    print(f"indexed {stats.docs} docs, {stats.passages} passages")
    return 0


def _log_event(run: Path, cmd: str, ok: bool, **fields: object) -> None:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with (run / "events.jsonl").open("a") as log:
        log.write(json.dumps({"ts": ts, "cmd": cmd, "ok": ok, **fields}) + "\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fail(run: Path, cmd: str, message: object) -> int:
    print(message, file=sys.stderr)
    _log_event(run, cmd, False)
    return 1


def _has_run(run: Path | None) -> bool:
    if run is None or run.is_dir():
        return True
    print(f"run folder not found: {run}", file=sys.stderr)
    return False


def _validate(args: argparse.Namespace) -> int:
    if not _has_run(args.run):
        return 1
    try:
        confirmed = ConfirmedStatements.model_validate_json((args.run / "confirmed.json").read_text())
    except (OSError, ValidationError) as exc:
        return _fail(args.run, "validate", exc)
    _log_event(args.run, "validate", True, rounds=confirmed.rounds, edits=len(confirmed.edits), model=args.model)
    return 0


def _retrieve(args: argparse.Namespace) -> int:
    if not _has_run(args.run):
        return 1
    try:
        result = retrieve(args.db, args.query, k=args.k)
    except FileNotFoundError:
        print("index not found: run fc index", file=sys.stderr)
        if args.run:
            _log_event(args.run, "retrieve", False)
        return 1
    if args.json:
        print(result.model_dump_json())
    else:
        for rank, hit in enumerate(result.hits, 1):
            print(f"{rank} {hit.score:.2f} {hit.doc_id} {hit.title}")
    if args.run:
        _log_event(args.run, "retrieve", True, doc_ids=[h.doc_id for h in result.hits])
    return 0


def _load_finalize_inputs(run: Path) -> tuple[ConfirmedStatements, Verdicts]:
    confirmed = ConfirmedStatements.model_validate_json((run / "confirmed.json").read_text())
    ids = [s.id for s in confirmed.statements]
    verdicts = Verdicts.model_validate_json((run / "verdicts.json").read_text(), context={"confirmed_ids": ids})
    return confirmed, verdicts


def _write_final(run: Path, confirmed: ConfirmedStatements, verdicts: Verdicts, db: Path) -> None:
    final = finalize(confirmed, verdicts, db)
    (run / "final.json").write_text(final.model_dump_json(indent=2))
    by_id = {sv.id: sv for sv in verdicts.statements}
    results = {s.id: rerun_queries(by_id[s.id], db) for s in confirmed.statements}
    for name, text in run_files(confirmed, verdicts, final, results).items():
        (run / name).write_text(text)


def _finalize(args: argparse.Namespace) -> int:
    if not _has_run(args.run):
        return 1
    if not args.db.exists():
        return _fail(args.run, "finalize", "index not found: run fc index")
    try:
        confirmed, verdicts = _load_finalize_inputs(args.run)
    except (OSError, ValidationError) as exc:
        return _fail(args.run, "finalize", exc)
    _write_final(args.run, confirmed, verdicts, args.db)
    _log_event(args.run, "finalize", True, final_sha256=_sha256(args.run / "final.json"))
    return 0


def _load_scores(run: Path) -> JudgeScores | None:
    path = run / "scores.json"
    return JudgeScores.model_validate_json(path.read_text()) if path.exists() else None


def _show(args: argparse.Namespace) -> int:
    if not _has_run(args.run):
        return 1
    final_path = args.run / "final.json"
    try:
        final = FinalAnswer.model_validate_json(final_path.read_text())
        scores = _load_scores(args.run)
    except (OSError, ValidationError) as exc:
        return _fail(args.run, "show", exc)
    sys.stdout.write(render_answer(final, scores))
    _log_event(args.run, "show", True, final_sha256=_sha256(final_path))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fc")
    sub = parser.add_subparsers(dest="command", required=True)

    schema = sub.add_parser("schema", help="print the JSON Schema of a contract")
    schema.add_argument("name", choices=sorted(SCHEMAS))
    schema.set_defaults(handler=_schema)

    fetch = sub.add_parser("fetch", help="fetch the arXiv corpus")
    fetch.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    fetch.set_defaults(handler=_fetch)

    index = sub.add_parser("index", help="build the FTS5 index from the corpus")
    index.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    index.add_argument("--db", type=Path, default=DEFAULT_DB)
    index.set_defaults(handler=_index)

    search = sub.add_parser("retrieve", help="retrieve passages for a query")
    search.add_argument("query")
    search.add_argument("--k", type=int, default=5)
    search.add_argument("--json", action="store_true")
    search.add_argument("--db", type=Path, default=DEFAULT_DB)
    search.add_argument("--run", type=Path)
    search.set_defaults(handler=_retrieve)

    validate = sub.add_parser("validate", help="validate a run file")
    validate.add_argument("run", type=Path)
    validate.add_argument("what", choices=["confirmed"])
    validate.add_argument("--model")
    validate.set_defaults(handler=_validate)

    final = sub.add_parser("finalize", help="ground the verdicts and write the final answer")
    final.add_argument("run", type=Path)
    final.add_argument("--db", type=Path, default=DEFAULT_DB)
    final.set_defaults(handler=_finalize)

    show = sub.add_parser("show", help="print the final answer of a run")
    show.add_argument("run", type=Path)
    show.set_defaults(handler=_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the fc command with argv (default sys.argv[1:]) and return its exit code."""
    args = _parser().parse_args(argv)
    return args.handler(args)
