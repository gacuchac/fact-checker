# Architecture: web-app-v1

Status: approved (2026-11-24; user: "let's use railways", deployment on Railway with an access code; amended the same day at the user's request: full tracing, a revision step after the review, and autonomous build and deployment; amended again after a live false unknown, user: "fix it and test it": a claim search per statement and a code consistency check that can trigger the revision)

Goal: a light local web app. You type a claim, review and approve the statements in the browser, and get the verdict with exact quotes and the review. The app calls the models directly: the **Claude API** for decomposition and verdicts, and the **OpenAI API** for the Sol review. The abstracts live in a SQLite database. Claude Code subagents are no longer part of the flow.

## What stays as it is
- The five contracts in `contracts.py` (`ConfirmedStatements`, `RetrievalResult`, `Verdicts`, `FinalAnswer`, `JudgeScores`), unchanged.
- `retrieve(db, query, k, per_doc)`, `check_quote`, `finalize(confirmed, verdicts, db)`, `render_answer`, `parse_scores`: same signatures and the same rules (rule N4, the conflict rule, rules 0–4).
- The `fc` CLI and the Claude Code runbook flow. They keep working side by side with the app.

## What changes

### 1. Database (`data/factcheck.sqlite`, built by `fc db build`)
| Table | Columns | Replaces |
| --- | --- | --- |
| `docs` | `doc_id` PK, `base_id`, `title`, `authors` (JSON), `published`, `abstract` | parsing authors and date out of the `#meta` passage text |
| `passages` (FTS5) | as today: `passage_id`, `doc_id`, `base_id`, `text` | (same) `data/index.sqlite`, which now becomes this file |
| `runs` | `id`, `claim`, `status`, `created_at`, `proposed`, `confirmed`, `verdicts`, `final`, `scores`, `error` (the JSON columns validated by the contracts) | the run folder, for app runs only |
| `events` | `run_id`, `ts`, `step`, `ok`, `payload` (JSON: doc_ids, final_sha256, model, tokens, seconds) | `events.jsonl`, for app runs only |

- **Internal change, no contract change:** `finalize` reads paper metadata from `docs` instead of calling the private `_meta_passage`. The only caller is `finalize.py:99`.
- `fc index` stays as an alias that builds the same database. `--db` defaults to the new file.

### 2. LLM client layer (`src/fact_checker/llm/`)
- **`LLMClient` protocol:** `complete(system: str, user: str, schema: type[BaseModel], model: str, effort: str | None) -> tuple[BaseModel, Usage]`.
- **`ClaudeClient`** (`anthropic` SDK):
  - Structured output through `output_config.format`, with effort in `output_config`.
  - Adaptive thinking (no `thinking` param), no forced `tool_choice`.
  - Server-side `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`).
  - `stop_reason == "refusal"` raises `LLMRefusal`.
- **`OpenAIClient`** (`openai` SDK): structured outputs with a JSON schema.
- **Config:** `.env` with `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`, plus the model names:
  - `FC_DECOMPOSE_MODEL` (default `claude-opus-5-5`);
  - `FC_VERIFY_MODEL` (default `claude-sonnet-5-5`, effort `high`);
  - `FC_REVIEW_MODEL` (default `gpt-6-sol`).
- **Tests** use a `FakeClient`. Nothing in CI calls a network.

### 3. Services (`src/fact_checker/services/`): pure orchestration over the client and the existing functions
| Function | Model | Replaces |
| --- | --- | --- |
| `decompose(claim, client) -> list[Statement]` | Opus 5.5 | the main session following the runbook prompt (same prompt text, moved to `prompts/decompose.md`) |
| `check_falsifiable(statement, client) -> Falsifiability` | Opus 5.5 | the main session's falsifiability check on statements you edit |
| `apply_edits(proposed, edits) -> ConfirmedStatements` (pure) | – | the chat confirmation loop |
| `verify(confirmed, db, client) -> Verdicts` | Sonnet 5.5, effort high | the claim-verifier subagent |
| `review(final, run_text, client) -> JudgeScores` | GPT-6 Sol | `fc judge` going through Codex (the rubric text is reused and parsed with `parse_scores`) |
| `revise(confirmed, verdicts, final, results, scores, client)` | Sonnet 5.5, effort high | (new) Claude revises its verdicts from Sol's flags and reasoning, using the same passages |
| `run_check(confirmed, db, clients, settings, tracer)` | – | verify, then `finalize`, the code consistency check, then review. If `needs_attention` or a code flag, one revision round: revise, `finalize`, review again. Then the final message |

