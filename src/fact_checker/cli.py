"""The fc command line: a thin layer over the library functions."""

import argparse
import json
import sys
import time
from pathlib import Path

from fact_checker import corpus
from fact_checker.contracts import SCHEMAS
from fact_checker.index import build_index
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


def _retrieve(args: argparse.Namespace) -> int:
    try:
        result = retrieve(args.db, args.query, k=args.k)
    except FileNotFoundError:
        print("index not found: run fc index", file=sys.stderr)
        return 1
    if args.json:
        print(result.model_dump_json())
    else:
        for rank, hit in enumerate(result.hits, 1):
            print(f"{rank} {hit.score:.2f} {hit.doc_id} {hit.title}")
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
    search.set_defaults(handler=_retrieve)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the fc command with argv (default sys.argv[1:]) and return its exit code."""
    args = _parser().parse_args(argv)
    return args.handler(args)
