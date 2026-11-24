# fact-checker

Checks claims about LLM research against a fixed corpus of 48 arXiv abstracts. For each claim it returns a verdict (**supported**, **contradicted** or **unknown**) and, for every part of the claim, the evidence: the paper's title, authors, date and an exact quote from its abstract.

It is a proof of concept, built for a time-boxed exercise. The design favours answers you can audit over answers that sound confident. When the abstracts don't settle a claim, the answer is `unknown`.

## How it works

```
you ⇄ Claude Code session (Opus)        1. breaks the claim into falsifiable statements
        │                                2. you confirm, edit, drop or add statements
        ▼  runs/<id>/confirmed.json
     claim-verifier subagent (Sonnet)   3. searches for each statement (fc retrieve)
        │                                4. writes verdicts with exact quotes
        ▼  runs/<id>/verdicts.json
     fc finalize  (plain Python)        5. re-runs the searches, keeps only quotes that are word for word
        │                                   in that statement's own passages, applies the conflict rule
        ▼  runs/<id>/final.json             and combines the verdicts
     fc judge     (GPT-6 Sol via Codex) 6. an independent reviewer scores the answer on six dimensions
        ▼  runs/<id>/scores.json
     fc show                            7. prints the answer, the evidence and the review
```

The `fc` command makes **no model calls**. Everything that decides what counts as evidence is deterministic code with unit tests: search, quote checking, the conflict rule, combining verdicts, and checking the review's format. Models only propose. Code can move a verdict towards `unknown`, never towards `supported`.

### The three design questions

1. **Choosing documents.** Each confirmed statement gets its own keyword search (BM25 over SQLite FTS5) across overlapping 2-sentence passages. It takes the top 5 passages, at most 2 per paper, and the verifier may run up to 2 reworded searches. The index is an inverted index on disk, so the cost per claim stays flat as the corpus grows, and embedding search could be added behind the same `retrieve` function.
2. **Not making things up.**
   - The verifier must quote before it gives a verdict.
   - `fc finalize` re-runs each search itself and drops any quote that is not an exact span of 5 or more words, after normalising spacing, punctuation and LaTeX, from a passage that statement's own search returned. In the spike this kept 11 of 11 genuine quotes and rejected 9 of 9 made-up ones.
   - No hits, no surviving quote, or two papers disagreeing all give `unknown`.
3. **Knowing the verdicts are right.**
   - Labelled cases with gold verdicts and gold papers are scored by code (`fc eval`).
   - An independent model, GPT-6 Sol, reviews every answer against a rubric. When it flags a problem, its reasoning goes back to the person. It never silently changes a verdict.

## Setup

Requires Python 3.12. The models only run inside a Claude Code session (see below); the `fc` command itself needs no API key.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # installs the fc package in editable mode, plus pytest
.venv/bin/fc db build                            # builds data/factcheck.sqlite from the committed data/corpus.json
.venv/bin/python -m pytest -q                   # 247 tests, no network needed
```

`data/corpus.json` is committed: 48 abstracts, keeping only the latest listed version where a paper appeared twice. To fetch it again from the arXiv API, run `.venv/bin/fc fetch`.

## Using it

### Check a claim (full flow)

Open Claude Code in this folder and ask it to follow [docs/RUNBOOK.md](docs/RUNBOOK.md) for your claim. The session:
- breaks the claim down and asks you to confirm the statements;
- runs the claim-verifier ([agents/claim-verifier.md](agents/claim-verifier.md)) as a Sonnet subagent;
- prints the result with `fc show`.

The reviewer step needs the [Codex CLI](https://github.com/openai/codex), signed in (`codex login status`), and the workspace script `codex_review.py`. Its path is set by `FC_CODEX_REVIEW`, and the model by `FC_JUDGE_MODEL`, which defaults to `gpt-6-sol`.

### The `fc` commands

| Command | What it does |
| --- | --- |
| `fc fetch` / `fc db build` | fetch the corpus from arXiv / build the abstracts database and search index (`fc index` is an alias) |
| `fc retrieve "<query>" --k 5 --json [--run <run>]` | search; with `--run`, the returned papers are logged to the run |
| `fc validate <run> confirmed` | check `confirmed.json` against its contract |
| `fc finalize <run>` | check the quotes, apply the rules, write `final.json` |
| `fc judge <run>` | run Sol's review and write `scores.json` |
| `fc show <run>` | print the answer |
| `fc schema <confirmed\|retrieval\|verdicts\|final\|scores>` | print a contract's JSON Schema |
| `fc eval prepare evals/cases <dir>` / `fc eval score evals/cases <dir>` | set up the seed eval cases / score them |

Every command run against a run folder appends a line to `<run>/events.jsonl` with a timestamp, the papers returned, and a hash of the `final.json` it read. That shows the steps ran in order, and that what was displayed is what was reviewed.

### Example output

```
Claim: LongAlign improves long-context performance by up to 30% but hurts performance on short, generic tasks.
Overall: contradicted (rule 2)

[1] supported | load-bearing | confirmed
  LongAlign improves performance on long-context tasks by up to 30%.
  supports: "LongAlign outperforms existing recipes for LLMs in long context tasks by up to 30\%" - LongAlign: A Recipe
  for Long Context Alignment of Large Language Models (2401.18058v1, 2024-01-31; Yushi Bai et al.)
[2] contradicted | load-bearing | confirmed
  Training with LongAlign lowers performance on short, generic tasks.
  contradicts: "while also maintaining their proficiency in handling short, generic tasks" - LongAlign: ... (2401.18058v1)
