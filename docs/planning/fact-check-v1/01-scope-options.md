# I1: Scope and options (fact-check-v1)

Time box: a working CLI at about 30 minutes, then the interviewers probe its limits. No 00-context.md exists; open points are at the end.

## What I found
- **Project**: an empty template. CI runs `pytest` on Python 3.12 with no API key, so tests must mock the LLM and the network. On this machine, system `python3` is 3.9 and `/opt/homebrew/bin/python3.12` is also installed. Neither has `anthropic` installed.
- **arXiv API** (checked with curl): `https://export.arxiv.org/api/query?id_list=<id>v<n>,...` returns the exact version asked for.
  - `2307.03172` v1 and v3 ("Lost in the Middle") are reworded: 122 and 145 words.
  - `2403.01432` v1 and v5 (FT vs RAG for less popular knowledge) differ in substance: 143 vs 211 words, "LLMs" vs "LMs", a new conclusion in v5, and a different code URL.
  - So the 50 ids are 48 papers. **The user's decision**: keep only the latest *listed* version of each paper (`2307.03172v3`, `2403.01432v5`), which gives **48 documents**.
  - `<published>` is the v1 date for every version and `<updated>` is the date of that version.
- **SQLite FTS5** with `bm25()` ranking works in the standard-library `sqlite3` (3.54.1 on Python 3.12). That gives a lexical index on disk with no services and no extra dependencies.
- **Sonnet 5.5 API facts** (given by the user; verified):
  - Effort is set with `output_config: {"effort": "high"}`.
  - Thinking is adaptive, so leave that parameter out; `{type: "disabled"}` returns a 400.
  - A forced `tool_choice` (`any`/`tool`) returns a 400.
  - Structured output goes through `output_config.format`, or `tool_choice: auto` with `strict: true`.
  - Server-side fallbacks: `betas: ["server-side-fallback-2026-07-01"]`, `fallbacks: "default"`.
  - Check `stop_reason == "refusal"`.
  - **No API key** is available: no `ANTHROPIC_API_KEY` in the environment, no `.env`, no `ant` CLI.
- **Codex review path**:
  - `codex` is at `/opt/homebrew/bin/codex`.
  - `scripts/codex_review.py` has a `judge` pass that reads the project's own `.claude/review-passes/judge.md` before the workspace's, and runs on Luna unless `--model` is given (Sol is `CODEX_SOL_MODEL=gpt-6-sol`).
  - `PASSES` is a fixed tuple, so a new pass name would mean editing the script.
  - `/eval-calibrate` also reads `<project>/.claude/review-passes/judge.md`, but its dimension names (`tool_use`, `groundedness`, ...) are hard-coded.

## Pipeline
`claim -> decompose (proposal) -> USER CONFIRMS (loop) -> confirmed statements -> retrieve per statement -> verdict per statement (evidence: title, versioned arXiv id, verbatim quote) -> quote check (code) -> conflict check (code) -> aggregate (code) -> overall verdict`

Decomposition and verification are **two separate steps with a typed hand-off**:
- `decompose(claim, feedback=None) -> Proposal`: an LLM call.
- `apply_edits(proposal, edits) -> Confirmed`: pure.
- `verify(claim, confirmed) -> Result`: retrieval, the verdict call and the code rules.
- `Confirmed` carries `proposed`, `confirmed`, `edits[]`, `rounds` and `source: interactive|auto|file|script`.
- The CLI prompt loop is a thin layer that reads input and produces `edits`. No pure function reads stdin.

- **Models**:
  - Every LLM step (decomposition, an optional rerank, verdicts) uses **`claude-sonnet-5-5` at `effort: "high"`**, set explicitly.
  - All rules after the verdict are deterministic code.
  - **Reviews** are a separate offline loop: GPT-6 Sol, through Codex, judges eval runs. It does not run inside `fc check`.
- **The decomposition** breaks the claim into:
  - **explicit sub-claims**: the atomic parts it states;
  - **implicit assumptions and presuppositions**: what it takes for granted. For example, "Why does RAG beat fine-tuning?" presupposes that RAG beats fine-tuning;
  - **framing biases**, each rewritten as a testable statement:
    - loaded wording;
    - false precision;
    - overgeneralisation ("all", "always");
    - causal framing where the evidence is only correlational.
  - Each item is rewritten as one falsifiable statement with its own query.

