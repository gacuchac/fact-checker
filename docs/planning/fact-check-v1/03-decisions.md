# Decisions: fact-check-v1 (I3)

Each decision is in the user's words, with the question it answers.

## D1. What happens when Sol scores a final answer low?
User: "go back to the main agent with the reasoning"
Read as: the claim-verifier subagent does not downgrade or revise on its own. It returns Sol's scores and Sol's reasoning (the flagged statements and the evidence for each score) to the main session, which shows them alongside the verdict and decides what to do next.

## D2. Where does the claim-verifier subagent definition live?
User: "use recommendation"
Read as: `fact-checker/agents/claim-verifier.md`, project code that the main session passes as the subagent's prompt (not under `.claude/agents/`).

## D3. May the Sol rubric live in the project's .claude/ folder?
User: "rubric can be in fact-checker/.claude/"
Read as: `fact-checker/.claude/review-passes/judge.md` is approved as an exception to the workspace rule that `.claude/` lives only at the root.

## D4. Which model does which step?
User: "opus for decompossing, sonnet for finding"
Read as: the main session on Opus breaks down the claim and runs the confirmation with the user. The claim-verifier subagent on Sonnet 5.5 at high effort does retrieval and verdicts. This replaces the earlier "Sonnet 5.5 high for every LLM step".

## D5. Do you approve the five contracts in architecture.md?
User: "approved"
Read as: architecture.md (ConfirmedStatements, RetrievalResult, Verdicts, FinalAnswer, JudgeScores; public functions; build order) is the approved design. A Sol flag never changes a verdict. It sets `needs_attention`, and the main session brings Sol's reasoning to the user.

## D6. When are the evals written?
User: "evals can be written in parallel."
Read as: the eval cases are written alongside the build rather than before it, so they don't block the 30-minute demo path.

## D7. What must the evals evaluate?
User: "evals should evaluate at least:
1. did the agent follow the methodology.
2. did it parse the user's intent and got approval before retireval
3. did it repharse anything in a way that breaks the meaning of the original text
4. did it miss any abstracts that are important.
5. is every claim sustained by evidence from the abstracts
6. did reviewer follo the rubric
7. did the final output match what was given to the reviewer
8. did the user approve of the output"
Read as: the evals judge the whole run (main session, verifier, Sol and user), not only the final answer. They need a simulated user for 2 and 8, gold documents per case for 4, and the trace plus the scores file for 6 and 7.

## D8. Is the 6-case seed enough?
User: "6 cases are agood seed, but expand"
Read as: start from spike-6's V1–V6 and expand to the full set (24–30) in parallel with the build.

## D9. Do the two defaults stand (user-added statements skip the implied_by check; rule 0: no load-bearing statement gives unknown)?
User: "both defaults stand, start the build"

## D10. Architecture change for D7 eval instrumentation (architecture-change-planner.md)
User: "approve 1a, 3a, 4a with Luna"
Read as:
- 1a: the `fc` CLI layer writes `<run>/events.jsonl` (timestamps, the doc ids `retrieve --run` returned, and the `final_sha256` that finalize, judge and show read). `fc show` renders the final answer deterministically, and the session pastes it verbatim.
- 3a: an eval harness drives a headless Claude Code session (`claude -p --resume`), with the workspace eval-runner as the simulated user.
- 4a: the eval rubric lives at `fact-checker/evals/judge/.claude/review-passes/judge.md` (D3's exception widened to this second folder) and is run from that folder. The eval judge runs on GPT-6 Luna; Sol stays the runtime reviewer.
