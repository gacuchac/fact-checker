<!-- pass: tests | model: gpt-6-luna | base: commit 8839f9012ce160c742ccba9f5b18cd715980d6ae | exit: 0 | 2026-11-25 18:10:30 -->
VERDICT: PASS

T1: PASS — [test_api.py](/private/var/folders/j6/q0mz0r8j0zv1_8w69zdsnx8h0000gn/T/tmpko1lhl0c/tree/tests/test_api.py:211) tests the public claim and verify endpoints and their expected responses.

T2: PASS — Together, the tests cover rejecting claims at the cap before decompose, counting unverified runs, and allowing verification of a claim started under the cap; the red run lists all four changed tests as failing before implementation.

T3: PASS — The tests require meaningful status codes, model-call counts, run counts, and verification behavior; a trivial stub would not satisfy them.

T4: PASS — The tests would catch a wrong cap decision, a skipped or repeated decompose call, an incorrectly created run, or verification being blocked by the cap; the assertions are against observable behavior.