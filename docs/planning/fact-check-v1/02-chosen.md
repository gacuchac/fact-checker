# I2: Test and choose (fact-check-v1)

Spikes live in `spikes/` (git-ignored). Python: `/opt/homebrew/bin/python3.12`; spike venv `spikes/.venv` (fastembed, anthropic 2.13, pydantic; installed in 14 s). Run every command below from `docs/planning/fact-check-v1/spikes/`.

## Spike results

### 1. Corpus fetch: HELD
- **Test**: one batched `export.arxiv.org/api/query?id_list=<48 ids>&max_results=48`, parsed with `xml.etree`. Retries with a 3.5 s pause are wired in but weren't needed.
- **Result**: 48/48 entries on the first try in **0.6 s**, no failures. The kept ids match the request exactly. `dropped_ids = [2307.03172v1, 2403.01432v1]`. Saved to `spikes/corpus.json` with title, authors, published, updated and abstract.
- **Text features that matter later**: 8 abstracts contain LaTeX (`\%`, `\textbf{}`, `$ε$`, `\url{}`, `\href{}`, `$^2$`). The only non-ASCII characters are `ε` and `λ`. Two `short- and` style hyphenations.
- **Rerun**: `python3.12 -I fetch_corpus.py`

### 2. Retrieval: HELD for recall, FALSIFIED for a score threshold
- **Test**: SQLite FTS5 (`porter unicode61`) with BM25. Passages are sentence windows with stride 1, the title in front, plus one metadata passage per paper. The query is the statement's keywords joined with OR, and at most 2 passages come from one paper. There are 13 hand-written statements: 3 close to the abstract wording, 6 paraphrased, 4 out of corpus (1 far off-topic, 3 near the domain).

| Setting | Close, recall@1 / @5 | Paraphrased, recall@1 / @5 |
| --- | --- | --- |
| BM25, 3-sentence windows (317 passages) | 3/3 / 3/3 | 5/6 / 5/6 |
| **BM25, 2-sentence windows (365 passages)** | 3/3 / 3/3 | 5/6 / **6/6** |
| Dense `bge-small-en-v1.5` (fastembed; 3 s to load, 8 s to embed) | 2/3 / 3/3 | 4/6 / 6/6 |
| RRF of BM25 and dense | 2/3 / 3/3 | 5/6 / 6/6 |
| BM25 on the statement plus a keyword query | n/a | the 3 weakest paraphrases all move to rank 1 |

- **The one BM25 miss**: "64 thousand tokens" against the abstract's "64k" (rank 5 with 2-sentence windows, missed with 3). Adding a keyword query fixed it (score 9.2 to 21.6). **Caveat**: I wrote those queries by hand after reading the abstracts, so they are optimistic. Spike 6 measures the model's own `query` field.
- **Threshold**: no score separates out-of-corpus statements.
  - The 3 near-domain out-of-corpus statements (4-bit quantisation, MoE routing, Transformer origin) score **5.3 to 13.9** in BM25. The paraphrased in-corpus statements score **6.6 to 18.2**. Per-term normalised scores also overlap (0.87 to 1.39 against 0.83 to 1.57).
  - Dense similarity overlaps too: **0.77 to 0.78** for near-domain out-of-corpus against **0.68 to 0.85** for paraphrased in-corpus.
  - Only the far off-topic statement ("photosynthesis") is separable: it gets 0 BM25 hits and dense similarity 0.55.
- **What it means**:
  - BM25 alone is enough at this size.
  - Dense retrieval adds no recall here and costs a 90 MB download and 11 s. Keep it as the scale-up option behind the same `Retriever` interface.
  - Out-of-corpus statements must be caught by the verdict and the quote check, not by a retrieval floor. The floor only applies to "no hits at all".
- **Rerun**: `python3.12 retrieval_spike.py -v`, `.venv/bin/python dense_spike.py`, `python3.12 query_rewrite_spike.py`

### 3. Verbatim quote check: HELD with rule N4
- **Test**: 20 quotes on real abstracts. 11 are genuine but reformatted: curly quotes, an en dash for a hyphen, line wrapping, case and a trailing period, LaTeX `\%` / `\textbf{}` / `$ε=0$` / `\url{}`, and `short- and`. 9 are fabricated: a changed number, the sign of `-1.9` dropped, an inserted negation, a swapped entity, stitching with an ellipsis, stitching across sentences, a paraphrase, a true but trivial 3-word quote, and v1-only wording ("LLMs" instead of "LMs").

