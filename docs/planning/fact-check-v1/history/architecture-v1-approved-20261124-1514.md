# Architecture: fact-check-v1 contracts

Status: approved

Source: 02-chosen.md (chosen approach, revised) and 03-decisions.md (D1–D4). There is no code yet, so there are no callers to migrate. A Grep of `fact-checker/` finds only the template scaffold.

## Components and who calls whom

```
user ⇄ main session (Opus)                     decomposes the claim, confirms with the user (D4)
        │ writes confirmed.json
        ▼
     claim-verifier subagent (Sonnet 5.5, high) prompt: fact-checker/agents/claim-verifier.md (D2)
        │ fc retrieve ──► RetrievalResult      (one or more per statement)
        │ writes verdicts.json
        │ fc finalize ──► final.json           (grounding rules, code is the authority)
        │ fc judge    ──► scores.json          (Sol via codex_review.py judge --model gpt-6-sol,
        │                                       rubric fact-checker/.claude/review-passes/judge.md, D3)
        ▼ returns paths only
     main session reads final.json + scores.json from disk; if Sol flags anything it shows Sol's
     reasoning to the user and decides with them (D1). No automatic downgrade by the judge.
```

`fc` makes no model calls. Every JSON file carries `schema_version: 1`. Each contract is a pydantic model in `src/fact_checker/contracts.py`, which is the single source of the JSON schemas the prompts quote.

## Contracts

### 1. `ConfirmedStatements` (`<run>/confirmed.json`): main session → subagent, `fc finalize`
| Field | Type | Meaning |
| --- | --- | --- |
| `claim` | str | the user's claim, verbatim |
| `statements[]` | `{id:int, text:str, load_bearing:bool, implied_by:str, query:str, kind:"explicit"\|"implicit_assumption"\|"framing_bias", mark:"confirmed"\|"user_edited"\|"user_added"}` | 1–5 items; `implied_by` is a verbatim span of `claim` (checked); `kind` is display only |
| `proposed[]` | same item shape | the decomposition before the user's edits |
| `edits[]` | `{op:"drop"\|"edit"\|"add"\|"flip_load_bearing"\|"feedback", id:int\|null, value:str\|null}` | what the user changed |
| `rounds` | int (≤3) | confirmation rounds |
| `source` | `"chat"\|"case"` | `case` = an eval case's approved statements |

### 2. `RetrievalResult` (stdout of `fc retrieve "<q>" --k 5 --json`): `fc` → subagent
`query:str, k:int, per_doc:int, hits[] {passage_id:str, doc_id:str (versioned arXiv id), title:str, score:float, text:str}`. Deterministic for a given index. Zero hits is a valid result.

### 3. `Verdicts` (`<run>/verdicts.json`): subagent → `fc finalize`
`statements[] {id:int, queries[]:str, evidence[] {passage_id:str, quote:str, stance:"supports"|"contradicts"}, verdict:"supported"|"contradicted"|"unknown", reason:str}`. There must be one entry per confirmed statement id, and nothing else.

### 4. `FinalAnswer` (`<run>/final.json`): `fc finalize` → main session
| Field | Meaning |
| --- | --- |
| `claim`, `overall {verdict, rule}` | overall verdict and the aggregation rule that fired |
| `statements[] {id, text, load_bearing, mark, model_verdict, verdict, downgrade_reason, evidence[], dropped_quotes[]}` | `downgrade_reason` ∈ `quote_failed`, `no_hits`, `conflict`, `null` (no `judge_flag`: D1) |
| `evidence[]` item | `{doc_id, title, authors, published, quote, stance}`: paper name and verbatim citation for every statement |
| `counts` | `{confirmed, user_edited, user_added, dropped}` |

`fc finalize` re-runs each statement's `queries[]` itself and accepts a quote only if, after rule N4, it is a substring of a passage that this re-retrieval returned for that statement. So it never trusts the subagent's passage ids.

### 5. `JudgeScores` (`<run>/scores.json`): `fc judge` → main session
`model:str, seconds:float, dimensions {evidence_relevance, statement_verdicts, overreach, conflict_handling, aggregation, unknown_calibration: {score:1..5, evidence:str}}, flagged[] {statement_id:int, dimension:str, reason:str}, needs_attention:bool`.
`needs_attention` is computed by code, not by Sol: it is true when `flagged` is non-empty or any of `statement_verdicts`, `overreach` or `evidence_relevance` is ≤ 2. It tells the main session to bring Sol's reasoning back to the user (D1).

## Public functions (the `fc` CLI is a thin layer over these)
- `build_index(corpus: Corpus, db: Path) -> IndexStats`
- `retrieve(db: Path, query: str, k: int = 5, per_doc: int = 2) -> RetrievalResult` (pure apart from reading the DB)
- `check_quote(quote: str, passage: str) -> bool` (rule N4, pure)
- `finalize(confirmed: ConfirmedStatements, verdicts: Verdicts, db: Path) -> FinalAnswer` (quote check, conflict rule, aggregation; I/O only through `retrieve`)
- `judge(final: FinalAnswer, run: Path) -> JudgeScores` (the only function that shells out to Codex)

## Build order
1. contracts.py (models and JSON schema export)
2. corpus fetch and index
3. retrieve
4. check_quote
5. finalize (conflict rule and aggregation)
6. judge and the rubric
7. agents/claim-verifier.md and the session runbook
8. eval prepare and score

Each step has its own tests first.

## Risks
- The subagent writes JSON that doesn't validate. `fc finalize` rejects it with the validation error, and the subagent fixes it once; if it fails again, the session reports it.
- The contract shape is quoted in prompts, so prompts must be generated from or checked against `contracts.py` (a test asserts that the prompt embeds the current schema).
- The subagent's model and effort are set by the session on each call and aren't enforced by `fc`. The run records `model` in `final.json` for audit.
- Codex needs network and its sign-in inside the subagent's Bash; this is unverified.

## Tests
- Unit tests per pure function: rule N4 on the spike-3 cases, the conflict and aggregation truth table, and the `implied_by` span check.
- Contract tests: round-trip each model; reject bad `Verdicts` (missing id, extra id, quote under 5 words).
- `finalize` on the spike-6 outputs (`spikes/llm/out/verify_A_*.json`) as fixtures, expecting 6/6.
- `judge` with Codex mocked; one live smoke test marked and skipped in CI.
