<!-- pass: pr | model: gpt-6-sol | base: dev | exit: 0 | 2026-11-25 19:08:51 -->
VERDICT: CHANGES

1. `src/fact_checker/evals.py:183`, `src/fact_checker/quotes.py:34`, `evals/cases/S01.yaml:10`: The S01 scorer checks raw, case-sensitive substrings while the pipeline accepts quotes after normalization, so a valid kept quote can falsely fail `quotes_verbatim`.
2. `src/fact_checker/evals.py:280`, `src/fact_checker/cli.py:279`, `src/fact_checker/cli.py:280`: A failed run’s raw error can enter the `completed` check detail, but the CLI redacts only `outcome.json`, so `checks.json` can expose a non-`sk-` secret.