## User stories (v1)
- **US-1 Fetch corpus**: `fc fetch` groups the 50 listed ids by base id and keeps the highest listed version of each. It fetches those 48 in one API call (`max_results=48`) and caches them to `data/corpus.json`.
  - Each record holds `doc_id` (versioned) and `base_id`, plus title, authors, published, updated and abstract.
  - The corpus metadata records `dropped_ids: ["2307.03172v1", "2403.01432v1"]`, and `fc fetch` logs them, so nothing is lost silently.
  - "Latest" means the latest of the listed versions, not arXiv's newest today. That keeps the corpus reproducible and matches the given list.
- **US-2 Decompose a claim**: `fc decompose "<claim>"` lists the statements. Each has its kind, `implied_by` span, `falsifiable_by` and query. `-o file.json` saves them for `--statements`.
- **US-2b Confirm the decomposition**: `fc check` stops after decomposing and shows the numbered statements with their kind, load-bearing flag and claim span. The user then:
  - accepts;
  - drops, edits or adds a statement;
  - flips a statement's load-bearing flag;
  - or gives free-text feedback, which triggers a new decomposition with that feedback.
  - There are at most 3 rounds; after that it asks for "accept or abort". An added or edited statement goes through the falsifiability check, and if it fails, the reason is shown and the user is asked again. No retrieval happens before the user accepts.
- **US-3 Check a claim**: `fc check "<claim>"` prints the confirmed decomposition and then **one row per statement**:
  - statement, kind, a `confirmed` / `user-edited` / `user-added` mark, verdict;
  - paper title, `doc_id` (e.g. `2403.01432v5`), a **verbatim quote**;
  - any conflict flag.
  - After the rows it prints the **overall verdict** with the rule that produced it, and "based on N statements you confirmed (k edited, j dropped)".
  - `--json` gives the same output as JSON, with the proposed decomposition, the confirmed decomposition and the edits.
  - `--trace <dir>` writes `transcript.md`, `trace.jsonl` (including the `proposed`, `edit` and `confirmed` events) and `checks.json` for the judge.
  - Non-interactive runs:
    - `--yes` accepts the proposal as it is;
    - `--statements file.json` skips decomposition;
    - `--script edits.json` replays scripted user edits.
    - If there is no TTY and none of these flags is given, it exits with an error instead of hanging.
- **US-4 Grounded verdicts**:
  - A quote that fails the check is dropped.
  - Conflicting papers make a statement `unknown`.
  - A statement with no relevant passages is `unknown`, and the LLM is not called for it.
- **US-5 Evaluate**: `fc eval` runs every case without a human. It passes each case's **approved statements** with `--statements` and writes one run folder per case, then prints:
  - accuracy and the confusion matrix;
  - per-statement accuracy;
  - the quote-check pass rate and recall@k.
- **US-6 Sol review**: GPT-6 Sol, through `codex_review.py judge`, judges **only the final answer** of each case run against the rubric below and writes `scores.json`. The approved statements are taken as given. It can also judge a single `fc check --trace` result on demand.
- **US-7 Inspect retrieval**: `fc retrieve "<text>"` shows the top-k passages with their scores.

**Out of scope**:
- full-text PDFs;
- a GUI or server;
- Docker, vector DB services or hosted search;
- deployment;
- world knowledge outside the corpus;
- languages other than English;
- recursive decomposition;
- a Codex call inside `fc check` at runtime (alternative R2 below).

## Corpus fetch
- **Request**: one HTTPS request for the 48 kept ids.
- **Parsing**: stdlib `xml.etree`.
- **Retries**: on an empty feed or a 503, retry with a pause of 3 seconds or more.
- **Validation**: assert 48 entries, every kept `doc_id` present, and the two `dropped_ids` recorded.
- **Cache**: commit `data/corpus.json` so runs are reproducible and work offline.

## Decision 0: Decomposition
**Output schema** (`output_config.format`): `statements[] {id, text, kind: explicit|implicit_assumption|framing_bias, implied_by, load_bearing, falsifiable_by, query}`.

| Option | Trade-off |
| --- | --- |
| **A. One Sonnet call, at most 5 statements** (recommended) | Fast enough. Guarded below |
| B. Two passes: explicit statements, then assumptions and biases | More focused, but 2x the latency and needs deduplication |
| C. Explicit sub-claims only | Least drift, but misses the hidden-premise cases the user wants |

**The quality gate is the user's approval**, not Sol. Before the user sees the proposal, code applies these guards:
1. **The original claim is always statement 0** and is load-bearing.
2. **A cap of 5.**
3. **`implied_by` must be a verbatim span of the claim**; a statement whose span fails is dropped.
4. **A framing bias decides nothing unless it is load-bearing.**

**The confirmation loop** (US-2b):