| Rule | Genuine accepted | Fabricated accepted |
| --- | --- | --- |
| exact substring | 3/11 | 0/9 |
| + whitespace and casefold | 4/11 | 0/9 |
| + NFKC, quotes and dashes | 6/11 | 0/9 |
| + LaTeX stripped | 10/11 | 0/9 |
| **+ hyphenation (N4)** | **11/11** | **0/9** |

- **A `difflib` fallback is rejected.** The fabricated quotes reach ratios of 0.97 (changed number), 0.99 (dropped sign), 0.98 (swapped entity) and 1.00 (trivial quote), so any fuzzy threshold that rescues formatting would also admit fabrications.
- **Rerun**: `python3.12 quote_spike.py`

### 4. Codex Sol judge: HELD
- **Test**: `codex_review.py judge --model gpt-6-sol --run-dir ../judge_run --context-file case.yaml --context-file transcript.md --context-file trace.jsonl --context-file checks.json`, using the draft rubric from 01 and a fake final answer with a planted overreach ("contradicted" from absence on S2).
- **Finding**: `pass_prompt_path` resolves the override from the **current working directory** (`Path.cwd()/.claude/review-passes/judge.md`), not from a fixed project path. The spike ran from `spikes/judge_cwd/`, which holds the rubric, so **nothing was written under the project's `.claude/`**.
- **Result**:
  - exit 0 in **14 s** (codex-cli 0.171.0, signed in with ChatGPT);
  - the output is a bare JSON object that `json.loads` parses, with all 6 dimensions and every score between 1 and 5;
  - Sol caught the planted overreach (overreach 1, statement_verdicts 1). It also caught an accidental one: the S1 quote compares fine-tuning with a baseline, not with RAG;
  - it scored conflict handling and aggregation 5, which is correct.
- **Rerun**: `cd judge_cwd && python3 ~/Developing/scripts/codex_review.py judge --model gpt-6-sol --run-dir ../judge_run --context-file ../judge_case/case.yaml --context-file ../judge_case/transcript.md --context-file ../judge_case/trace.jsonl --context-file ../judge_case/checks.json`

### 5. Confirmation UX: HELD
- **Test**: a prototype of a pure `apply_edit(statements, line)` and a thin stdin loop with canned statements.
- **Result**:
  - **Piped stdin with no flag** exits 1 with "stdin is not a terminal; pass --yes, --statements FILE or --script FILE". It does not hang.
  - **`--yes`, `--statements` and `--script`** all work. The script replay showed the falsifiability rejection ("opinion words") and the guard that keeps statement 0 from being dropped.
  - **Through a real pty** (`script(1)`), a 3-line session (`d 3`, `l 2`, `a`) produced the confirmed list and recorded the edits.
  - **Typing cost**: accepting takes 1 line, and a typical fix-up takes 2 to 3 lines. The menu fits in 100 columns.
  - **EOF** (for example input piped faster than the prompt reads it) aborts, which is safe.
  - **Not measured**: human reading time.
- **Rerun**: `echo a | python3.12 confirm_spike.py; python3.12 confirm_spike.py --script script.json; (sleep .5; echo 'd 3'; sleep .3; echo a; sleep .5) | script -q /dev/null python3.12 confirm_spike.py`

### 6. Live LLM via Sonnet subagents (high effort): HELD for the core, the periphery is noisy
- **Test**: each subagent saw only the system prompt, the schema and its inputs, never the expected outputs. The inputs are in `spikes/llm/`:
  - `decompose_prompt.md`: claims D1 to D5, run twice (A and B);
  - `verify_cases.md`: cases V1 to V6 with the real BM25 top-5, run once.

  The outputs are in `spikes/llm/out/`.
- **6b verdicts: 6/6 cases PASS**, and every quote passed the N4 verbatim check.
  - V3, on topic but not settled: `unknown`. The model did not call missing evidence "contradicted".
  - V4, two papers disagreeing: a supports quote from 2312.05934v3 and a contradicts quote from 2604.23801v1, so the code makes it `unknown`.
  - V5, out of corpus: `unknown`.
  - V6, batched: S0 supported and S1 contradicted, with the evidence kept with the right statement.
  - **Caveat**: 6 cases with expectations I wrote. This shows the prompt works; it does not measure accuracy.
