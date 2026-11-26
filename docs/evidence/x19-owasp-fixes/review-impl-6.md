<!-- pass: impl | model: gpt-6-luna | base: HEAD | exit: 0 | 2026-11-25 18:36:03 -->
VERDICT: CHANGES
I1: FAIL — [cli.py](/Users/tamarmilstein/Developing/fact-checker/src/fact_checker/cli.py:263) passes a temporary scratch directory as `work`, though unit 10 requires `work=out/<id>` for each case.
I2: PASS — [cli.py](/Users/tamarmilstein/Developing/fact-checker/src/fact_checker/cli.py:257) selects cases by mode and optional ID, with no test-input special-casing or hard-coded expected outputs.
I3: PASS — [cli.py](/Users/tamarmilstein/Developing/fact-checker/src/fact_checker/cli.py:214) changes only private helper signatures; no public function signature or output shape changes.