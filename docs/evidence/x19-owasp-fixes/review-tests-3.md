<!-- pass: tests | model: gpt-6-luna | base: commit 6463d93f68928efe4f1b4d3b7e8f1502f896e415 | exit: 0 | 2026-11-25 18:08:59 -->
VERDICT: PASS
T1: PASS — `tests/test_security.py:134` changes the edit ID used by the confirm helper to match the unit’s route-level confirm checks.
T2: PASS — The unit’s length and confirm-round tests are already part of the reviewed baseline; this fix corrects the helper input they depend on.
T3: PASS — The changed helper input does not assert success by itself.
T4: PASS — The corrected ID lets the existing tests expose incorrect confirm behavior while keeping them independent of the internal implementation.