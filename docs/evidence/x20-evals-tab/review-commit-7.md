<!-- pass: commit | model: gpt-6-luna | base: commit 47c226308e19d72672de1859c6c4cafd00b35930 | exit: 0 | 2026-11-25 19:31:41 -->
VERDICT: CHANGES

C1: PASS — The subject states one clear goal: “security check sentences skip the doc rows and read as plain sentences.”

C2: PASS — The test-only diff specifies that document rows are excluded from `checks` and evidence stances read as plain sentences in [tests/test_eval_cases.py](/private/var/folders/j6/q0mz0r8j0zv1_8w69zdsnx8h0000gn/T/tmp87r0g4p9/tree/tests/test_eval_cases.py:204).

C3: PASS — The added tests cover only those sentence and document-row behaviors.

C4: PASS — Separating document rows from security-check sentences advances the planned Evals display, which labels “Must cite” and “Must be found by search” separately.

C5: FAIL — The existing S11 test drops its expectation that the search requirement appears in `checks`: `-    assert "Search must find: 2307.03172v3" in v.checks` This loosens a test without the stated architecture or red-phase exception.