<!-- pass: commit | model: gpt-6-luna | base: commit b446e4a2d4b22705e958c8fca402fb6414a52245 | exit: 0 | 2026-11-25 19:44:26 -->
VERDICT: CHANGES

C1: PASS — The subject states one goal: explain “load-bearing” in a visible hint beside the statements table and result tags.

C2: FAIL — The result tag is linked to the visible hint only when at least one statement is load-bearing; when none are load-bearing, no hint is rendered, so the stated per-tag explanation and description are not delivered. The relevant diff line is `      {answer.statements.some((statement) => statement.load_bearing) && <LoadBearingHint id={hintId} />}`.

C3: PASS — The diff adds the explanation and accessibility links described by the message; it adds no separate behavior or feature.

C4: PASS — The changes implement planned US-1: a visible explanation and accessible description for the term on the statements table and result view.

C5: N/A — The diff adds no tests and does not delete, skip, or loosen any tests.