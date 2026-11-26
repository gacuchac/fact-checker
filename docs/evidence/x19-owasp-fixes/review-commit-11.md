<!-- pass: commit | model: gpt-6-luna | base: commit 386a807079fbb43c0fce8701438d726d3e740ae5 | exit: 0 | 2026-11-25 18:37:21 -->
VERDICT: PASS
C1: PASS — Commit message states one goal: limit the statement edit and add inputs to 500 characters.
C2: PASS — [check.test.tsx](/private/var/folders/j6/q0mz0r8j0zv1_8w69zdsnx8h0000gn/T/tmpxml_h43g/tree/web/tests/check.test.tsx:70) checks that both inputs expose `maxlength="500"`, as planned.
C3: PASS — The diff adds only the input-length test, matching the test-only commit message.
C4: PASS — The test advances US-1 by specifying the planned 500-character UI limits.
C5: PASS — The diff adds a test and does not game, delete, skip, or loosen any tests.