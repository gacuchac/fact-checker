<!-- pass: impl | model: gpt-6-luna | base: HEAD | exit: 0 | 2026-11-25 18:09:35 -->
VERDICT: PASS
I1: PASS — `src/fact_checker/api/routes.py:97` and `src/fact_checker/api/routes.py:107` implement unit 3’s length and confirm-round checks, in the specified order after status validation and before `confirm_claim`; the diff changes only a named file.
I2: PASS — `src/fact_checker/api/routes.py:98` checks the general 500-character limit, and `src/fact_checker/api/routes.py:116` checks the general three-round limit; neither targets test inputs or hard-codes expected outputs.
I3: PASS — `src/fact_checker/api/routes.py:107` keeps `post_confirm`’s existing parameters, and the diff adds no public function signature or output-shape change.