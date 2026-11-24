# Architecture proposal: web-app-v1

Status: proposed (not approved)

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
| `run_check(run_id, store, clients)` | – | the runbook steps 5–6: verify, then `finalize`, then review, with events |

**How the verifier searches (decision V).** Code runs `retrieve` once per statement (`text + query`, k=5, per_doc=2). Then one batched Sonnet call returns the verdicts for every statement, each against its own passages, which is the spike-6b setup that passed 6/6. `queries[]` records what code ran, and `finalize` re-runs those same queries. There is no model-driven tool loop in v1, so the app makes 3 model calls per claim (decompose, verify, review), plus one for each edited statement.

### 4. HTTP API (`src/fact_checker/api/`, FastAPI, served by `uvicorn`)
| Endpoint | Does |
| --- | --- |
| `POST /api/claims {claim}` | creates a run and returns `{run_id, proposed: [Statement]}` |
| `POST /api/claims/{id}/confirm {statements, edits}` | checks falsifiability for edited and added statements; returns the `ConfirmedStatements`, or 422 with the reasons |
| `POST /api/claims/{id}/verify` | 202; starts `run_check` in a background task |
| `GET /api/claims/{id}` | status (`proposed`, `confirmed`, `verifying`, `done`, `failed`), the final answer, the scores, `needs_attention` and the events |
| `GET /api/docs?q=` and `GET /api/docs/{doc_id}` | browse and search the abstracts database |

Local only and no auth in v1 (decision L). CORS is limited to the Vite dev origin.

### 5. React app (`web/`, Vite + React + TypeScript, tested with Vitest)
- **Check page:**
  1. Enter a claim.
  2. A statements table: kind, load-bearing, `implied_by`, and drop, edit, add or flip actions.
  3. Approve.
  4. Progress while the run works.
  5. The result: the overall verdict and rule, then each statement with its verdict and its exact quotes (paper title, arXiv id, authors, date).
  6. The review scores, with a **needs attention** panel showing Sol's reasoning (D1).
- **Abstracts page:** search the database and open a paper.

## PRs into dev (modular, one commit each, `pr` review only)
| PR | Scope | Depends on |
| --- | --- | --- |
| W1 | DB schema, `fc db build`, `docs` metadata in `finalize` | – |
| W2 | LLM client layer and config (mocked tests) | – |
| W3 | Services: decompose, falsifiability, apply_edits, verify, review, run_check (FakeClient tests) | W1, W2 |
| W4 | FastAPI API and run store (TestClient tests) | W3 |
| W5 | React app (Vitest tests), a README section and a `make dev`-style script | W4 |

Each PR: the implementer writes tests and code together (no qa agent, no decomposer). The full suite must pass, plus a Codex `pr` pass with one fix round. Merged into `dev` locally with `--no-ff` under the bot's identity.

## Risks
- **No API keys yet.** Everything is built and tested with mocks. A live smoke run needs `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` in `fact-checker/.env`.
- **OpenAI model name.** Confirm that `gpt-6-sol` is the model id on the OpenAI API, not just in Codex. It's configurable either way.
- **Behaviour versus the subagent.** A batched API call isn't the subagent's tool loop. Re-run the V1–V6 seed cases through the app once keys exist, and compare.
- **Latency.** About 5–10 s to decompose, 15–30 s to verify, about 10 s to review. Hence the background task and polling in the UI.
- **Cost.** Per claim: one Opus call, one Sonnet call and one Sol call. Token usage is recorded in `events`.

## Decisions taken by default (say if you want otherwise)
- **V:** code-driven retrieval with one batched verdict call, not a tool-use loop.
- **L:** local only, no auth, no deployment.
- **E:** the eval judge (Luna, 8 dimensions) stays deferred, and the seed eval keeps running from the CLI.

## How tests change
- **Existing tests:** all 248 stay green. `finalize` tests run against the new `docs` table, built by the same fixture helper.
- **New Python tests:** the DB build, the clients (with the SDK calls mocked), the services (with `FakeClient`), and the API (with FastAPI `TestClient`).
- **New UI tests:** components tested with Vitest and React Testing Library.
