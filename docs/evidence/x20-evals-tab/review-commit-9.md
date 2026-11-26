<!-- pass: commit | model: gpt-6-luna | base: commit 08abd0ffb9146d2614862cac05067008b242ff7c | exit: 0 | 2026-11-25 19:32:47 -->
VERDICT: PASS

C1: PASS — The message sets one goal: classify eval cases as Security or Fact-check using OWASP tags.

C2: PASS — The diff applies that category to both the card tag and filter in [EvalsPage.tsx](/private/var/folders/j6/q0mz0r8j0zv1_8w69zdsnx8h0000gn/T/tmpozwkv0zw/tree/web/src/pages/EvalsPage.tsx): cases with OWASP tags are Security; others are Fact-check.

C3: PASS — The diff changes only category labels and filtering, matching the stated goal.

C4: PASS — The change supports US-2’s Security/Fact-check filter and card labeling in the plan.

C5: N/A — The diff changes no tests.