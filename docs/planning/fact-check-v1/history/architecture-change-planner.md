# Proposed architecture change: D7 eval instrumentation (fact-check-v1)

Status: proposed by the planner (I3 update for D6–D8). This is not applied: architecture.md is unchanged.

## What must change
D7 asks the evals to judge the whole run. Four of its dimensions need evidence that the approved architecture doesn't produce:

| D7 dimension | Evidence needed | What architecture.md has today |
| --- | --- | --- |
| 1 methodology order, 2 approval before retrieval | timestamps for each `fc` step and for the chat turns, including the subagent's `fc retrieve` calls | `fc retrieve` writes only stdout. Nothing records when or by whom each step ran |
| 4 missed abstracts | the doc ids retrieved for each statement | can be rebuilt by re-running `verdicts.queries`, but queries the verifier ran and didn't list are invisible |
| 7 shown output = judged output | a hash of the `final.json` that Sol judged, and of the one the session displayed | the session renders free-form from `final.json`. No hash is kept |
| 2, 8 user approval | a driven user conversation | the entry point is an interactive Claude Code session, with no programmatic driver |

Proposed additions. None changes the five contracts or the five public functions.
1. **A run event log, `<run>/events.jsonl`**, written by the `fc` CLI layer only, so the functions stay pure.
   - One line per command: `{ts, cmd, ok}`.
   - `retrieve` adds `doc_ids`, and takes a new optional `--run <run>` flag that the verifier prompt uses.
   - `finalize`, `judge` and `show` add the `final_sha256` they read.
2. **`fc show <run>`**: a pure renderer in `report.py` of `final.json` and `scores.json`. The runbook has the session paste its output verbatim.
3. **An eval harness, `harness/`**: project code that meets the workspace harness contract (loop.md 5b).
   - It drives a headless Claude Code session (`claude -p --resume`, runbook prompt, `FC_RUNS_DIR`) for each eval case.
   - It writes `trace.jsonl` turn, tool and model events.
   - The case's fc run folder is `<eval run dir>/<case>/fc/`, so fc's `transcript.md`, `trace.jsonl` and `checks.json` don't collide with the harness's files of the same names.
4. **The eval rubric's location**: a second `judge.md`, because `codex_review.py` resolves the single `judge` pass from `<cwd>/.claude/review-passes/judge.md`, and D3 already uses `fact-checker/.claude/` for Sol's runtime rubric.

## Why
These are the user's decision D7, items 1, 2, 4, 7 and 8. Without them, those dimensions can only be judged by a model reading transcripts, and could not be checked by code.

## What it affects
- **architecture.md**:
  - the components diagram gains the harness and the event log;
  - "Public functions" gains a renderer for `fc show`. It is module-internal, but the session depends on its output;
  - the CLI list gains `show` and `retrieve --run`;
  - the risks gain the headless-session seam;
  - the eval section names the second rubric location.
- **`agents/claim-verifier.md`** (fc-07): the retrieve command gains `--run <run>`. If this is approved after fc-07 is built, fc-10 updates the prompt and the runbook.
- **The workspace rule on `.claude/`**: option 4a below widens D3's exception to a second project `.claude/` folder.
- **New seam**: headless `claude -p` launching the Sonnet subagent and running Codex without permission prompts. Unverified; the live harness smoke test is the first proof.
- **The build**: tasks fc-10, fc-11 and fc-12 in 03-solution-prd.md wait for this decision. The demo path, fc-01 to fc-07, doesn't.

## Options
- **Event evidence**:
  - **(1a) the CLI event log plus `fc show`**, as above. Recommended: deterministic and cheap, and it covers subagent calls whatever Claude Code's stream shows.
  - (1b) rely only on Claude Code's `stream-json` output, captured by the harness. This adds nothing to `fc`, but whether subagent tool calls appear there is unverified, and it doesn't work in `statements` mode.
  - (1c) let the eval judge infer order and display equality from transcripts. This adds nothing, but dimensions 1, 2 and 7 become judgement calls, which D7's wording doesn't need.
- **User simulation**:
  - **(3a) the harness over headless `claude -p --resume`**. Recommended: it is the real entry point.
  - (3b) the later SDK entry point (`fc check`) with a scripted user. It needs an API key and isn't built.
  - (3c) `statements` mode only. Dimensions 2 and 8 can't be evaluated.
- **Eval rubric location**:
  - **(4a) `fact-checker/evals/judge/.claude/review-passes/judge.md`, run with that cwd by `fc eval judge` on Luna.** Recommended now: spike 4 proved the cwd override works.
  - (4b) a new pass name in `codex_review.py`'s `PASSES`, a workspace change done as a separate root task. Recommended as the follow-up.
  - (4c) the rubric passed with `--context-file`. Codex would see two conflicting rubrics. Not recommended.
