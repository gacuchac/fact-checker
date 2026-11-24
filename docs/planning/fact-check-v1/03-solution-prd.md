# 03 Solution and PRD, light POC: fact-checker / fact-check-v1

Built against architecture.md (approved, D1–D10). This is the POC cut, to be built in about 30–40 minutes. The full PRD, with the 8-dimension evals, the harness and every story, is in `history/03-solution-prd-full.md`.

## Goal
In a Claude Code session, a user states a claim about LLM research and gets back:
- a verdict: supported, contradicted or unknown;
- for each statement they confirmed, the paper title, the versioned arXiv id and a verbatim quote;
- the code rule that produced the overall verdict;
- Sol's six scores, with Sol's reasoning when it flags something (D1).

Code, not the model, decides what counts as evidence. The verdicts are grounded in 48 abstracts.

## Non-goals
These are out of scope for the POC:
- PDFs, a GUI, Docker, hosted search, deployment and world knowledge;
- the SDK entry point;
- dense retrieval;
- any automatic downgrade after a Sol flag;
- everything under "Next, after the POC".

## Flow
| # | Who | Does | Writes |
| --- | --- | --- | --- |
| 1 | Main session (Opus) | Decomposes the claim into 1–5 statements and confirms them with the user (at most 3 rounds), then runs `fc validate` | `runs/<id>/confirmed.json` |
| 2 | claim-verifier (Sonnet 5.5, high) | Runs `fc retrieve "<text> <query>" --k 5 --json --run <run>` per statement, plus up to 2 more queries; quotes evidence first, then gives a verdict | `verdicts.json` |
| 3 | fc (code) | `fc finalize`: re-retrieves, applies the N4 quote check, the conflict rule and rules 0–4 | `final.json`, `events.jsonl` |
| 4 | Sol (via `fc judge`) | Scores 6 dimensions plus `flagged[]`; code sets `needs_attention` | `scores.json` |
| 5 | Main session | Runs `fc show <run>` and pastes it verbatim. If `needs_attention`, it shows Sol's reasoning and the user decides | the answer in chat |

## Build tasks (for `/build`)

| Task | Title | Est. | Depends on | Evals |
| --- | --- | --- | --- | --- |
| fc-01 | Contracts, corpus and index, retrieve | 12 min | none | no |
| fc-02 | Quote check, finalize, `fc show`, event log | 12 min | fc-01 | no |
| fc-03 | Judge (Sol) and the runtime rubric | 5 min | fc-02 | no |
| fc-04 | Verifier prompt, runbook, seed-case scoring, smoke run | 10 min | fc-02, fc-03 | **yes** |

Unit tests cover the pure functions only (`check_quote`, the finalize rules, the aggregation, `render_answer`, contract validation). Each task's tests are written first.

### fc-01 Contracts, corpus and index, retrieve
- **Files:**
  - `pyproject.toml` (`fc` entry point, pydantic, pyyaml);
  - `src/fact_checker/{contracts,corpus,index,retrieve,cli}.py`;
  - `data/corpus.json`;
  - `.gitignore` (`runs/`, `data/index.sqlite`);
  - `tests/test_contracts.py`.
- **Done when:**
  1. Each of the 5 contracts round-trips through JSON. `Verdicts` rejects a missing id, an extra id and a quote under 5 words. `ConfirmedStatements` rejects an `implied_by` that isn't in the claim, unless the statement is `user_added`.
  2. `fc fetch` writes 48 docs, with `dropped_ids == [2307.03172v1, 2403.01432v1]`. `fc index` builds the FTS5 index: 2-sentence windows, stride 1, title in front, plus 1 metadata passage per doc.
  3. `fc retrieve "relevant information in the middle of long contexts" --json` puts `2307.03172v3` top-1, returns at most 2 hits per paper, and returns the same JSON on every run.
  4. "photosynthesis in plants" returns 0 hits with exit code 0, and FTS5 syntax characters in a query don't raise an error.
  5. `fc schema verdicts` prints `Verdicts.model_json_schema()`.
- **Reference:** the fetch and retrieval spikes are in the local, git-ignored `spikes/` folder; the spec is architecture.md and 02-chosen.md §1–2.

### fc-02 Quote check, finalize, `fc show`, event log
- **Files:**
  - `src/fact_checker/{quotes,finalize,report,cli}.py`;
  - `tests/test_quotes.py`, `tests/test_finalize.py`, `tests/test_report.py`;
  - `tests/fixtures/spike6/`.
- **Done when:**
  1. `check_quote` on the 20 spike-3 cases accepts all 11 genuine quotes and 0 of the 9 fabricated ones. It rejects ellipses and quotes under 5 words.
  2. `finalize` on the V1–V6 fixtures gives the expected verdicts 6/6, with V4 `unknown` (`conflict`). A fabricated quote, or one taken from another statement's passages, is dropped, and `supported` becomes `unknown` (`quote_failed`).
  3. Rules 0–4 pass their truth table. Rule 0: no load-bearing statement gives `unknown` (D9).
  4. `render_answer` is deterministic on fixtures, and renders a missing `scores.json` as "not judged".
  5. `validate`, `retrieve --run`, `finalize` and `show` each append one line to `<run>/events.jsonl`. The `final_sha256` in that line matches the file on disk.

