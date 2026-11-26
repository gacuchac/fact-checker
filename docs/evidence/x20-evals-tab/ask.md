User request (2026-11-25), verbatim: "Come up with more questions for the evals, and show the evals in a new tab."

Context:
- "questions" refers to the 12 multi-abstract questions the main session wrote earlier in the conversation (each answerable only by combining 2+ arXiv abstracts from data/corpus.json). The app checks claims, not open questions, so each becomes a claim-form eval case with its expected verdict and gold docs. The main session drafts the cases and brings them to the user for approval (CLAUDE.md: eval cases are written with the user); they land in evals/cases/ on this task's branch.
- "show the evals in a new tab": a new tab in the web app next to Check, Traces and Abstracts, listing the committed eval cases in evals/cases/ (today V1-V7 in statements mode; the OWASP S cases in claim mode arrive with x19).
- The OWASP task x19 (bugfix/x19-owasp-fixes) is still building in the main checkout; this task runs in its own worktree off dev and must not depend on x19's unmerged code.

Follow-up request (2026-11-25), verbatim: "Go through all 50 abstracts yourself and review the eval questions against them. The goal right now is to make the evals more robust, not more exact: broader coverage and fewer brittle cases, rather than fine-tuning the expected verdicts. The single verdicts for Q04, Q07 and Q10 are fine as they are."
