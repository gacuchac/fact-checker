<!-- pass: plan | model: gpt-6-sol | base: dev | exit: 0 | 2026-11-25 17:49:46 -->
VERDICT: CHANGES

1. **Subtask 1 (S07):** The plan puts only a jsdom test in CI and leaves the headless Chrome check optional, so the requested browser case will not run on every PR.
2. **Subtask 6 (S02):** Its case checks for a fabricated quote but omits `allowed_overall`, so it can pass even when the injected claim is marked supported.
3. **Subtask 5 (S15):** The fix depends on setting `FC_CLIENT_IP_HEADER` in Railway, but the plan leaves that as an open question; until it is set, deployed clients still share a rate limit bucket.