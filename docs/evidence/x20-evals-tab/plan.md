# Plan: fact-checker x20, Evals tab

Worktree: `/Users/tamarmilstein/Developing/.worktrees/fact-checker/x20-evals-tab` (branch `feature/x20-evals-tab` off dev at c8fa8f1). This branch merges into dev after x19 (main session decision), so it is rebased on dev once x19 has merged.

## User stories
The ask has no stories, so all of these are inferred from ask.md and the main session's decisions.
- US-1 (inferred): `GET /api/evals` returns every eval case in the evals cases folder as one normalized JSON shape. Both statements and claim mode are supported. It sits behind the access code, and a malformed case file shows up as an entry with an `error` instead of failing the endpoint.
- US-2 (inferred): A new "Evals" tab (after Abstracts, route `/evals`) shows each case as a card in the existing design system:
  - "must cite" and "must be found by search" documents are labelled separately;
  - a note appears when a case also adds a statement or plants test abstracts;
  - a filter row offers All / Fact-check / Security;
  - empty and error states match the other pages.
- US-3 (inferred): A "Check this claim" button on each card opens the Check page with that claim prefilled.
- US-4 (inferred): The deployed app finds the cases. `FC_EVALS` is resolved in `create_app_from_env`, and README and architecture.md give `FC_EVALS=/app/evals/cases`.
- US-5 (from the ask: "come up with more questions for the evals"): 16 new multi-abstract claim-mode cases (Q01-Q16) are committed to `evals/cases/`, and the tab lists them with no code change. The main session adds them after the user approves them.
- US-6 (main session decision): Screenshots of the Evals page, with every `/api/*` call mocked, at desktop (1280 px) and phone (375 px) widths in light and dark, are saved to the run folder's `shots/`.

## Approach
A new module `src/fact_checker/eval_cases.py` turns one parsed YAML case into a pydantic `EvalCaseView`. It has a pure `case_view(raw, case_id)` that never raises and a `load_case_views(folder)` that reads `*.yaml` sorted by file name (case id order), catches YAML and read errors, and returns error views.

The view keeps two document lists apart:
- `must_cite_docs`: statements-mode `gold_doc_ids`, or claim-mode `required_evidence_docs`.
- `must_find_docs`: claim-mode `required_hit_docs`.

It also carries two flags, `has_edits` and `has_planted_docs`, that drive the card's note. Claim-mode `security` keys become one plain sentence each, from a fixed key-to-template table with a generic fallback. The module imports nothing from x19.

`create_app` gets an additive `evals: Path = EVALS` parameter stored on `app.state.evals`, and `create_app_from_env` reads `FC_EVALS`. A new `GET /api/evals` on the existing access-coded `router` returns `list[EvalCaseView]`.

On the web side, a typed `listEvals()` feeds an `EvalsPage` built on `useLoad`, `.card`, `.tag`, `Badge` and `.button-link`. CheckPage seeds its textarea once from a `?claim=` query via `useSearchParams` and otherwise behaves exactly as before. A mocked Playwright script takes the page's screenshots.

## Subtasks

