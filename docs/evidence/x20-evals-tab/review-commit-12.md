<!-- pass: commit | model: gpt-6-luna | base: commit 79b6ce479d6ef8639bb5715e35847b7615182d9c | exit: 0 | 2026-11-25 19:40:57 -->
VERDICT: CHANGES
C1: PASS — The subject states one goal: clarify how statements-mode gold documents are represented.
C2: FAIL — The tests specify that statements-mode gold docs are expected sources, contrary to the plan’s contract that they are required citations; `tests/test_eval_cases.py:32` changes this to `assert v.must_cite_docs == []`.
C3: PASS — The diff only changes tests to assert the stated distinction between expected sources and required citations.
C4: FAIL — The plan explicitly maps statements-mode `gold_doc_ids` to `must_cite_docs`; the new assertions reverse that planned contract: `tests/test_api.py:371` adds `assert body[0]["must_cite_docs"] == []`.
C5: PASS — The commit adds and updates assertions; it does not hard-code outputs to game tests or delete, skip, or loosen tests.