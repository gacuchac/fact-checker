<!-- pass: commit | model: gpt-6-luna | base: commit eb05e437c73d621ab0a714d5f76debb75974fe1a | exit: 0 | 2026-11-25 19:10:24 -->
VERDICT: PASS
C1: PASS — The message states one clear goal: align `quotes_verbatim` with the pipeline’s N4 normalizer.
C2: PASS — `src/fact_checker/evals.py:184` now normalizes both quote and abstract with `normalise` before comparison, as the message says.
C3: PASS — The diff only changes the quote comparison to use the imported normalizer.
C4: PASS — This advances planned US-8, which requires `quotes_verbatim` scoring for claim cases.
C5: N/A — The diff does not change tests.