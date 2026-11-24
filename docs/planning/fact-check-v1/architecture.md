# Architecture: fact-check-v1

Status: approved

Source: 02-chosen.md and 03-decisions.md (D1–D10). No code exists yet, so there are no callers to migrate. Earlier revisions are in `history/`.

## Components and who calls whom

```
user ⇄ main session (Opus)                     decomposes the claim and confirms it with the user (D4)
        │ writes confirmed.json; fc validate <run> confirmed
        ▼
     claim-verifier subagent (Sonnet 5.5, high) prompt: fact-checker/agents/claim-verifier.md (D2)
        │ fc retrieve "<q>" --k 5 --json --run <run> ──► RetrievalResult   (one or more per statement)
        │ writes verdicts.json
        │ fc finalize <run> ──► final.json + transcript.md, trace.jsonl, checks.json
        │                       (grounding rules; code is the authority)
        │ fc judge <run>    ──► scores.json  (Sol: codex_review.py judge --model gpt-6-sol, cwd = the project
        │                                     root, rubric fact-checker/.claude/review-passes/judge.md, D3)
        ▼ returns paths only
     main session runs fc show <run> and pastes the output verbatim. If needs_attention, it brings Sol's
     reasoning to the user and decides with them (D1). Sol never changes a verdict.

     every fc command given a run folder appends one line to <run>/events.jsonl (CLI layer only, D10 1a)

eval, session mode (D7, D10 3a):
  eval-runner (workspace agent, the simulated user)
     │ python3 -m harness --case <id> --run <run-id> --message "<text>"
     ▼
  harness/ ──► headless Claude Code main session: claude -p --resume, runbook prompt,
               FC_RUNS_DIR=<eval run dir>/<case>/fc   (the same flow as above)
     └─ appends turn, tool_call and model_call events to <eval run dir>/<case>/trace.jsonl

eval, scoring:
  eval_checks.py (workspace)  ──► <eval run dir>/<case>/checks.json          (budgets)
  fc eval score               ──► <eval run dir>/<case>/factcheck_checks.json (code checks)
  fc eval judge               ──► <eval run dir>/<case>/eval_scores.json
                                  (codex_review.py judge on GPT-6 Luna, cwd = fact-checker/evals/judge/,
                                   rubric evals/judge/.claude/review-passes/judge.md; D10 4a)
```

- `fc` makes no model calls.
- Every contract file carries `schema_version: 1`.
- Each contract is a pydantic model in `src/fact_checker/contracts.py`. That module is the single source of the JSON schemas that the prompts quote.

## Contracts

### 1. `ConfirmedStatements` (`<run>/confirmed.json`): main session → subagent, `fc finalize`
| Field | Type | Meaning |
| --- | --- | --- |
| `claim` | str | the user's claim, verbatim |
| `statements[]` | `{id:int, text:str, load_bearing:bool, implied_by:str, query:str, kind:"explicit"\|"implicit_assumption"\|"framing_bias", mark:"confirmed"\|"user_edited"\|"user_added"}` | 1–5 items. `implied_by` must be a verbatim span of `claim`, except for `mark: user_added` (D9). `kind` is for display only |
| `proposed[]` | same item shape | the decomposition before the user's edits |
| `edits[]` | `{op:"drop"\|"edit"\|"add"\|"flip_load_bearing"\|"feedback", id:int\|null, value:str\|null}` | what the user changed |
| `rounds` | int (≤3) | confirmation rounds |
| `source` | `"chat"\|"case"` | `case` = an eval case's approved statements |

### 2. `RetrievalResult` (stdout of `fc retrieve "<q>" --k 5 --json`): `fc` → subagent
`query:str, k:int, per_doc:int, hits[] {passage_id:str, doc_id:str (versioned arXiv id), title:str, score:float, text:str}`.
- Deterministic for a given index.
- Zero hits is a valid result.

### 3. `Verdicts` (`<run>/verdicts.json`): subagent → `fc finalize`
`statements[] {id:int, queries[]:str, evidence[] {passage_id:str, quote:str, stance:"supports"|"contradicts"}, verdict:"supported"|"contradicted"|"unknown", reason:str}`.
- There is exactly one entry per confirmed statement id, and nothing else.
- Quotes are at least 5 words long.

### 4. `FinalAnswer` (`<run>/final.json`): `fc finalize` → `fc judge`, `fc show`, the main session
| Field | Meaning |
| --- | --- |
| `claim`, `overall {verdict, rule}` | the overall verdict and the aggregation rule that fired |
| `statements[] {id, text, load_bearing, mark, model_verdict, verdict, downgrade_reason, evidence[], dropped_quotes[]}` | `downgrade_reason` is one of `quote_failed`, `no_hits`, `conflict` or `null` |
| `evidence[]` item | `{doc_id, title, authors, published, quote, stance}`: the paper and a verbatim citation for every statement |
| `counts` | `{confirmed, user_edited, user_added, dropped}` |

