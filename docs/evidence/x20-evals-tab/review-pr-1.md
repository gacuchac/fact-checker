<!-- pass: pr | model: gpt-6-sol | base: dev | exit: 0 | 2026-11-25 19:39:22 -->
VERDICT: CHANGES

1. `src/fact_checker/eval_cases.py:52`, `web/src/pages/EvalsPage.tsx:68`, `src/fact_checker/evals.py:90`: Statements-mode `gold_doc_ids` are scored as aggregate document recall, but the tab labels every one “Must cite,” incorrectly presenting them as required per-case citations.