| Option | How | Trade-off |
| --- | --- | --- |
| **A. A numbered menu with commands** (recommended) | `a` accepts. `d N` drops, `e N <text>` edits, `+ <text>` adds, `l N` flips load-bearing, `f <text>` gives feedback and re-decomposes. At most 3 rounds | Fast to type live. Every action is recorded as an `edit` |
| B. Accept or give free-text feedback only | Every change goes through re-decomposition | Simplest, but slow (one Sonnet call per round) and drifts |
| C. Open the statements in `$EDITOR` as JSON | Full control | Clumsy in a live demo; easy to break the schema |

**Falsifiability check for a statement the user adds or edits**:
- A. One Sonnet call returning `{falsifiable, reason, query}` (recommended). It also writes the statement's search query.
- B. A code heuristic (one sentence, no "and"/"or", no opinion words). Cheap but brittle.

If the check fails, the reason is shown and the user is asked again. The user is the authority on intent, so a statement the user adds needs no `implied_by` span; it is marked `user-added`.

**Non-interactive input**:

| Option | Use |
| --- | --- |
| `--statements file.json` (recommended for evals and Sol) | Each eval case carries its **approved** statement list, so verification is judged on an aligned decomposition |
| `--yes` | Accepts the proposal unseen. For quick demos and smoke runs only; the output says "not confirmed" |
| `--script edits.json` | Replays scripted user actions through the same `apply_edits`. It tests the loop logic in pytest, not answer quality |

## Decision 1: Retrieval (per statement)
Unit of retrieval: **sentence-window passages**, 2 to 3 sentences with a stride of 1. The title goes first in each passage, and each document also gets one metadata passage. Each statement runs its own query, and the source of each passage is tracked.

| Option | Pros | Cons | At 1000x scale |
| --- | --- | --- | --- |
| **A. BM25 with SQLite FTS5** (recommended start) | No setup, explainable, exact on numbers and names | Misses paraphrases | An inverted index on disk, sublinear |
| B. Local dense embeddings (`fastembed`) | Handles paraphrase | Download time; weak on negation and numbers | FAISS or hnswlib, built offline |
| C. Hybrid with RRF, top-20, then a Sonnet rerank to top-5 | Best precision | One more high-effort call per statement | The rerank cost is fixed per statement |

Plan: A behind `Retriever.search(query, k)`, with k = 5 per statement and at most 2 passages per `base_id`. The LLM sees at most N x k passages, so the cost per claim does not grow with the corpus.