### fc-03 Judge (Sol) and the runtime rubric
- **Files:**
  - `src/fact_checker/judge.py`, `cli.py`;
  - `.claude/review-passes/judge.md` (D3; the text is in `history/03-solution-prd-full.md` §7);
  - `tests/test_judge.py`.
- **Done when:**
  1. With the subprocess mocked, a canned Sol output, including the saved `<!-- pass -->` header, parses into `JudgeScores`.
  2. `needs_attention` is true exactly when `flagged` is non-empty, or when any of `statement_verdicts`, `overreach` or `evidence_relevance` is 2 or less.
  3. A score outside 1–5, an unknown dimension or an unknown statement id gives exit 1 and no `scores.json`.
  4. Codex runs with cwd = the project root and `--model gpt-6-sol`, and the event line carries `final_sha256`.

### fc-04 Verifier prompt, runbook, seed-case scoring, smoke run
- **Files:**
  - `agents/claim-verifier.md`, `docs/RUNBOOK.md`;
  - `src/fact_checker/evals.py`, `cli.py` (`eval prepare|score`);
  - `tests/test_prompts.py`, `tests/test_evals.py`.
- **Done when:**
  1. `test_prompts.py` asserts that `claim-verifier.md` embeds `fc schema verdicts` and that `RUNBOOK.md` embeds `fc schema confirmed`.
  2. The runbook preflight passes: `codex login status`, then one `fc judge` on the V4 fixture.
  3. Smoke run, recorded in the PR: the full flow on 3 claims, using spike 6a's D1, D2 and D5. Expected results:
     - D2 ends `contradicted` (rule 2), with the +30% statement `supported`;
     - D5 ends `unknown`;
     - every quote passes N4, and `fc show` matches `final.json`.
  4. `fc eval prepare evals/cases <dir>` writes one `confirmed.json` per seed case (`source: case`). `fc eval score` reports accuracy, the quote pass rate and recall of `gold_doc_ids`.

**Prompts:**
- **Decomposition (runbook):** spike 6a's prompt (`spike-assets/llm/decompose_prompt.md`) with the spike-6 tightening:
  - a framing bias only when the loaded word appears in the claim;
  - no statement entailed by another;
  - 1–3 statements preferred, with a cap of 5;
  - `kind` is for display only.
- **Verdict prompt and tool steps (`claim-verifier.md`):** spike 6b's prompt (`spike-assets/llm/verify_cases.md`) plus the tool steps.
- The full text of both is in `history/03-solution-prd-full.md` §6.

## Evals for the POC (D6, D8)
- **Cases:** the 6 seed cases, V1–V6 from spike 6, as `evals/cases/V*.yaml` in `statements` mode. Each carries the approved statements, gold verdicts and `gold_doc_ids`. They are written with the user in parallel with the build (D6) and block no task.
- **Scoring:** code only: accuracy, the quote pass rate, and recall of the gold docs.
- **Evals flag:** yes, for fc-04, which ships the prompts, using these seed cases.

## Next, after the POC (deferred, not dropped; details in `history/03-solution-prd-full.md`)
- The 8 D7 dimensions as code checks plus an eval judge (§8.3).
- Expand to 24–30 cases with the planned case mix (§8.2, D8).
- The eval harness over headless `claude -p --resume`, with eval-runner as the user (D10 3a). The `claude` CLI must first be installed or linked: only the VS Code extension's copy exists on this machine.
- The eval rubric at `evals/judge/.claude/review-passes/judge.md`, on GPT-6 Luna (D10 4a).
- Sol calibration against hand scores (US-11).

## Interview answers, as built
1. **Choosing documents:**
   - each confirmed statement gets its own BM25 search over SQLite FTS5 2-sentence passages: top 5, at most 2 per paper, plus up to 2 reworded queries;
   - in the spikes, the gold paper was in the top 5 for 9 of 9 statements;
   - FTS5 is an inverted index on disk, so cost per claim doesn't grow with the corpus, and dense retrieval can sit behind the same `retrieve`.
2. **Not making things up:**
   - the model quotes evidence before it gives a verdict;
   - `fc finalize` re-runs the retrieval itself and keeps only N4-verbatim quotes of 5 or more words from that statement's own passages (11/11 genuine kept, 0/9 fabricated);
   - no hits, failed quotes or a cross-paper conflict make a statement `unknown`, and code can only move a verdict toward `unknown`.
3. **Knowing the verdicts are right:**
   - labelled cases with gold verdicts and gold papers, scored by code;
   - Sol reviews every answer, and its flags go to the user;
   - the 8-dimension, simulated-user eval comes next.

## Top risks
- `fc judge` (Codex: network and sign-in) may be blocked inside the subagent's Bash. The preflight in fc-04 tests this. If it fails, the answer shows "not judged".
- Opus decomposition and the tightened prompt haven't been run yet, since spike 6a ran on Sonnet. The smoke run is the first check.
- Whether the subagent's effort can be set to high on each call is unverified. The model is recorded in `events.jsonl`.
- The conflict rule may fire on papers with different setups (V4). Accuracy beyond the 6 seed cases is unmeasured.

## Still open
- Where the model is recorded. `FinalAnswer` has no `model` field, so it goes in `events.jsonl` for now. Moving it into `final.json` would be a contract change.
- The eval targets (for example, 80% accuracy and no `supported` on a false claim) are proposed and not yet confirmed.