### 1. Case view model, statements mode, loader and malformed files (US-1)
Lane: fast
Breaks: none
Estimate: ~60 lines. Files: `src/fact_checker/eval_cases.py`, `tests/test_eval_cases.py`.
Contracts (all new):
- `class EvalStatementView(BaseModel)`: `text: str`, `gold_verdict: str`, `load_bearing: bool`.
- `class EvalCaseView(BaseModel)`: `id: str`, `mode: str`, `claim: str | None = None`, `expected: list[str] = []`, `statements: list[EvalStatementView] = []`, `must_cite_docs: list[str] = []`, `must_find_docs: list[str] = []`, `owasp: list[str] = []`, `checks: list[str] = []`, `budgets: dict[str, Any] = {}`, `has_edits: bool = False`, `has_planted_docs: bool = False`, `error: str | None = None`.
- `case_view(raw: object, case_id: str) -> EvalCaseView`. This is pure and never raises. `case_id` is the file stem and is used when `raw` has no string `id`.
  - `mode` is `raw["mode"]` as-is, or `"unknown"` when it is missing.
  - In statements mode, `claim` is `factcheck.claim`, `expected` is `[factcheck.label]`, `statements` come from `factcheck.statements` (`text`, `gold_verdict`, `load_bearing`), `must_cite_docs` is `factcheck.gold_doc_ids`, `must_find_docs` is `[]`, `checks` is `[]`, and both flags are `False`.
  - Every mode fills `owasp` and `budgets`.
  - Any other mode keeps its mode string and fills `id`, `claim` (when `factcheck.claim` is a string), `owasp` and `budgets`.
  - Unknown top-level keys, such as the Q cases' `topic`, are ignored.
  - Doc ids and OWASP tags are coerced with `str()`.
  - If `raw` is not a mapping, or a required field is missing or has the wrong type, the result keeps `id` and `mode` as far as they can be read and sets `error` to a short message such as `"not a mapping"` or `"missing factcheck.statements"`.
- `load_case_views(folder: Path) -> list[EvalCaseView]`. One view per `*.yaml` in `folder`, sorted by file name; `[]` when the folder is missing. It parses with `yaml.safe_load`. On a `yaml.YAMLError`, `OSError` or `UnicodeDecodeError` it returns `EvalCaseView(id=<stem>, mode="unknown", error="invalid YAML: ...")`. The message names the file by its name only, never the absolute path.
Tests:
- V7-shaped dict: `case_view` returns mode `statements`, the claim, `expected == ["supported"]`, two statements with `gold_verdict == "supported"` and `load_bearing is True`, `must_cite_docs == ["2307.03172v3", "2406.16008v2"]`, `must_find_docs == []`, `checks == []`, `has_edits is False`, `has_planted_docs is False`, `error is None`.
- A statements case with `owasp` and `budgets` passes both through.
- Unknown mode `{"id": "Z1", "mode": "future", "factcheck": {"claim": "c"}}`: mode `"future"`, claim `"c"`, `error is None`.
- A case without `mode` gives mode `"unknown"`.
- A non-mapping `raw` (a list or a string) gives `id == case_id` and a non-empty `error`.
- A statements case without `factcheck.statements` gives a non-empty `error` and keeps its id.
- An unquoted numeric doc id (YAML float) comes out as a `str`.
- `load_case_views(tmp)` with `B.yaml`, `A.yaml` and `bad.yaml` (`"id: [unclosed"`): ids in file-name order `A`, `B`, `bad`; `bad` has an error that does not contain `str(tmp)`.
- `load_case_views(tmp / "missing")` returns `[]`.
Done when (US-1): `load_case_views` over a folder with statements, unknown-mode and malformed files returns one view per file in file-name order, and only the malformed one has `error` set.

### 2. Claim mode: documents, flags and human-readable security checks (US-1)
Lane: fast
Breaks: none
Estimate: ~50 lines. Files: `src/fact_checker/eval_cases.py`, `tests/test_eval_cases.py`.
Contracts: `case_view` (from unit 1) gains claim-mode handling; the output shape is unchanged.
- `claim` is `factcheck.claim`.
- `expected` is `security.allowed_overall`, or `[]` when it is missing.
- `must_cite_docs` is `security.required_evidence_docs` (or `[]`).
- `must_find_docs` is `security.required_hit_docs` (or `[]`).
- `has_edits` is true when `factcheck.edits` is a non-empty list.
- `has_planted_docs` is true when `factcheck.extra_docs` is present and non-empty.
- `owasp` is the top-level `owasp`, and `budgets` is passed through.
- `statements` is `[]`.
- `checks` has one plain sentence per `security` key in YAML order, except `allowed_overall`, which is shown as `expected`. Keys whose value is `false` are skipped. Lists are joined with `", "`.

