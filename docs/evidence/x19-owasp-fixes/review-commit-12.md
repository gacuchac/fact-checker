<!-- pass: commit | model: gpt-6-luna | base: commit 2c23d5c84586186d8a6f52cbee51c64f1ce405aa | exit: 0 | 2026-11-25 18:37:36 -->
VERDICT: FAIL
C1: PASS — The subject states one clear goal: limit both statement input fields to 500 characters.
C2: PASS — The diff adds `maxLength={500}` to both inputs named in the message (`web/src/components/StatementsTable.tsx:39` and `web/src/components/StatementsTable.tsx:119`).
C3: PASS — The diff only adds the stated input limits.
C4: PASS — This implements the planned web input limits for US-1.
C5: N/A — The diff changes no tests.