- **6a decomposition (2 runs of 5 claims)**:
  - **Guards**: `implied_by` is verbatim in 27 of 27 statements, no output has more than 5 statements, and S0 is load-bearing every time.
  - **Expected structure, in both runs**:
    - D2 splits into a +30% statement and a "hurts short tasks" statement, with an identical structure;
    - D3's presupposition is S0;
    - D4's "always" is a framing_bias.
  - **Retrieval with the model's own queries**: the gold paper is top-1 for every load-bearing statement in D1 to D4, in both runs. This settles the doubt from spike 2 that my hand-written queries were optimistic.
  - **Stability**: the load-bearing core (S0 and the main explicit statements) is stable up to wording. The periphery varies:
    - statement counts change between runs: D1 from 2 to 3, D4 from 4 to 3, D5 from 4 to 2;
    - `kind` labels flip: D3's S0 is implicit_assumption in A and explicit in B.
  - **Over-decomposition**:
    - D4-A has 3 near-duplicate "retrieval always helps" statements;
    - D5, which is out of corpus, gets 4 statements in A;
    - D1 gets an invented "across all models" framing bias in both runs (load-bearing in neither);
    - D3 gets an extra statement that is not load-bearing.
- **What it means**: the core is reliable and the periphery is noisy, so quality is controlled at the user's confirmation step, which supports that decision. The prompt changes in the chosen approach below follow from this.
- **Rerun**:
  - verdicts: `for v in V1 V2 V3 V4 V5 V6; do python3.12 llm/check_verdicts.py $v llm/out/verify_A_$v.json; done`
  - decompositions: `python3.12 llm/check_queries.py "<claim>" llm/out/decompose_<A|B>_<D1..D5>.json`
- **For the later SDK backend, verified offline** (`.venv/bin/python sdk_shape_spike.py`, against a mock transport):
  - SDK 2.13 sends `output_config: {effort, format}` and `fallbacks: "default"` through `client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"])`;
  - the header is `anthropic-beta: server-side-fallback-2026-07-01`;
  - `fallbacks` is only accepted on the beta client;
  - the SDK uses `httpx2`, not `httpx`, which matters when mocking in pytest.

## Chosen approach (revised: the entry point is a Claude Code session)
**The user's decision**: the entry point is a Claude Code session. It calls a claim-verification subagent, which runs the retrieval and the Sol verification. The Python program is a **toolkit with no model calls**. The file-based `LLMStep` / exit-3 design from the previous revision is dropped.

**Flow**:
1. **Session (in chat)**:
   - takes the claim and decomposes it;
   - shows the numbered statements to the user and applies their edits: drop, edit, add, flip load-bearing, or give feedback and re-decompose (at most 3 rounds);
   - runs the falsifiability check on statements the user edits or adds;
   - writes `confirmed.json`.

   The user's approval of what the claim means stays here because it is interactive.
2. **`claim-verifier` subagent** (Sonnet 5.5, effort high), given the run folder:
   1. for each statement, `fc retrieve "<query>" --k 5 --json`, as many queries as it needs;
   2. writes `verdicts.json`: evidence first, verbatim quotes, then the verdict;
   3. `fc finalize <run>`: code decides, and can only move a statement toward `unknown`;
   4. `fc judge <run>`: Sol scores the final answer;
   5. `fc finalize <run> --judge`: applies the low-score policy;
   6. returns a short summary.
3. **Session**: reads `<run>/final.json` and `<run>/scores.json` **from disk**, never from the subagent's summary, and shows the per-statement rows, the overall verdict and the rule that produced it, and Sol's scores.

### Toolkit: `fc` (deterministic, no LLM)
- `fc fetch`: builds `data/corpus.json` (committed; 48 documents, `dropped_ids` logged) and the FTS5 index `data/index.sqlite`.
- `fc retrieve "<query>" [--k 5] --json` returns `RetrievalResult`. The settings are unchanged from spike 2.
- `fc finalize <run> [--judge]`:
  - validates `verdicts.json` against the schema;
  - **re-runs every query listed in `verdicts.json`** against the same deterministic index. The own-passage check therefore never trusts the subagent's word about what it retrieved;
  - applies the N4 quote check, the conflict rule and the strict ordered aggregation;
  - writes `final.json`, `transcript.md`, `trace.jsonl` and `checks.json`.
