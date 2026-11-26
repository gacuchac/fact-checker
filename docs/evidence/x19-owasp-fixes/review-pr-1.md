<!-- pass: pr | model: gpt-6-sol | base: dev | exit: 0 | 2026-11-25 19:06:52 -->
VERDICT: CHANGES

1. [S05.yaml](/Users/tamarmilstein/Developing/fact-checker/evals/cases/S05.yaml:8), [evals.py](/Users/tamarmilstein/Developing/fact-checker/src/fact_checker/evals.py:234), [cli.py](/Users/tamarmilstein/Developing/fact-checker/src/fact_checker/cli.py:265): If S05 detects a leaked secret, the CLI still writes the raw result and spans to `outcome.json`, preserving the secret it just flagged.

2. [cli.py](/Users/tamarmilstein/Developing/fact-checker/src/fact_checker/cli.py:257), [cli.py](/Users/tamarmilstein/Developing/fact-checker/src/fact_checker/cli.py:273): A misspelled `--case` selects no cases and exits successfully, so an on-demand eval can report success without running a check.