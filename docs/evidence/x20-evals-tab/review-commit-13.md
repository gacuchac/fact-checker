<!-- pass: commit | model: gpt-6-luna | base: commit 41b36bc30578edaf6ff4c429375b0bf3e2b6fc83 | exit: 0 | 2026-11-25 19:41:35 -->
VERDICT: PASS
C1: PASS — The subject states one clear goal: fix how statements-mode gold docs are shown.
C2: PASS — The diff maps statements-mode gold docs to `expected_docs` and renders them as “Expected sources” in [EvalsPage.tsx](/private/var/folders/j6/q0mz0r8j0zv1_8w69zdsnx8h0000gn/T/tmp7pmqa117/tree/web/src/pages/EvalsPage.tsx:70).
C3: PASS — The added field is used only for statements-mode expected sources; the claim-mode “Must cite” and “Must be found by search” rows remain separate in [eval_cases.py](/private/var/folders/j6/q0mz0r8j0zv1_8w69zdsnx8h0000gn/T/tmp7pmqa117/tree/src/fact_checker/eval_cases.py:53).
C4: PASS — Showing statement gold docs as expected sources advances the Evals tab’s goal of clearly presenting eval case information.
C5: N/A — This diff changes no tests.