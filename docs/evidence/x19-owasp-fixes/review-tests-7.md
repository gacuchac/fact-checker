<!-- pass: tests | model: gpt-6-luna | base: commit 5456bf06018c3ba0f2539807d10e7c181a4c20c9 | exit: 0 | 2026-11-25 18:28:57 -->
VERDICT: PASS

T1: PASS — `tests/test_evals.py:387` feeds clean and leaking outcomes through `score_claim_case` and checks the public check results.

T2: PASS — `tests/test_evals.py:409` covers leakage across outputs, secrets, prompt overlap, required hit documents, and the plan’s stated budget limits.

T3: PASS — `tests/test_evals.py:420` checks that the secret is absent from the failed check’s detail, beyond merely asserting failure.

T4: PASS — `tests/test_evals.py:397` pairs passing and failing outcomes for each leakage key, and `tests/test_evals.py:416` checks budget thresholds at and just beyond the limits.