**How the verifier searches (decision V).** Code runs `retrieve` twice per statement, once for `text + query` and once for the user's own claim (k=5, per_doc=2 each), and gives the statement the union of the passages; the claim search was added after a live run where a reworded statement missed the abstract's key sentence. Then one batched Sonnet call returns the verdicts for every statement, each against its own passages, which is the spike-6b setup that passed 6/6. `queries[]` records what code ran, and `finalize` re-runs those same queries. There is no model-driven tool loop in v1, so the app makes 3 model calls per claim (decompose, verify, review), plus one for each edited statement.

### 3b. Tracing and the revision step (user decision, 2026-11-24)
**What is traced.** Every step of a run is a span in the `spans` table of `data/factcheck.sqlite`: `id`, `run_id`, `parent_id`, `seq`, `kind`, `name`, `started_at`, `ended_at`, `status`, `model`, `input` (JSON), `output` (JSON), `usage` (JSON) and `error`. `kind` is one of `user`, `llm`, `tool`, `code` and `system`. One run is one trace.

**The spans, in order:**
- `user`: the claim; the statement edits and approval.
- `llm`: decompose, each falsifiability check, verify, review (Sol), revise, and the second review. Each stores the full system prompt, the user message, the schema name, model, effort, the raw output text, the parsed output, the tokens, the latency, and the model that actually served it.
- `tool`: every `retrieve` call, with the query, k, per_doc and every passage returned.
- `code`: `finalize`, with the quote checks, the dropped quotes, the downgrades and the rule that fired; `consistency`, with the code flags of the first answer.
- `system`: the final message sent to the user.

**How it's recorded.**
- A `Tracer` (`src/fact_checker/tracing.py`) writes spans through a `SpanStore`.
- A `TracingClient` wraps any `LLMClient` and records each call. The `retrieve` and `finalize` calls in the services are wrapped the same way.
- The services take the tracer as a parameter: no hidden state, and tests use an in-memory store.

**The revision step.** This replaces D1's "flags never change a verdict" for the app.
- **Code consistency check** (`one_sided_unknowns`, after the first `finalize`): a statement the model left `unknown`, with no downgrade by code, whose kept quotes all take one stance gets an `unknown_calibration` flag that says so. The flags are kept in the result as `consistency_flags`.
- When Sol's review sets `needs_attention`, or the code check raised a flag (and the review itself succeeded), `revise` gives Sonnet the confirmed statements, its earlier verdicts, the same passages, and Sol's scores, evidence and flags plus the code flags. Sonnet returns new `Verdicts`.
- `finalize` then re-checks every quote and re-applies the rules, so code still has the final say.
- Sol reviews once more. That is one round at most.
- Both versions are kept in the run and the trace, and the UI shows that the answer was revised and why.

**The final message.** It is rendered by code (`render_answer`) from the last checked `FinalAnswer` and review, plus a line saying whether it was revised. No model writes free text that could stray from the checked quotes. It is stored as the `final_message` span.

**Why our own tables and not Langfuse or MLflow.** Langfuse self-hosting needs Docker, Postgres and ClickHouse (and the exercise rules out Docker). Langfuse Cloud adds an account, more keys, and a third party that receives every prompt and abstract. MLflow needs a second hosted service with its own storage. A table in the database we already ship needs neither. The span fields follow the OpenTelemetry and Langfuse model, so an exporter could be added later without changing the services.

### 4. HTTP API (`src/fact_checker/api/`, FastAPI, served by `uvicorn`)
| Endpoint | Does |
| --- | --- |
| `POST /api/claims {claim}` | creates a run and returns `{run_id, proposed: [Statement]}` |
| `POST /api/claims/{id}/confirm {statements, edits}` | checks falsifiability for edited and added statements; returns the `ConfirmedStatements`, or 422 with the reasons |
| `POST /api/claims/{id}/verify` | 202; starts `run_check` in a background task |
| `GET /api/claims/{id}` | status (`proposed`, `confirmed`, `verifying`, `done`, `failed`), the final answer, the scores, `needs_attention` and the events |
| `GET /api/docs?q=` and `GET /api/docs/{doc_id}` | browse and search the abstracts database |
| `GET /api/runs` and `GET /api/runs/{id}/trace` | list the runs; return one run's spans in order, for the traces page |

