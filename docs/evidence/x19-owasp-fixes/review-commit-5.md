<!-- pass: commit | model: gpt-6-luna | base: commit 5002223ecc0e19ea19100c6cb0b395b10206950c | exit: 0 | 2026-11-25 18:11:36 -->
VERDICT: CHANGES

C1: PASS — The message states one clear goal: count the daily cap by claims started.

C2: PASS — `src/fact_checker/api/routes.py:91` checks the cap before `start_claim`, and `src/fact_checker/api/routes.py:121` removes the cap check from verification, matching the message and plan.

C3: PASS — The diff changes only the daily-cap behavior and its documentation, as the message says.

C4: PASS — The change implements US-3 from the plan: enforce the cap when claims start and do not count a started claim again at verification.

C5: N/A — The diff does not change or remove tests.