<!-- pass: impl | model: gpt-6-luna | base: HEAD | exit: 0 | 2026-11-25 18:01:46 -->
VERDICT: PASS
I1: PASS — [base.py](/Users/tamarmilstein/Developing/fact-checker/src/fact_checker/llm/base.py:23) adds the requested redaction and applies it to `LLMError`; the only changed code file is named in the unit’s Files list.
I2: PASS — [base.py](/Users/tamarmilstein/Developing/fact-checker/src/fact_checker/llm/base.py:12) uses a general token pattern and contains no test-specific inputs or expected outputs.
I3: PASS — [base.py](/Users/tamarmilstein/Developing/fact-checker/src/fact_checker/llm/base.py:29) adds an exception constructor without changing a public function’s signature or output shape.