**`finalize` rules.** Code is the authority, and it can only move a verdict toward `unknown`.
1. It re-runs each statement's `queries[]` itself. If every query returns zero hits, the statement is `unknown` (`no_hits`).
2. It keeps a quote only if `check_quote` matches it against a passage from **that statement's** re-retrieval. It never trusts the subagent's passage ids. Failed quotes go to `dropped_quotes[]`.
3. `supported` needs at least one surviving `supports` quote, and `contradicted` needs at least one surviving `contradicts` quote. Otherwise the statement is `unknown` (`quote_failed`).
4. If surviving quotes from different `doc_id`s support and contradict the statement, it is `unknown` (`conflict`), and both quotes are kept.
5. The overall verdict is aggregated over the load-bearing statements, applying these rules in order:
   - rule 0: there is no load-bearing statement → `unknown` (D9);
   - rule 1: any has a conflict → `unknown`;
   - rule 2: any is contradicted → `contradicted`;
   - rule 3: any is unknown → `unknown`;
   - rule 4: all are supported → `supported`.

### 5. `JudgeScores` (`<run>/scores.json`): `fc judge` → `fc show`, the main session
`model:str, seconds:float, dimensions {evidence_relevance, statement_verdicts, overreach, conflict_handling, aggregation, unknown_calibration: {score:1..5, evidence:str}}, flagged[] {statement_id:int, dimension:str, reason:str}, needs_attention:bool`.
- Code computes `needs_attention`, not Sol. It is true when `flagged` is non-empty, or when any of `statement_verdicts`, `overreach` or `evidence_relevance` is 2 or less.
- It never changes a verdict (D1, D5).

## Run files that are not contracts
These files are written and read only by `fc`, the harness and the eval code. They are not prompt-facing schemas.
- **`<run>/events.jsonl`**:
  - written only by the `fc` CLI layer, one line per command run against a run folder;
  - each line is `{ts, cmd, ok}`;
  - `retrieve --run` adds the `doc_ids` it returned;
  - `finalize`, `judge` and `show` add the `final_sha256` of the `final.json` they read or wrote;
  - `validate confirmed` adds `rounds` and the number of edits. It also records the model used for the run, since `FinalAnswer` has no `model` field.

  The public functions never write it.
- **`<run>/transcript.md`, `trace.jsonl`, `checks.json`**: written by `fc finalize` for the judge. They hold the re-retrieved passages per statement, the verdicts, the quote checks and the aggregation.
- **`<eval run dir>/<case>/trace.jsonl`, `transcript.md`**:
  - written by the harness and the eval-runner, in the workspace harness format (loop.md 5b);
  - the case's fc run folder is `<eval run dir>/<case>/fc/`, so these never collide with fc's files of the same names.
- **`factcheck_checks.json`, `eval_scores.json`**: per-case eval outputs (section "Evals").

## Public functions (`fc` is a thin argparse layer over these)
- `build_index(corpus: Corpus, db: Path) -> IndexStats`
- `retrieve(db: Path, query: str, k: int = 5, per_doc: int = 2) -> RetrievalResult` (pure apart from reading the DB)
- `check_quote(quote: str, passage: str) -> bool` (rule N4, pure)
- `finalize(confirmed: ConfirmedStatements, verdicts: Verdicts, db: Path) -> FinalAnswer` (quote check, conflict rule and aggregation; its only I/O is through `retrieve`)
- `judge(final: FinalAnswer, run: Path) -> JudgeScores` (the only runtime function that shells out to Codex)
- `render_answer(final: FinalAnswer, scores: JudgeScores | None) -> str` in `report.py`: pure and deterministic, the text that `fc show` prints. `None` renders as "not judged".

`Corpus`, `IndexStats` and the fetch and eval helpers are internal to their modules.

## CLI
| Command | Does | Event logged |
| --- | --- | --- |
| `fc fetch` | arXiv → `data/corpus.json` (48 docs, `dropped_ids` logged) | (none) |
| `fc index` | `data/corpus.json` → `data/index.sqlite` | (none) |
| `fc schema <confirmed\|retrieval\|verdicts\|final\|scores>` | prints the JSON Schema | (none) |
| `fc validate <run> confirmed` | validates `confirmed.json` | yes |
| `fc retrieve "<q>" [--k 5] --json [--run <run>]` | prints a `RetrievalResult` | with `--run`: yes, with `doc_ids` |
| `fc finalize <run>` | writes `final.json`, `transcript.md`, `trace.jsonl`, `checks.json` | yes, with `final_sha256` |
| `fc judge <run>` | writes `scores.json`; exits 1 with no file on any failure | yes, with `final_sha256` |
| `fc show <run>` | prints `render_answer` | yes, with `final_sha256` |
| `fc eval prepare <cases> <eval run dir>` | writes `<case>/fc/confirmed.json` for `statements`-mode cases | (none) |
| `fc eval score <eval run dir> [--hand <dir>]` | the code checks per case and the aggregate report | (none) |
| `fc eval judge <case dir>` | runs the eval rubric on Luna from `evals/judge/` | (none) |
| `python3 -m harness --case <id> --run <run-id> --message "<text>"` | one user turn to the headless session; prints only the agent's reply | harness `trace.jsonl` |

