<!-- pass: pr | model: gpt-6-sol | base: dev | exit: 0 | 2026-11-25 19:12:13 -->
VERDICT: CHANGES

1. `src/fact_checker/eval_runner.py:69`, `src/fact_checker/cli.py:276-279`, `src/fact_checker/tracing.py:92-100`: `outcome.json` retains full system prompts in the LLM span inputs, contradicting the command’s attempt to omit prompts from the saved outcome.
2. `src/fact_checker/evals.py:205-209`, `src/fact_checker/evals.py:235-240`, `src/fact_checker/cli.py:253-255`: Secrets containing JSON-escaped characters, such as quotes, can evade both `forbid_secrets` and the file redaction because each searches serialized JSON for the unescaped value.