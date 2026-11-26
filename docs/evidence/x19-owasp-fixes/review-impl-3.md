<!-- pass: impl | model: gpt-6-luna | base: HEAD | exit: 0 | 2026-11-25 18:11:05 -->
VERDICT: PASS
I1: PASS — The changes stay within unit 4’s listed files and implement the claim-start cap, remove the verify cap, and update the requested docs (`src/fact_checker/api/routes.py:88`, `src/fact_checker/api/routes.py:136`).
I2: PASS — The cap uses the configured daily count and cap; no test-specific inputs or expected outputs are hard-coded (`src/fact_checker/api/routes.py:92`).
I3: PASS — The edited route function signatures are unchanged (`src/fact_checker/api/routes.py:88`, `src/fact_checker/api/routes.py:136`).