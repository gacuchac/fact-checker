"""Run one claim-mode eval case through the web session services against a temporary database."""

import json
import re
from importlib.resources import files
from pathlib import Path

from fact_checker.api.app import Clients
from fact_checker.contracts import Edit
from fact_checker.corpus import Corpus, Doc, load_corpus
from fact_checker.evals import ClaimOutcome
from fact_checker.index import build_index
from fact_checker.llm.base import LLMError
from fact_checker.llm.config import Settings
from fact_checker.services.session import confirm_claim, start_claim, verify_claim
from fact_checker.store import get_run, list_spans


def _extra_docs(path: Path) -> list[Doc]:
    docs = json.loads(path.read_text(encoding="utf-8"))["docs"]
    return [Doc.model_validate({**d, "abstract": re.sub(r"\s+", " ", d["abstract"]).strip()}) for d in docs]


def _corpus_for(case: dict, root: Path) -> Corpus:
    corpus = load_corpus(root / "data" / "corpus.json")
    extra = case["factcheck"].get("extra_docs")
    if extra:
        corpus = corpus.model_copy(update={"docs": [*corpus.docs, *_extra_docs(root / extra)]})
    return corpus


def _prompts() -> dict[str, str]:
    folder = files("fact_checker.services") / "prompts"
    return {p.name: p.read_text(encoding="utf-8") for p in folder.iterdir() if p.name.endswith(".md")}


def _drive(
    case: dict, db: Path, clients: Clients, settings: Settings
) -> tuple[str | None, list[dict] | None, str | None]:
    """Return the run id, the confirm issues and the error of a run driven as far as the case goes."""
    factcheck = case["factcheck"]
    run_id = None
    try:
        run_id, _ = start_claim(db, factcheck["claim"], clients.decompose, settings)
        edits = [Edit.model_validate(e) for e in factcheck.get("edits", [])]
        confirmed = confirm_claim(db, run_id, edits, clients.check, settings)
        if isinstance(confirmed, list):
            return run_id, [i.model_dump() for i in confirmed], None
        verify_claim(db, run_id, clients.verify, clients.review, settings)
    except LLMError as error:
        return run_id, None, str(error)
    return run_id, None, None


def run_claim_case(
    case: dict, root: Path, clients: Clients, settings: Settings, secrets: list[str], work: Path
) -> ClaimOutcome:
    """Run a claim-mode case and return what it left behind, ready to score.

    Builds work/db.sqlite from root/data/corpus.json plus the docs of root/<extra_docs> when the case names
    it; the corpus file is only read. Runs start_claim, then confirm_claim with the case's edits, then
    verify_claim when confirmed. An LLMError ends the run and is recorded as the outcome's error.
    """
    corpus = _corpus_for(case, root)
    db = work / "db.sqlite"
    build_index(corpus, db)
    run_id, rejected, error = _drive(case, db, clients, settings)
    run = get_run(db, run_id) if run_id else None
    spans = [s.model_dump(mode="json") for s in list_spans(db, run_id)] if run_id else []
    return ClaimOutcome(
        rejected=rejected,
        result=run.result if run else None,
        error=error or (run.error if run else None),
        spans=spans,
        abstracts={d.doc_id: d.abstract for d in corpus.docs},
        prompts=_prompts(),
        secrets=secrets,
    )
