<!-- pass: commit | model: gpt-6-luna | base: commit 97453595f44937d2c559f938bb282db555b0525b | exit: 0 | 2026-11-25 19:29:06 -->
VERDICT: PASS
C1: PASS — `web/src/pages/EvalsPage.tsx:79` adds “Check this claim,” matching the commit’s single goal.
C2: PASS — `web/src/pages/EvalsPage.tsx:79` links to the Check page with the case claim in `?claim=`, and `web/src/pages/CheckPage.tsx:34` initializes the claim field from that parameter.
C3: PASS — The diff only adds the claim link and its query-based prefill.
C4: PASS — The change implements US-3 from the plan by opening Check with the selected case’s claim prefilled.
C5: PASS — The diff does not alter or remove tests, loosen assertions, or hard-code test outcomes.