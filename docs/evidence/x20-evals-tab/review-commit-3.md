<!-- pass: commit | model: gpt-6-luna | base: commit 21ef530d5d4ae7cb196de8e2de70465effed6e8c | exit: 0 | 2026-11-25 19:27:45 -->
VERDICT: PASS
C1: PASS — `web/src/pages/EvalsPage.tsx:82` defines the Evals page as a single feature with cards, filters, and loading, empty, and error states.
C2: PASS — `web/src/pages/EvalsPage.tsx:20` renders separate labelled document rows, case notes, mode filters, and error messages as described in the commit message.
C3: PASS — `web/src/App.tsx:17` adds the Evals navigation link and route; the other changes support that page.
C4: PASS — `web/src/App.tsx:17` adds the requested Evals tab alongside the existing app tabs.
C5: N/A — No tests are added, removed, skipped, or loosened in this diff.