- `fc judge <run>` wraps `codex_review.py judge --model gpt-6-sol` with the run's transcript, trace and checks. It runs with the project root as its cwd, so the rubric override is found. It writes `scores.json`.
- `fc schema <confirmed|retrieval|verdicts|final|scores>` prints the JSON Schema; the pydantic models are the single source.
- `fc eval prepare|score`: see Evals below.

### Typed contracts
| Contract | From -> to | Carries |
| --- | --- | --- |
| `ConfirmedStatements` (`confirmed.json`) | session -> subagent | `claim`; `statements[] {id, text, load_bearing, query, kind (display only), mark: confirmed/user-edited/user-added}`; `proposed[]`, `edits[]`, `rounds`, `source: chat/case` |
| `RetrievalResult` (stdout) | `fc retrieve` -> subagent | `query`, `k`; `hits[] {passage_id, doc_id, title, score, text}` |
| `Verdicts` (`verdicts.json`) | subagent -> `fc finalize` | `statements[] {id, queries[], evidence[] {passage_id, quote, stance: supports/contradicts}, verdict, reason}` |
| `FinalAnswer` (`final.json`) | `fc finalize` -> session | `claim`; `overall {verdict, rule}`; `statements[] {id, text, load_bearing, mark, model_verdict, verdict, downgrade_reason (quote_failed/no_hits/conflict/judge_flag/null), evidence[] {doc_id, title, quote, stance}, dropped_quotes[]}`; counts (confirmed, edited, dropped); `judge` (null until `--judge`) |
| `JudgeScores` (`scores.json`) | `fc judge` -> `fc finalize --judge`, session | the 6 dimensions `{score, evidence}`, plus a new `flagged_statements[]` (ids Sol found overreaching or not following from their quotes), `model`, `seconds` |

**Later SDK entry point**: a Python driver (`fc check`) makes the decomposition and verdict calls with the Anthropic SDK (the request shape proven in spike 6) and calls the same `retrieve`, `finalize` and `judge` functions with the same contracts. That is the path to "use an LLM via API" without a Claude Code session.

### Sol at runtime on every claim
- **Cost and latency**: 1 Codex call per claim, **about 14 s** (one measurement). It is billed to the ChatGPT plan's Codex quota, not per token. Codex must be signed in wherever the subagent runs.
- **Rubric change**: at runtime there is no gold label. The rubric reads the gold label and the label checks only when present (evals), judges the 6 dimensions from the quotes alone, and adds `flagged_statements`.
- **When Sol scores low**:

| Option | Behaviour | Trade-off |
| --- | --- | --- |
| A. Attach the scores only | The verdicts are unchanged; the scores are shown | Simplest, but a flagged overreach still ships as the verdict |
| **B. Downgrade the flagged statements to `unknown` (recommended)** | If `statement_verdicts`, `overreach` or `evidence_relevance` is 2 or lower, the statements in `flagged_statements` become `unknown` (`judge_flag`), and code re-aggregates | Deterministic and one-directional: a judge can only remove support, never add it. Costs no extra call |
| C. One revision round, then downgrade | The subagent revises the flagged statements once, `finalize` and `judge` run again, and anything still flagged becomes `unknown` | Best recall, but adds a verdict pass and about 14 s, and the subagent sees the judge's critique (risk of teaching to the judge) |

  **Open for the user in I3**: A, B or C.

### Where the subagent and the rubric live (open for the user)
| Option | How | Trade-off |
| --- | --- | --- |
| **A. `fact-checker/agents/claim-verifier.md` (recommended)** | Project code. The session reads it and passes it as the prompt to a general-purpose subagent, with model `sonnet` | Matches the workspace rule that product agents are project code. There is no frontmatter, so tools and model are set by the session at each call |
| B. `fact-checker/.claude/agents/claim-verifier.md` | Loaded natively by Claude Code | Needs a session opened in the project, which the project's CLAUDE.md forbids. Also breaks "`.claude/` only at the root" |
| C. `~/.claude/agents/claim-verifier.md` | A user-level agent | Lives outside both repos, so it is not versioned with the code it drives |

The rubric is unchanged: `fact-checker/.claude/review-passes/judge.md` (codex_review.py resolves it from the cwd). It still needs the user to accept the exception to the workspace `CLAUDE.md`. The alternative is a new workspace pass.

