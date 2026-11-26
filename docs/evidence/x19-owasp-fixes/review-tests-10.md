<!-- pass: tests | model: gpt-6-luna | base: commit f46bf748b67233dfaffe8885a89658c614a2d963 | exit: 0 | 2026-11-25 18:35:11 -->
VERDICT: CHANGES

T1: PASS — The added test exercises the public CLI, filters to claim-mode cases, and checks its output directories in [tests/test_evals.py](/private/var/folders/j6/q0mz0r8j0zv1_8w69zdsnx8h0000gn/T/tmpr4eiumqi/tree/tests/test_evals.py:585).

T2: FAIL — It checks case selection, but this diff adds no coverage for the planned exit codes, outcome/check files, or secret redaction. The existing tests for those behaviors were not changed here. `+    assert sorted(p.name for p in out_all.iterdir()) == ["C1", "C2"]`

T3: PASS — The test asserts which case directories the command actually creates, so a stub that creates no outputs would fail. Evidence: [tests/test_evals.py](/private/var/folders/j6/q0mz0r8j0zv1_8w69zdsnx8h0000gn/T/tmpr4eiumqi/tree/tests/test_evals.py:585).

T4: FAIL — The added assertions would not catch the command selecting a case but writing incorrect results or returning the wrong exit code. `+    main(["eval", "run-claims", str(cases), str(out_all)])`