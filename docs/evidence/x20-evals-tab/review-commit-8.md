<!-- pass: commit | model: gpt-6-luna | base: commit 3cc7a96671a031da3e2b476cd2196cd7bde3592b | exit: 0 | 2026-11-25 19:32:40 -->
VERDICT: PASS
C1: PASS — `src/fact_checker/eval_cases.py:84` supports the message’s single goal: make security checks read as plain sentences and omit document rows.
C2: PASS — `src/fact_checker/eval_cases.py:84-86` omits the two document-row keys, while `src/fact_checker/eval_cases.py:88-92` renders known evidence stances as plain sentences.
C3: PASS — `src/fact_checker/eval_cases.py:68-92` changes only how security check lines are generated, as the message describes.
C4: PASS — `src/fact_checker/eval_cases.py:84-86` keeps document requirements out of the check sentences, consistent with the plan’s separate “Must cite” and “Must be found by search” rows.
C5: PASS — The diff changes no tests and does not weaken or remove any.