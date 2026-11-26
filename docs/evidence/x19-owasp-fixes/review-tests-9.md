<!-- pass: tests | model: gpt-6-luna | base: commit ba7a4bc5fc8766d0acff50fa215aad6c141989fc | exit: 0 | 2026-11-25 18:33:23 -->
VERDICT: CHANGES

T1: PASS — `tests/test_evals.py:503` checks that statement-mode `prepare` and `score` exclude claim-mode cases through the CLI.

T2: FAIL — The tests do not assert that `run-claims` selects only `mode: claim` cases or honors `--case ID`, both required by the unit contract. The tested invocation is `main(["eval", "run-claims", str(cases), str(out)])`.

T3: PASS — `tests/test_evals.py:520` checks written outcome and checks files, exit status, and that secrets and prompts are excluded from the outcome.

T4: PASS — `tests/test_evals.py:532` asserts that the secret value does not appear in any written output file; `tests/test_evals.py:520` also checks the command’s result and artifacts.