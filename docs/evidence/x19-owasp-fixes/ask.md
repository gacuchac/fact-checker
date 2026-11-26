User request (2026-11-25), verbatim: "fix all failutrs"
Context: the failures of the OWASP LLM Top 10 eval run in ~/Developing/.claude/runs/fact-checker/x16-owasp-evals/results.md (cases S06, S13a, S13b, S14, S15, S16b; definitions in draft-cases.md, runnable checks in run_det.py).

User's answers (AskUserQuestion, 2026-11-25), verbatim choices:
- Daily cap: "Claims started (Recommended)" = one cap on claims per day; each claim includes its decomposition, its confirm rounds and one verification.
- Confirm cap: "3 rounds (Recommended)" = matches the existing rounds <= 3 field, which is declared but never enforced.
- Trace access: "Everyone with the code (Recommended)" = keep as is.
- Eval runs: "Split (Recommended)" = the deterministic and browser cases go in pytest/CI on every PR; the 9 model cases go in evals/ and run on demand.

Defaults stated by the main session and not objected to:
- Edited or added statement text gets the same 500-character limit as the claim, rejected with 422 before any model call.
- Provider error text is redacted (no key fragments) before it is stored in runs or spans or returned in a 502.
- The rate limiter keys on the real client IP behind Railway's proxy: Railway's edge sets X-Real-IP (docs.railway.com/networking/public-networking/specs-and-limits). Read it only when a setting names that header (e.g. FC_CLIENT_IP_HEADER=X-Real-IP on Railway), otherwise request.client.host.
- Wrong access codes are throttled after 10 per minute per client (429).