```

## Web app

There is a web version that calls the models directly. You approve the statements in the browser, and every step of a run is recorded so you can inspect it.

| Step | Who does it |
| --- | --- |
| Break the claim into falsifiable statements | Claude Opus 5.5 (Anthropic API) |
| Review, edit and approve the statements | you, in the browser (statements you edit or add get a falsifiability check from Opus) |
| Search each statement, then give verdicts with exact quotes | code (BM25 over SQLite FTS5), then Claude Sonnet 5.5 at high effort |
| Check every quote and combine the verdicts | code (`finalize`): only exact quotes from that statement's own passages survive |
| Review the answer against the rubric | GPT-6 Sol (OpenAI API) |
| If the reviewer flags problems, revise once | Sonnet revises using the reviewer's reasoning, code re-checks it, and Sol reviews again |
| The final message | rendered by code from the checked answer |

**Traces.** Every run is a trace in the `spans` table of `data/factcheck.sqlite`:
- your claim, edits and approval;
- every model call, with the full system prompt, the user message, the raw output, model, tokens and latency, including Sol's review and Claude's revision;
- every search, with its passages;
- `finalize`, with its quote checks;
- the final message.

The **Traces** page shows each run as a timeline you can expand. The **Abstracts** page lets you browse and search the 48 papers.

### Run it locally
```bash
cp .env.example .env            # add ANTHROPIC_API_KEY and OPENAI_API_KEY
.venv/bin/pip install -r requirements-dev.txt
(cd web && npm ci && npm run build)
.venv/bin/fc serve --port 8000  # serves the API and the built app at http://127.0.0.1:8000
```
For frontend development, run `npm run dev` in `web/` (on port 5173, with `/api` proxied to port 8000).

Settings are environment variables (see `.env.example`):
- the models and effort levels;
- `FC_ACCESS_CODE`: when set, the app asks for it;
- `FC_DAILY_RUN_CAP`: how many claims can be verified per day;
- `FC_DB`, `FC_WEB_DIST` and `FC_CORPUS`: file paths.

### Deployment
One Railway service runs `uvicorn` with `fact_checker.api.app:create_app_from_env`. It serves both the API and the built React app. Railway no longer lets new services use `railway.json`, so the build and start settings live on the service:

| Setting | Value |
| --- | --- |
| Builder | Railpack (Python from `pyproject.toml`), with `RAILPACK_PACKAGES=node@22` for the web build |
| Build command | `cd web && npm ci && npm run build` |
| Start command | `uvicorn --factory fact_checker.api.app:create_app_from_env --host 0.0.0.0 --port $PORT` |
| Healthcheck | `/api/health` |
| Variables | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `FC_ACCESS_CODE`, `FC_DAILY_RUN_CAP`, the model names, `FC_DB=/data/factcheck.sqlite`, `FC_WEB_DIST=/app/web/dist`, `FC_CORPUS=/app/data/corpus.json` |

- **Database:** on a Railway volume at `/data`, so runs and traces survive redeploys.
- **Secrets:** the API keys and the access code are Railway variables; nothing secret is in the repo.

### Browser test
`e2e/flow.mjs` drives the deployed (or local) app in headless Chrome with Playwright. It takes a screenshot at every step: claim, access code, statements, verifying, result, review, trace timeline, each span type, traces list and abstracts.
```bash
cd e2e && npm install
BASE_URL=https://<app> ACCESS_CODE=<code> OUT_DIR=shots node flow.mjs
```

## Results so far

From [docs/planning/fact-check-v1/smoke-run-fc-04.md](docs/planning/fact-check-v1/smoke-run-fc-04.md):

- **Smoke run.** Three claims gave the expected verdicts: one supported, one contradicted, and one outside the corpus that came back `unknown` with no invented evidence. Every quote was exact.
- **Seed eval (6 cases).** Code scoring gave 6/6 verdicts correct, a 100% quote pass rate, and every gold paper found. **But the reviewer flagged overreach on 2 of the 6.** In both, the gold label we wrote accepted a hedged quote ("often highest") or an unstated scope ("this benchmark") as proof. So the gold labels themselves need review, and 6 self-written cases are a smoke test, not a measure of accuracy.

## Known limits

- **Small eval.** It has 6 cases. The plan is 24–30, scored on 8 dimensions with a simulated user.
- **No standalone API path yet.** The models run inside a Claude Code session. A web app calling the Claude and OpenAI APIs directly is the next step; the contracts and `fc` stay as they are.
- **The reviewer depends on the author's workspace.** `fc judge` calls `codex_review.py` from the author's agentic workspace (default `~/Developing/scripts/codex_review.py`; override with `FC_CODEX_REVIEW`). Search, finalize, eval scoring and the tests run anywhere.
- **Keyword search only.** Paraphrased claims depend on the verifier's reworded searches.
- **Review follow-ups.** Open items from code review are listed in the planning notes.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/fact_checker/` | contracts, corpus, index, retrieve, quotes, finalize, report, judge, evals, CLI |
| `agents/claim-verifier.md` | the verifier's prompt |
| `docs/RUNBOOK.md` | the session's procedure, including the decomposition prompt |
| `.claude/review-passes/judge.md` | the reviewer's rubric |
| `evals/cases/` | seed eval cases |
| `docs/planning/fact-check-v1/` | the plan: scope and options, spike results, decisions, architecture, PRD |
| `tests/` | unit and integration tests |
