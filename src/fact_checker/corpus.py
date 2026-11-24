"""The arXiv corpus: which papers, how to fetch them and how to store them."""

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

ARXIV_IDS: tuple[str, ...] = (
    "2309.01431v2", "2401.15884v3", "2504.19754v1", "2412.15246v1", "2508.15253v2",
    "2601.11863v1", "2407.01102v1", "2501.00332v1", "2406.13692v2", "2411.09213v1",
    "2402.13178v2", "2602.18734v2", "2406.05804v6", "2401.07324v3", "2602.20867v1",
    "2603.22386v1", "2603.13404v1", "2602.20426v1", "2509.25370v1", "2601.06112v1",
    "2406.12276v1", "2603.19896v1", "2305.01937v1", "2308.01862v1", "2404.13076v1",
    "2310.05657v1", "2406.00936v1", "2412.00543v1", "2406.04244v1", "2502.07445v2",
    "2403.01432v5", "2312.05934v3", "2604.23801v1", "2407.04528v4", "2501.04652v2",
    "2510.01600v2", "2402.11035v3", "2408.02152v3", "2307.03172v3", "2406.16008v2",
    "2310.03025v2", "2411.03538v1", "2310.01427v1", "2401.18058v1", "2406.02818v1",
    "2503.17407v2", "2412.16926v3", "2601.22548v3", "2307.03172v1", "2403.01432v1",
)  # fmt: skip
ATOM = {"a": "http://www.w3.org/2005/Atom"}
API_URL = "https://export.arxiv.org/api/query"
USER_AGENT = "fact-checker/0.1"
RETRY_PAUSE_SECONDS = 3.5


class Doc(BaseModel):
    """One arXiv paper's metadata and abstract."""

    doc_id: str
    base_id: str
    title: str
    authors: list[str]
    published: str
    updated: str
    abstract: str


class Corpus(BaseModel):
    """The kept papers, the superseded ids that were dropped, and when they were fetched."""

    kept_ids: list[str]
    dropped_ids: list[str]
    fetched_at: str
    docs: list[Doc]


def _split_id(doc_id: str) -> tuple[str, int]:
    base, version = doc_id.rsplit("v", 1)
    return base, int(version)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def keep_latest(ids: Sequence[str]) -> tuple[list[str], list[str]]:
    """Return (kept, dropped): the latest listed version of each paper, both in listed order."""
    latest: dict[str, int] = {}
    for doc_id in ids:
        base, version = _split_id(doc_id)
        latest[base] = max(latest.get(base, version), version)
    kept = list(dict.fromkeys(i for i in ids if _split_id(i)[1] == latest[_split_id(i)[0]]))
    return kept, [i for i in ids if i not in kept]


def parse_feed(xml: bytes) -> list[Doc]:
    """Parse an arXiv Atom feed into docs, in feed order."""
    docs = []
    for entry in ET.fromstring(xml).findall("a:entry", ATOM):
        doc_id = entry.findtext("a:id", namespaces=ATOM, default="").rsplit("/abs/", 1)[1]
        docs.append(
            Doc(
                doc_id=doc_id,
                base_id=_split_id(doc_id)[0],
                title=_collapse(entry.findtext("a:title", namespaces=ATOM, default="")),
                authors=[a.findtext("a:name", namespaces=ATOM, default="") for a in entry.findall("a:author", ATOM)],
                published=entry.findtext("a:published", namespaces=ATOM, default=""),
                updated=entry.findtext("a:updated", namespaces=ATOM, default=""),
                abstract=_collapse(entry.findtext("a:summary", namespaces=ATOM, default="")),
            )
        )
    return docs


def build_corpus(ids: Sequence[str], xml: bytes, fetched_at: str) -> Corpus:
    """Build a Corpus of the latest version of each id from a feed; raise ValueError naming missing ids."""
    kept, dropped = keep_latest(ids)
    by_id = {d.doc_id: d for d in parse_feed(xml)}
    missing = [i for i in kept if i not in by_id]
    if missing:
        raise ValueError(f"missing from feed: {', '.join(missing)}")
    return Corpus(kept_ids=kept, dropped_ids=dropped, fetched_at=fetched_at, docs=[by_id[i] for i in kept])


def fetch_feed(kept: Sequence[str], attempts: int = 4) -> bytes:
    """Fetch the Atom feed for the ids in one request; raise RuntimeError after the last failed attempt."""
    query = urllib.parse.urlencode({"id_list": ",".join(kept), "max_results": len(kept)})
    request = urllib.request.Request(f"{API_URL}?{query}", headers={"User-Agent": USER_AGENT})
    error: Exception | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(RETRY_PAUSE_SECONDS)
        try:
            body = urllib.request.urlopen(request, timeout=60).read()
            entries = ET.fromstring(body).findall("a:entry", ATOM)
        except (OSError, ET.ParseError) as exc:
            error = exc
            continue
        if len(entries) == len(kept):
            return body
        error = RuntimeError("feed has the wrong number of entries")
    raise RuntimeError(f"fetch failed after {attempts} attempts: {error}")


def load_corpus(path: Path) -> Corpus:
    """Read a Corpus from a JSON file."""
    return Corpus.model_validate_json(path.read_text(encoding="utf-8"))


def save_corpus(corpus: Corpus, path: Path) -> None:
    """Write a Corpus to a JSON file, creating the parent folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(corpus.model_dump_json(indent=1), encoding="utf-8")