### Prompts (from spike 6)
- **Decomposition**:
  - add a framing_bias only when a loaded word, an absolute or causal wording literally appears in the claim, and quote that word in `implied_by`;
  - no statement may be entailed by another one;
  - prefer 1 to 3 statements, with 5 as a hard cap that the session enforces;
  - `kind` is for display only.
- **Where decomposition runs**: the settled setting is Sonnet 5.5 at high effort for every LLM step. If the session itself is not on Sonnet 5.5, it delegates decomposition and the falsifiability check to a short Sonnet subagent and keeps the confirmation in chat. **Open for the user.**
- **The verdict prompt** in `spikes/llm/verify_cases.md` becomes part of `claim-verifier.md`, with the tool steps added.

### Unchanged from the spikes
- **Retrieval**:
  - SQLite FTS5 `porter unicode61`, BM25;
  - **2-sentence windows, stride 1**, the title in front, plus 1 metadata passage per paper;
  - the query is the statement's text plus its `query` keywords, joined with OR and stopwords removed;
  - **k = 5, at most 2 passages per paper**;
  - behind `Retriever.search(query, k)`, with dense/hybrid as the scale-up option.
- **Threshold**: **no score threshold** (falsified). 0 hits for every query gives `unknown` (`no_hits`).
- **Quote rule (N4)**, applied to both the quote and the cited passage:
  1. NFKC;
  2. curly quotes to ASCII, dashes (`–`, `—`, `‐`, `‑`, `−`) to `-`, NBSP to a space;
  3. strip LaTeX: `\cmd{x}` becomes `x` for textbf/textit/emph/url/href/mathrm/text/mathbf, `\%` and similar become `%`, `$` is removed, `\times` becomes `x`;
  4. collapse whitespace and casefold;
  5. a hyphen between letters (`(?<=[a-z])-\s*(?=[a-z])`) becomes a space. A sign before a number is kept;
  6. trim punctuation at both edges.

  Then: no ellipsis, **at least 5 words**, a substring of a passage that re-retrieval returns for one of *that* statement's queries. There is no fuzzy fallback.
- **Conflict and aggregation**: unchanged from 01, strict and ordered, enforced in `fc finalize`.

### Evals
- `fc eval prepare <run>` writes one run folder per case, with `confirmed.json` built from the case's approved statements (`source: case`).
- The session drives the same `claim-verifier` subagent on each case, at most 3 at a time.
- `fc eval score <run>` reads every `final.json` and `scores.json` and reports:
  - accuracy and the confusion matrix;
  - per-statement accuracy;
  - the quote-check pass rate;
  - recall@k on `gold_doc_ids`;
  - the mean Sol score per dimension;
  - how often the judge policy changed a verdict.
- The loop logic and the grounding rules are tested in pytest without any LLM.

## Risks and still unverified
- **Risk:** "use an LLM via API" and "run the program and verify example claims" are met only through a Claude Code session, until the SDK entry point exists. `fc` alone gives no verdicts.
- **Risk: subagent permissions**. The subagent needs Bash permission for `fc` and for `codex` (through `fc judge`). Codex needs network access and its sign-in under `~/.codex`. A sandboxed subagent Bash call may block it.
- **Risk: quote discipline**. The subagent may paraphrase, cite a passage it never retrieved, or skip `finalize` or `judge`. `finalize` drops bad quotes and re-runs retrieval itself, and the session reads `final.json` and `scores.json` from disk. A missing `scores.json` shows as "not judged", never as a pass.
- **Risk: latency per claim**. Retrieval takes milliseconds. Subagent start-up plus the high-effort verdicts are not measured. Sol takes about 14 s, and option C adds one more verdict pass and judge call.
- **Unverified**:
  - end-to-end wall time per claim;
  - whether the session can set the subagent's model and **effort** (Sonnet 5.5, high) on every call;
  - whether the subagent can run `fc judge` (Codex) from inside Claude Code;
  - the runtime rubric (no gold) and `flagged_statements`: not run yet; spike 4 judged one fake case that had a gold label;
  - the tightened decomposition prompt (not rerun);
  - the falsifiability check;
  - accuracy beyond the 6 self-written verdict cases;
  - the SDK path (server-side effort, schema, refusals, fallbacks; needs a key);
  - whether a subagent behaves like a raw API call;
  - retrieval on more than 17 statements;
  - the conflict-rule misfire (V4 has different setups);
  - Sol's agreement with hand grades, and the hard-coded dimension names in `/eval-calibrate`.
