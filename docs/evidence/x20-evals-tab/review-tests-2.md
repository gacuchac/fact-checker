<!-- pass: tests | model: gpt-6-luna | base: commit b78553aae161b5343c4592f199ea23bece02c2ba | exit: 0 | 2026-11-25 19:21:39 -->
VERDICT: PASS

T1: PASS — [tests/test_eval_cases.py](/private/var/folders/j6/q0mz0r8j0zv1_8w69zdsnx8h0000gn/T/tmpz7naal1y/tree/tests/test_eval_cases.py:107) checks claim-mode results through `case_view`’s returned fields and errors.

T2: PASS — [tests/test_eval_cases.py](/private/var/folders/j6/q0mz0r8j0zv1_8w69zdsnx8h0000gn/T/tmpz7naal1y/tree/tests/test_eval_cases.py:169) covers the claim-mode docs, flags, checks, and error cases named in the unit’s done line; all added tests are red in the supplied run.

T3: PASS — [tests/test_eval_cases.py](/private/var/folders/j6/q0mz0r8j0zv1_8w69zdsnx8h0000gn/T/tmpz7naal1y/tree/tests/test_eval_cases.py:117) asserts concrete output values that a trivial stub would not satisfy.

T4: PASS — [tests/test_eval_cases.py](/private/var/folders/j6/q0mz0r8j0zv1_8w69zdsnx8h0000gn/T/tmpz7naal1y/tree/tests/test_eval_cases.py:196) checks malformed security and missing-claim errors alongside correct output behavior, without constraining internals.