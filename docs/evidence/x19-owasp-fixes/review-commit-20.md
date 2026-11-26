<!-- pass: commit | model: gpt-6-luna | base: commit 700c11409e37a6b126815f6c1be6350ee95ee04c | exit: 0 | 2026-11-25 19:10:45 -->
VERDICT: PASS
C1: PASS — The message states one goal: redact known secrets in `checks.json` from `run-claims`.
C2: PASS — `src/fact_checker/cli.py` serializes checks and redacts known secrets before writing `checks.json`, as promised.
C3: PASS — The diff only changes how `checks.json` is written, matching the message.
C4: PASS — This strengthens the planned US-8 guarantee that run artifacts never expose secrets.
C5: N/A — The diff does not add, change, or remove tests.