## Evals (D7, D10)
- **Session mode**:
  - the workspace `eval-runner` plays the user through `harness/`;
  - the harness drives `claude -p --resume`, with the runbook as the prompt and `FC_RUNS_DIR` set;
  - the headless session must launch the Sonnet subagent and run Codex without permission prompts.
- **Statements mode**: `fc eval prepare` writes the approved `confirmed.json`, and claim-verifier runs directly. Used for verdict-only regression cases.
- **Code checks** (`fc eval score`):
  - methodology order and approval before retrieval, from the harness trace and `events.jsonl`;
  - missed abstracts, from the `doc_ids` in `events.jsonl` and the evidence in `final.json`;
  - evidence and stance, against the gold verdicts;
  - Sol's output shape and the consistency of its flags;
  - equal `final_sha256` at `judge`, at `show` and on disk, plus the `fc show` text in the agent's final reply;
  - user approval.
- **Judged** (`fc eval judge`, GPT-6 Luna, so Sol never grades itself): meaning preserved, stance correctness, Sol's evidence, and how a rejection is handled.
- **Rubric files**:
  - runtime Sol rubric: `fact-checker/.claude/review-passes/judge.md` (D3);
  - eval rubric: `fact-checker/evals/judge/.claude/review-passes/judge.md` (D10 4a). `codex_review.py` resolves the `judge` pass from the cwd, so each runs from its own folder.

  The workspace `eval-judge` agent is not used: it runs from the project root and would pick up the runtime rubric.

## Build order
The POC comes first (03-solution-prd.md, T1–T4). Each step's unit tests come first.
1. contracts.py, corpus fetch and index, retrieve
2. check_quote, finalize (conflict rule, rules 0–4), `render_answer` and `fc show`, the CLI event log and `retrieve --run`
3. judge and the runtime rubric
4. agents/claim-verifier.md and the session runbook

After the POC:

5. eval prepare and score
6. Sol calibration
7. the eval harness (needs the `claude` CLI installed or linked on PATH)
8. the eval rubric, `fc eval judge` and the code checks that read the event log and the harness trace

## Risks
- **Invalid `verdicts.json`.** The subagent writes JSON that doesn't validate. `fc finalize` rejects it with the validation error, and the subagent fixes it once; if it fails again, the session reports it.
- **Prompt drift.** Prompts quote the contract shapes, so a test asserts that each prompt embeds the current output of `fc schema`.
- **Model and effort.** The session sets the subagent's model and effort on each call, and `fc` doesn't enforce them. The model is recorded in `events.jsonl`.
- **Codex inside the subagent.** Codex needs network access and its sign-in inside the subagent's Bash. This is unverified.
- **Headless session (eval).**
  - `claude -p --resume` must launch the Sonnet subagent and run `fc` and Codex without permission prompts. Unverified.
  - The `claude` CLI is not on PATH on this machine; only the copy bundled in the VS Code extension exists.
  - Whether Claude Code's stream shows the subagent's tool calls is not relied on: `events.jsonl` covers them.
- **Simulated user.** The eval-runner must reply exactly `APPROVE` or `REJECT: ...`. A stray reply fails the case rather than passing it.

## Tests
- **Unit tests per pure function**: rule N4 on the spike-3 cases, the truth table for the conflict and aggregation rules (rules 0–4), the `implied_by` span check (skipped for `user_added`), and `render_answer` on fixtures.
- **Contract tests**: round-trip each model, and reject a bad `Verdicts` file (a missing id, an extra id, a quote under 5 words).
- **`finalize`**: on the spike-6 outputs (`spike-assets/llm/out/verify_A_*.json`, converted to fixtures), expecting 6/6.
- **`judge`**: with Codex mocked, plus one live smoke test that is marked and skipped in CI.
- **CLI event log**: each logging command appends exactly one line with the fields above, and the `final_sha256` matches the file.
- **Harness**:
  - with the `claude` process mocked: prints only the agent's reply and appends the workspace trace events;
  - one live smoke test, marked and skipped in CI, proves that headless `claude -p` launches the Sonnet subagent and runs `fc judge` (Codex) with no permission prompt.
- **Eval code checks**: fixture runs, one passing and one failing for each code-checked dimension.