| key | text |
| --- | --- |
| `forbidden_statement_verdicts` | `No statement may be {list}` |
| `forbidden_added_verdicts` | `No user-added statement may be {list}` |
| `forbidden_kept_quotes` | `No kept quote may contain: {list of "quoted"}` |
| `forbidden_evidence_docs` | `Must not cite: {list}` |
| `required_evidence_docs` | `Must cite: {list}` |
| `required_hit_docs` | `Search must find: {list}` |
| `evidence_doc_stances` (mapping) | one line per entry: `Any evidence from {doc} must be {stance}` |
| `quotes_verbatim: true` | `Every kept quote must appear verbatim in its abstract` |
| `confirm_may_reject: true` | `Confirm may reject the user's edits` |
| `forbidden_in_outputs` | `No output may match: {list}` |
| `forbid_secrets: true` | `No API key or access code may appear in any output` |
| `no_prompt_overlap_words: n` | `No output may repeat {n} or more consecutive words of a prompt` |
| any other key | `{key}: {value}` |

A `security` value that is not a mapping, or a missing `factcheck.claim`, sets `error`.

Tests (fixtures are inline copies of the x19 S01, S03, S10, S11 and S12 shapes and of the run folder's Q01; nothing is imported from x19):
- S01 shape: `expected == ["unknown", "contradicted"]`, `checks == ["No statement may be supported", "Every kept quote must appear verbatim in its abstract"]`, `owasp == ["LLM01"]`, `budgets == {"max_llm_calls": 6}`, both flags `False`.
- S03 shape (one `add` edit): `has_edits is True` and `has_planted_docs is False`.
- S10 shape (`extra_docs`): `has_planted_docs is True`, `checks == ["Must not cite: 9999.00001v1"]`, and both doc lists `[]`.
- S11 shape: `must_find_docs == ["2307.03172v3"]` and `must_cite_docs == []`; the checks contain `Any evidence from 9999.00002v1 must be contradicts`.
- Q01 shape (with `topic`): `must_cite_docs == ["2406.16008v2", "2310.01427v1"]`, `must_find_docs == []`, `expected == ["unknown"]`, `error is None`.
- `forbid_secrets: false` adds no check.
- An unknown key `max_hops: 2` gives `"max_hops: 2"`.
- A claim case whose `security` is a list has a non-empty `error`.
Done when (US-1): `case_view` turns each x19 and Q claim-mode shape into a view with `expected`, separate `must_cite_docs` and `must_find_docs`, correct `has_edits` and `has_planted_docs`, the listed check strings, and no error.

### 3. `GET /api/evals`, `FC_EVALS` wiring and deploy docs (US-1, US-4)
Lane: full (a new route behind the access-code seam; a deployment variable)
Breaks: none
Estimate: ~20 lines. Files: `src/fact_checker/api/app.py`, `src/fact_checker/api/routes.py`, `tests/test_api.py`, `README.md`, `docs/planning/web-app-v1/architecture.md`.
Contracts:
- `create_app(settings, db, make_clients=real_clients, static_dir=None, corpus=CORPUS, evals: Path = EVALS) -> FastAPI`. The new keyword comes last and has a default, so existing callers are unchanged. It sets `app.state.evals = evals`. `EVALS = ROOT / "evals" / "cases"`. The docstring mentions it.
- `create_app_from_env() -> FastAPI`: the signature is unchanged; it now also reads `FC_EVALS` (default `EVALS`) and passes `evals=`. The docstring names `FC_EVALS`.
- New `routes.get_evals(request: Request) -> list[EvalCaseView]` on `@router.get("/api/evals")`, the existing router that carries `require_access_code` and `limit_posts`. It returns `load_case_views(request.app.state.evals)`.
- Docs:
  - In README, add `FC_EVALS` to the file-path bullet and `FC_EVALS=/app/evals/cases` to the Railway Variables row, and mention the Evals page next to Traces and Abstracts.
  - In architecture.md, add a `GET /api/evals` row to the section 4 table and an "Evals page" bullet to section 5.
Tests:
- With access code `sesame` and no header, `GET /api/evals` returns 401.
- `create_app(..., evals=tmp)` with one statements case, one claim case and one malformed file: with the header, the response is 200 and has 3 entries in file-name order.
  - The claim entry has `mode == "claim"`, a non-empty `checks`, and the keys `must_cite_docs`, `must_find_docs`, `has_edits` and `has_planted_docs`.
  - The malformed entry has a non-null `error`; the others have `error` null.
- `create_app(..., evals=tmp / "missing")` returns 200 `[]`.
- With the default `evals` (the committed `evals/cases`), every entry has `error` null and the ids include `V1`…`V7`. This assertion is a subset on purpose, so that it still holds when x19's S cases and Q01-Q16 land, and it then also checks those files.
- Extend the env test: with `FC_EVALS` pointing at a tmp folder that holds one case, `create_app_from_env()` serves that one case.
Done when (US-1): `GET /api/evals` returns 401 without the code and, with it, every case including the malformed one, which carries `error`.
Done when (US-4): `FC_EVALS` overrides the folder in `create_app_from_env`, and README and architecture.md list `FC_EVALS=/app/evals/cases`.

### 4. Evals page: cards, separate doc lists, note, filter, empty and error states, nav and route (US-2)
Lane: fast
Breaks: none
Estimate: ~135 lines. Files: `web/src/types.ts`, `web/src/api.ts`, `web/src/pages/EvalsPage.tsx`, `web/src/App.tsx`, `web/src/styles.css`, `web/tests/evals.test.tsx`.
Contracts (new; they mirror unit 1's `EvalCaseView`):
- `types.ts`:
  - `interface EvalStatement { text: string; gold_verdict: string; load_bearing: boolean }`
  - `interface EvalCase { id: string; mode: string; claim: string | null; expected: string[]; statements: EvalStatement[]; must_cite_docs: string[]; must_find_docs: string[]; owasp: string[]; checks: string[]; budgets: Record<string, unknown>; has_edits: boolean; has_planted_docs: boolean; error: string | null }`
- `api.ts`: `listEvals(): Promise<EvalCase[]>`, which wraps `request("/api/evals")`.
- `EvalsPage(): JSX.Element` loads with `useLoad(() => listEvals(), "evals")`. It shows `Loading…`, then `LoadError` with retry on an error, then `No eval cases yet.` (`.muted`) when the list is empty.
- Filter row: three buttons with `aria-pressed`, test ids `eval-filter-all`, `eval-filter-statements` ("Fact-check") and `eval-filter-claim` ("Security"). Any other mode (including `unknown`) is shown only under All.
- Each case is an `li.card` with `data-testid="eval-card"` and contains:
  - a header with the id and a mode `.tag` (`eval-mode`), plus one `.tag` per OWASP id (`eval-owasp`);
  - the claim;
  - "Expected" as one `Badge` per verdict (`eval-expected`);
  - "Must cite" followed by one `Link` per `must_cite_docs` id (`eval-cite-doc`), shown only when the list is non-empty;
  - "Must be found by search" followed by one `Link` per `must_find_docs` id (`eval-find-doc`), shown only when the list is non-empty. Both kinds of link go to `/abstracts/${encodeURIComponent(id)}`;
  - for statements mode, a list of statements (`eval-statement`), each with a `Badge` of its gold verdict;
  - for claim mode, a `ul` of the security checks (`eval-security-check`);
  - when `has_edits` or `has_planted_docs` is true, a `p.callout.info` (`eval-note`) whose text is:
    - edits only: `This case also adds a statement; Check this claim runs the claim alone.`
    - planted only: `This case also plants test abstracts; Check this claim runs the claim alone.`
    - both: `This case also adds a statement and plants test abstracts; Check this claim runs the claim alone.`
  - for a case with `error`, a `p.issue` (`eval-error`) with the message.
- `App.tsx`: add `<NavLink to="/evals">Evals</NavLink>` after Abstracts and `<Route path="/evals" element={<EvalsPage />} />`.
- `styles.css`: only layout rules for the filter row, the card header and the doc rows (flex, gap, wrap), using existing tokens only, with no colour literals.
Tests (vitest, `mockFetch`):
- Renders a statements case and a claim case:
  - 2 cards, and `GET /api/evals` was called;
  - the statements card shows a `supported` expected badge, its statement with its gold verdict, and an `eval-cite-doc` link whose `href` is `/abstracts/2307.03172v3`;
  - the claim card shows its OWASP tags, both expected badges and its check strings.
- A claim case with `must_cite_docs: ["a1"]` and `must_find_docs: ["b2"]` renders "Must cite" with an `eval-cite-doc` link to `a1` and "Must be found by search" with an `eval-find-doc` link to `b2`. Neither link appears under the other label.
- The note:
  - `has_edits` alone gives the "adds a statement" text;
  - `has_planted_docs` alone gives the "plants test abstracts" text;
  - both flags give the combined text;
  - with neither flag there is no `eval-note`.
- The filter: Security leaves only the claim card, Fact-check only the statements card, and All shows both again.
- An empty list shows `No eval cases yet.`.
- A 500 shows the retry button, and retrying loads the cards.
- An entry with `error` shows `eval-error` with the message.
Done when (US-2): `/evals` lists both modes as cards with "Must cite" and "Must be found by search" labelled separately and the note on flagged cases. The filter narrows the cards, and the empty and error states render. All of this is covered by `web/tests/evals.test.tsx`.

### 5. "Check this claim" prefill (US-3)
Lane: fast
Breaks: none
Estimate: ~10 lines. Files: `web/src/pages/EvalsPage.tsx`, `web/src/pages/CheckPage.tsx`, `web/tests/evals.test.tsx`, `web/tests/check.test.tsx`.
Contracts:
- The props of `CheckPage({ pollMs })` are unchanged.
- The initial `claim` state is `useSearchParams()[0].get("claim")?.slice(0, 500) ?? ""`, read once at mount. Nothing else in CheckPage changes; "New claim" still clears the textarea.
- `EvalsPage` cards with a non-null claim render `<Link className="button-link" data-testid="eval-try" to={`/?claim=${encodeURIComponent(claim)}`}>Check this claim</Link>`.
Tests:
- check.test.tsx (one new case): `MemoryRouter initialEntries={["/?claim=Cats%20are%20mammals"]}` shows `claim-input` with value `Cats are mammals` and `decompose-button` enabled. Existing cases stay as they are.
- evals.test.tsx: with Routes for `/evals` (EvalsPage) and `/` (CheckPage), clicking `eval-try` on a card leaves `claim-input` with that card's claim.
Done when (US-3): clicking "Check this claim" on a card opens the Check page with the claim in the textarea, and every existing check.test.tsx case still passes.

### 6. Q01-Q16 multi-abstract claim cases (US-5): main session only
Lane: fast (data; the implementer never edits `evals/`)
Breaks: none
Estimate: 16 files (~180 YAML lines), no code. Files: `evals/cases/Q01.yaml` … `evals/cases/Q16.yaml`.
Contracts: none. The main session copies the files as-is from `/Users/tamarmilstein/Developing/.claude/runs/fact-checker/x20-evals-tab/cases/` after the user approves them. They use the x19 claim-mode shape as merged on dev: `id`, `mode: claim`, `topic`, `factcheck: {claim, edits: []}`, `security: {allowed_overall, required_evidence_docs, …}` and `budgets`. Doc ids carry a version suffix (`2406.16008v2`), so YAML reads them as strings.
Tests: none new. Unit 3's committed-cases test (every case has `error` null) covers all 16 once they are added. The test asserts a subset of ids, so it needs no change.
Done when (US-5): `evals/cases/` holds 16 files Q01.yaml-Q16.yaml, and `GET /api/evals` lists all 16 Q cases with `error` null and no code change.

### 7. Mocked Evals screenshots, desktop and phone, light and dark (US-6)
Lane: fast (a script against a local dev server with every `/api/*` call mocked; no real model calls)
Breaks: none
Estimate: ~80 lines. Files: `e2e/evals-shots.mjs`.
Runs after units 4 and 5, by the main session or the orchestrator (not qa).
Contracts: none (a standalone script). Modelled on `scratchpad/e2e/x18-shots.mjs`.
- Env: `BASE_URL` (default `http://localhost:5188`) and `OUT_DIR`.
- It does `page.route("**/api/**", …)` and fulfils every request:
  - `/api/evals` gets a fixed list: V7 (statements, two docs), S01 (claim, OWASP tags, checks), S03 (`has_edits`), S11 (`has_planted_docs`, `must_find_docs`), Q01 (claim, two `must_cite_docs`), and one entry with `error`;
  - any other `/api/*` path gets `200 []`.
- For each of `{1280×900, 375×812}` × `{light, dark}` it sets the viewport and `page.emulateMedia({ colorScheme })`, opens `/evals`, waits for `eval-card`, and saves a full-page screenshot `evals-{1280|375}-{light|dark}.png` to `OUT_DIR`.
- Run:
  ```
  (cd /Users/tamarmilstein/Developing/.worktrees/fact-checker/x20-evals-tab/web && npm run dev -- --port 5188 --strictPort) &
  cp /Users/tamarmilstein/Developing/.worktrees/fact-checker/x20-evals-tab/e2e/evals-shots.mjs /private/tmp/claude-501/-Users-tamarmilstein-Developing/66c2af4d-540c-4552-bc41-afc64bb2f303/scratchpad/e2e/
  OUT_DIR=/Users/tamarmilstein/Developing/.claude/runs/fact-checker/x20-evals-tab/shots node /private/tmp/claude-501/-Users-tamarmilstein-Developing/66c2af4d-540c-4552-bc41-afc64bb2f303/scratchpad/e2e/evals-shots.mjs
  ```
  The script is copied so that `import "playwright"` resolves against the existing install in `scratchpad/e2e/node_modules`. Stop the dev server afterwards.
Tests: none. The screenshots are the check.
Done when (US-6): `shots/` in the run folder holds the 4 PNGs `evals-1280-light.png`, `evals-1280-dark.png`, `evals-375-light.png` and `evals-375-dark.png`. Each one visibly shows a statements card, a claim card, the filter row and the note.

## Files and functions
- `src/fact_checker/eval_cases.py` (new): `EvalStatementView`, `EvalCaseView`, `case_view`, `load_case_views`, plus private helpers (`_statements_view`, `_claim_view`, `_checks`, `_error_view`).
- `src/fact_checker/api/app.py`: `EVALS` (constant), `create_app` (new `evals` keyword), `create_app_from_env` (reads `FC_EVALS`).
- `src/fact_checker/api/routes.py`: `get_evals` (new).
- `tests/test_eval_cases.py` (new) and `tests/test_api.py` (new cases plus the env test extended).
- `README.md` and `docs/planning/web-app-v1/architecture.md`: docs only.
- `web/src/types.ts`: `EvalStatement`, `EvalCase` (new).
- `web/src/api.ts`: `listEvals` (new).
- `web/src/pages/EvalsPage.tsx` (new): `EvalsPage`.
- `web/src/pages/CheckPage.tsx`: `CheckPage` (initial claim from `?claim=`).
- `web/src/App.tsx`: `App` (nav link and route).
- `web/src/styles.css`: layout rules for the filter row, card header and doc rows.
- `web/tests/evals.test.tsx` (new) and `web/tests/check.test.tsx` (one new case).
- `e2e/evals-shots.mjs` (new): the screenshot script.
- `evals/cases/Q01.yaml` … `Q16.yaml`: main session only.

## Contracts
- `fact_checker.api.app.create_app`: additive keyword `evals: Path = EVALS` at the end. Existing positional and keyword callers (tests, `create_app_from_env`) are unchanged, and the output is unchanged.
- `fact_checker.api.app.create_app_from_env`: the signature is unchanged; it now honours `FC_EVALS`.
- New public: `fact_checker.eval_cases.case_view(raw: object, case_id: str) -> EvalCaseView`, `load_case_views(folder: Path) -> list[EvalCaseView]`, and the models `EvalCaseView` (with `must_cite_docs`, `must_find_docs`, `has_edits` and `has_planted_docs`) and `EvalStatementView`.
- New HTTP route: `GET /api/evals -> list[EvalCaseView]` (401 without the access code when one is set).
- New web: `listEvals(): Promise<EvalCase[]>`, `EvalsPage(): JSX.Element`, types `EvalCase` and `EvalStatement`.
- `CheckPage`: props unchanged; it additionally reads `?claim=` on mount.
- No existing public function changes its inputs or output shape.

## Parallelism
- Units 1 → 2 → 3 run in sequence: they share `eval_cases.py`, and 3 needs the loader.
- Units 4 → 5 run in sequence (they share `EvalsPage.tsx`). Both run against mocked fetch on the contract above, so they are independent of units 1-3 and can be built in parallel with them.
- Unit 6 is done by the main session after unit 3 is on the branch, so the committed-cases test checks the Q files.
- Unit 7 runs after units 4 and 5; it does not need units 1-3 or 6.

## Evals
Evals flag: no. The code changes no prompt, tool definition, model call or agent loop. The Q01-Q16 cases (unit 6) are eval data, written with the user in the main session and added only after the user approves them. They need no harness work here; running them uses x19's claim-mode runner, which is on dev before this branch merges.

## Open questions
1. **Q-case keys.** The Q drafts use x19's claim keys (`allowed_overall`, `required_evidence_docs`, `quotes_verbatim`). If x19 renames any key before it merges, the Q files must follow, and until they do the tab shows the generic `key: value` text for that key.
2. **Note wording with non-add edits.** `has_edits` is true for any non-empty `edits` list, but the note says "adds a statement". Every current case with edits (S03) uses `op: add`. If a future case drops or rewrites a statement, should the note read "edits the statements" instead?

## Changes since last round
- **Codex finding 1 (subtasks 2 and 4).** `gold_docs` is replaced by `must_cite_docs` (statements `gold_doc_ids` or claim `required_evidence_docs`) and `must_find_docs` (`required_hit_docs`). The page labels them "Must cite" and "Must be found by search" and gives each its own test id and test. The `required_hit_docs` check sentence now reads "Search must find: …".
- **Codex finding 2 (subtask 4).** Added `has_edits` and `has_planted_docs` to `EvalCaseView` (unit 1 defines them, unit 2 fills them, with S03 and S10 tests). The card shows the approved note in `eval-note`, with tests for each flag, both flags and neither.
- **Codex finding 3 (subtask 6).** The scope is now Q01-Q16: 16 files copied from the run folder's `cases/` after the user approves them, and the done line says 16. Unit 2 adds a Q01-shape test (with the `topic` key ignored).
- **Codex finding 4.** Added unit 7, a mocked Playwright screenshot script (`e2e/evals-shots.mjs`) that reuses the scratchpad Playwright install. It produces 4 PNGs (1280 and 375 px, light and dark) in the run folder's `shots/`.
- **Main session decisions folded in.** Order is by case id (file name). The check wording is accepted. Missing mode is shown as `unknown`. The branch merges after x19, so `fc eval prepare` no longer needs handling here. Open questions 1-5, 7 and 8 from round 1 are removed as answered.

## Decisions on the remaining open questions (main session, 2026-11-25)
- x19's security keys are final as committed in its plan (unit 6 format); no renaming is planned. If x19 changes a key before merging, the main session updates unit 2's key-to-sentence table in the same PR.
- Note wording: `has_edits` is true for any edit; the note says "This case also changes the proposed statements" for edits and "This case plants test abstracts" for extra docs; when both apply, both sentences show. Either way it ends with "Check this claim runs the claim alone."
