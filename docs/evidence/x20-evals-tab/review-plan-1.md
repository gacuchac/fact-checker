<!-- pass: plan | model: gpt-6-sol | base: dev | exit: 0 | 2026-11-25 18:31:21 -->
VERDICT: CHANGES

1. **Subtasks 2 and 4:** The approved design labels “must cite” and “must be found by search” docs separately, but the model combines them into one `gold_docs` list, so the page cannot show that distinction.
2. **Subtask 4:** The approved note for cases with edits or planted abstracts is missing, and the view model exposes neither field needed to display it.
3. **Subtask 6:** The approved scope is Q01–Q16, while the files, tests, and done line still specify Q01–Q12.
4. **Missing e2e subtask:** The approved mocked Evals screenshots for desktop and phone in light and dark modes have no implementation or done criteria.