No user accounts. Every `/api/*` route except `/api/health` requires the header `X-Access-Code`, which must equal env `FC_ACCESS_CODE`. If `FC_ACCESS_CODE` is unset, the check is off, which suits local development. A per-IP rate limit and env `FC_DAILY_RUN_CAP` (the number of claims verified per day) protect the API credit. In production, FastAPI serves the built React app from `web/dist` on the same origin. CORS is allowed only for the Vite dev origin.

### 5. React app (`web/`, Vite + React + TypeScript, tested with Vitest)
- **Check page:**
  1. Enter a claim.
  2. A statements table: kind, load-bearing, `implied_by`, and drop, edit, add or flip actions.
  3. Approve.
  4. Progress while the run works.
  5. The result: the overall verdict and rule, then each statement with its verdict and its exact quotes (paper title, arXiv id, authors, date).
  6. The review scores, with a **needs attention** panel showing Sol's reasoning and, when the answer was revised, the first and the revised verdicts side by side.
- **Traces page:** the list of runs. Each run opens a timeline of its spans (kind, name, model, latency, tokens), and every span expands to show its full input and output.
- **Abstracts page:** search the database and open a paper.

## PRs into dev (modular, one commit each, `pr` review only)
| PR | Scope | Depends on |
| --- | --- | --- |
| W1 | DB schema, `fc db build`, `docs` metadata in `finalize` | – |
| W2 | LLM client layer and config (mocked tests) | – |
| W3 | Services: decompose, falsifiability, apply_edits, verify, review, run_check (FakeClient tests) | W1, W2 |
| W4 | Tracing (`spans` table, `Tracer`, `TracingClient`), the `runs` store, `revise` and the revision round in `run_check`, and the final message | W3 |
| W5 | FastAPI API: claims, confirm, verify, runs and trace, docs; access code, rate limit, daily cap (TestClient tests) | W4 |
| W6 | React app (Vitest tests): the check flow, the traces page, the abstracts page, an access-code prompt | W5 |
| W7 | Railway deploy (`railway.json`: install, `npm ci && npm run build`, `fc db build`, `uvicorn`), `/api/health`, then deploy and a Playwright end-to-end run against the live URL with a screenshot of every step | W6 |

Each PR: the implementer writes tests and code together (no qa agent, no decomposer). The full suite must pass, plus a Codex `pr` pass with one fix round. Merged into `dev` locally with `--no-ff` under the bot's identity.

## Risks
- **No API keys yet.** Everything is built and tested with mocks. A live smoke run needs `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` in `fact-checker/.env`.
- **OpenAI model name.** Confirm that `gpt-6-sol` is the model id on the OpenAI API, not just in Codex. It's configurable either way.
- **Behaviour versus the subagent.** A batched API call isn't the subagent's tool loop. Re-run the V1–V6 seed cases through the app once keys exist, and compare.
- **Latency.** About 5–10 s to decompose, 15–30 s to verify, about 10 s to review. Hence the background task and polling in the UI.
- **Cost.** Per claim: one Opus call, one Sonnet call and one Sol call. Token usage is recorded in `events`.

## Decisions taken by default (say if you want otherwise)
- **V:** code-driven retrieval with one batched verdict call, not a tool-use loop.
- **L:** deployed as one Railway service (Python and Node builds, no Dockerfile). No user accounts; a shared access code, a rate limit and a daily cap instead. The keys are Railway variables in production and in `.env` locally, which git ignores.
- **E:** the eval judge (Luna, 8 dimensions) stays deferred, and the seed eval keeps running from the CLI.

## How tests change
- **Existing tests:** all 248 stay green. `finalize` tests run against the new `docs` table, built by the same fixture helper.
- **New Python tests:** the DB build, the clients (with the SDK calls mocked), the services (with `FakeClient`), and the API (with FastAPI `TestClient`).
- **New UI tests:** components tested with Vitest and React Testing Library.
