X21 (Simple mode, web only, two units, test-first; no backend or contract change).

### 1. Explain "load-bearing" where it appears (US-1)
Files: web/src/components/StatementsTable.tsx, web/src/components/ResultView.tsx (and any other place the term shows), web/src/styles.css, web/tests.
- Next to each place "load-bearing" appears (statement review table column/toggle, result statement tag), add a short user-facing explanation: e.g. "Load-bearing: if this statement is false, the whole claim is false. Only load-bearing statements decide the overall verdict." Use an accessible pattern: a visible one-line hint near the column header / legend, plus `title` + `aria-describedby` on each tag; no hover-only information.
- Keep every existing data-testid, text and behaviour; existing tests pass unchanged.
Tests: the explanation text is rendered near the term on the Check (statements) page and on the result view, and each load-bearing tag is described by it (aria-describedby).

### 2. Readable span input/output in the Traces tab (US-2)
Files: web/src/pages/TracePage.tsx (+ a small pure formatter module if needed), web/src/styles.css, web/tests/traces.test.tsx.
- Replace the raw `JSON.stringify` <pre> dumps with a readable view: objects as labelled key/value rows (keys humanised, e.g. "passage_id" -> "Passage id"), arrays as numbered lists, long strings wrapped in a readable text block (prompts and quotes keep line breaks), numbers/booleans/null shown plainly; nesting indented with the design tokens; keep a "Show raw JSON" toggle per box for exact inspection.
- Text only: render through React text nodes, never innerHTML (S07 security tests must keep passing).
- Keep span-row/span-toggle test ids and the llm prompt display; existing tests pass unchanged.
Tests: a nested object renders as labelled rows with humanised keys; arrays as numbered items; the raw toggle shows the exact JSON; payload strings stay inert (no element created).