## Decision 2: Grounding, conflicts and aggregation
**Per statement** (enforced in code):
1. **Evidence before verdict**: `evidence[] {passage_id, doc_id, quote, stance}`, then `verdict`. Missing information means `unknown`.
2. **Verbatim quote check**: after normalizing whitespace, case, quotes and dashes, the quote must be a substring of the cited passage, which must be one of that statement's own passages. Quotes that fail are dropped. A statement with no surviving quote is `unknown`.
3. **Retrieval floor**: if the best score is below a threshold tuned on the eval set, the statement is `unknown` and the LLM is skipped.
4. **Conflict rule** (the user's): if surviving quotes from **different papers** support and contradict the same statement, it is `unknown` and both are shown. The corpus has one version per paper, so versions cannot conflict.
5. **Refusals and errors**: if `stop_reason == "refusal"`, or the output does not parse after one retry, the statement is `unknown` (reason `model_refusal` or `model_error`).

**Aggregation** (pure function). **A, strict and ordered (recommended)**: rules are applied in this order:
1. any load-bearing statement has a conflict: `unknown`;
2. any load-bearing statement is contradicted: `contradicted`;
3. any load-bearing statement is `unknown`: `unknown`;
4. every load-bearing statement is supported: `supported`.

The alternatives are B (statement 0 decides) and C (a weighted vote).

## Decision 3: Correctness
The user approves the decomposition, so the eval judges **the final answer given approved statements**.
- **Code checks** (deterministic, in `checks.json`; Sol does not re-judge these):
  - the label against the gold label, overall and per statement;
  - quote verbatim pass or fail;
  - the statement cap;
  - recall@k on `gold_doc_ids`.
- **Optional diagnostic** (code only, not part of the Sol rubric): how often a raw `--yes` proposal covers the case's approved statements. This tracks how often the user has to edit.
- **Sol judges** what code can't: the final-answer rubric below.
- **Eval cases**: `evals/cases/<case-id>.yaml`, one file per case, because that is the shape the judge pass expects. Each case has `claim`, `label`, **`statements`** (the approved list, passed with `--statements`; each statement has its own gold verdict), `gold_doc_ids` and `note`. There are about 24 to 30 cases. The types are:
  - paraphrase;
  - a changed number or flipped direction;
  - a swapped entity;
  - topic present but the fact absent;
  - outside the corpus;
  - a hidden presupposition, made into an approved statement;
  - biased framing ("all", causal wording);
  - a compound claim with one false part;
  - conflicting abstracts, which should be `unknown`;
  - optional: a claim true only in `2403.01432v1` (the "LLMs" wording or the HeydarSoudani repo URL) is not `supported`, because v1 is out of the corpus;
  - a metadata claim;
  - an injected instruction.
  - Each case is checked by a human.
- **The loop itself** is tested in pytest with `--script` and a fake decomposer. The tests cover:
  - a scripted user dropping or editing a statement;
  - an added statement that fails the falsifiability check and is re-asked;
  - the round cap.
  - They assert the confirmed list and the recorded edits.
- **Runs**: `evals/runs/<run-id>/<case-id>/` (git-ignored) holds `transcript.md`, `trace.jsonl` (confirmed statements, retrieval hits, verdict call, code checks), `checks.json` and `scores.json`.
- **Calibration**: the user grades a sample by hand with `/eval-calibrate`. Sol's scores count only once they agree with the hand grades within 1 point per dimension. Where they differ, the anchors are changed.

## Sol review rubric (draft): final answer only
The file is `fact-checker/.claude/review-passes/judge.md`; see "Rubric location" below. Its draft text:

> You are judging the final answer of a claim fact-checker for one eval case. You get the case (claim, gold label, the approved statements with their gold verdicts, gold docs), the transcript, the trace (retrieved passages per statement, verdict-call output, aggregation) and the code checks. The user approved the statements: take them as given and don't judge the decomposition. The code checks already settle label accuracy against gold, verbatim quotes and the statement cap: don't re-judge them. Judge only from the quoted evidence and passages in the trace, never from your own knowledge of the papers.
>
> Score each dimension separately from 1 to 5. Never combine them.
> 1. evidence_relevance: does each quote bear on its statement, not just share keywords?
>    5 = every quote addresses its statement directly. 3 = some quotes are only topical. 1 = quotes mostly share keywords without bearing on the statement.
> 2. statement_verdicts: given only the quoted evidence, is each statement's verdict right?
>    5 = all follow from the quotes. 3 = one is debatable. 1 = one or more contradict their quotes.
> 3. overreach: no `supported` on partial or hedged evidence, and no `contradicted` from mere absence.
>    5 = none. 3 = one borderline case. 1 = a clear overreach on a load-bearing statement.
> 4. conflict_handling: do contradictions between different papers give `unknown`, with both quotes shown?
>    5 = correct, or no conflict present and none invented. 3 = a conflict flagged but explained poorly. 1 = a real conflict missed, or a conflict invented from quotes that don't disagree.
> 5. aggregation: does the overall verdict follow the stated rule from the statement verdicts?
>    5 = it follows exactly. 3 = it follows, but the rule shown is wrong or missing. 1 = it violates the rule.
> 6. unknown_calibration: is `unknown` avoided where the quoted evidence is decisive?
>    5 = `unknown` only where the evidence is missing or conflicting. 3 = once where the evidence looks decisive. 1 = used by default despite decisive evidence.
>
> For each dimension give the score and the evidence: quote the transcript or name the trace field (e.g. `trace[3].evidence[0].quote`).
>
> Output only this JSON:
> {"case": "<case-id>", "evidence_relevance": {"score": 0, "evidence": ""}, "statement_verdicts": {"score": 0, "evidence": ""}, "overreach": {"score": 0, "evidence": ""}, "conflict_handling": {"score": 0, "evidence": ""}, "aggregation": {"score": 0, "evidence": ""}, "unknown_calibration": {"score": 0, "evidence": ""}}

**Rubric location and choosing Sol**:
- **Conflict to flag**: `~/Developing/CLAUDE.md` says `.claude/` lives "only here, never copied into a project". But `codex_review.py` (`pass_prompt_path`) and `/eval-calibrate` both support `<project>/.claude/review-passes/judge.md`. The workspace rule and the code disagree.

| Option | How | Trade-off |
| --- | --- | --- |
| **A. Project override and `--model gpt-6-sol`** (recommended) | `fact-checker/.claude/review-passes/judge.md` holds the rubric. Run `codex_review.py judge --model gpt-6-sol --run-dir ... --context-file ...` once per case | No workflow code change; `/eval-calibrate` already looks there. It needs the user to accept the CLAUDE.md exception. `/eval-calibrate`'s hard-coded dimension names need a small workflow fix |
| B. A new workspace pass `factcheck-judge` added to `PASSES` (optionally to `SOL_PASSES`) | The rubric lives in `~/Developing/.claude/review-passes/` | Keeps CLAUDE.md as written, but changes the workflow repo (a separate root task) |
| C. The generic `judge` with `--model gpt-6-sol` and the rubric passed as a `--context-file` | No new files | Sol sees two conflicting rubrics. Not recommended |

## Cost and latency
| Item | Calls | Note |
| --- | --- | --- |
| Decomposition and confirmation | 1 Sonnet call, plus 1 for each feedback round (3 at most), plus 1 falsifiability check for each statement the user adds or edits | The human's thinking time dominates. The menu commands avoid re-decomposing |
| Verdicts, batched (recommended) | 1 Sonnet high call | The own-passage check prevents evidence bleed between statements. The spike measures latency |
| Verdicts, per statement (in parallel) | N (N of 5 or less) | About the same wall time; N times the tokens |
| Sol review, offline (recommended) | 1 Codex call per eval case | About 30 calls per eval run; no cost per production claim |
| R2: Sol at runtime for every claim | 1 Codex call per `fc check` | Tens of seconds and OpenAI cost per claim, and Codex must be signed in wherever `fc` runs. At most an opt-in `--review` flag |

## Overall alternatives
1. **Decompose, user confirms, BM25 per statement, one batched verdict, Sol judges final answers offline (recommended)**. *Main assumption*: given approved statements, the batched call keeps each statement's evidence separate, with per-statement accuracy of 85% or more on the eval set.
2. **Decompose, user confirms, hybrid retrieval with a Sonnet rerank, per-statement verdicts in parallel; Sol offline**. *Main assumption*: N + N + 1 high-effort calls after confirmation stay within the latency budget.
3. **Agentic verification after confirmation**: Sonnet gets `search(query)` and loops over the confirmed statements, then fills the same schema; the same code checks run, and Sol judges offline. *Main assumption*: it converges in 6 tool calls or fewer with `tool_choice: auto` and is stable enough to evaluate.

## Risks to test in I2 (ranked)
1. **The confirmation UX in a live demo**: the prompt has to be readable, quick to answer, and must not hang when there is no TTY. *Spike*: the loop with a fake decomposer in a real terminal. Time accepting, dropping, editing and adding; check that piped stdin without `--yes` or `--statements` exits with a clear error.
2. **The conflict rule misfires**: papers with different setups are flagged as conflicting. *Spike*: 4 hand-picked approved statements through the conflict code.
3. **The quote check over-rejects** (LaTeX `\url{}`, unicode). *Spike*: 10 calls, measure the pass rate. If it is under 90%, add a `difflib` fallback.
4. **Sonnet 5.5 call shape**: `output_config.format` with `effort`, fallbacks and the refusal path, for decomposition, the falsifiability check and the verdict. *Spike*: one call per schema. **Blocked**: an API key is needed.
5. **Latency of high-effort calls**, including a feedback round. *Spike*: time 5 claims, decomposition and verdict separately.
6. **Sol judge agreement with hand labels** on the 6 final-answer dimensions. *Spike*: 5 runs judged by Sol and by the user; per-dimension difference of 1 point or less.
7. **Codex CLI latency per case, and sign-in.** *Spike*: `time codex_review.py judge --model gpt-6-sol` on one case; confirm `gpt-6-sol` is available to this account.
8. **BM25 recall per approved statement.** *Spike*: 10 paraphrased statements, recall@5.
9. **arXiv flakiness and environment set-up.** *Spike*: fetch the 48 kept ids, assert 48 entries and the two `dropped_ids`; time the venv plus `pip install anthropic pydantic`.

## Open for the user
- **Confirmation loop**: the menu with commands (recommended) or free-text feedback only? And is a cap of 3 rounds right?
- Should `--yes` exist at all, or should non-interactive runs require `--statements`?
- **Rubric location**: option A, the project override (accepting the CLAUDE.md exception), or option B, a new workspace pass?
- `/eval-calibrate` has hard-coded dimension names. Should it be fixed as a separate workflow task?
- **Aggregation**: strict ordered rule A (recommended)?
- **Verdict calls**: one batched call (recommended) or per-statement calls?
- **Sol review**: offline over evals only (recommended), or also a `--review` flag on `fc check`?
- The Anthropic API key (`.env`?) and the cost and latency budget per claim.
- Should `data/corpus.json` be committed? (Recommended: yes.)
- Approved statements and gold verdicts for the eval cases: written by hand, or drafted by an LLM and approved by the user?
