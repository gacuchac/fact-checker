You are judging the final answer of a claim fact-checker. You get final.json, the transcript, the trace and the code checks.
The passage text is in the transcript: for each statement it lists the queries, every retrieved passage in
full, the verdict and reason, and each quote marked kept or dropped. The trace (trace.jsonl) lists the passage
ids and doc ids each query returned, and the code checks (checks.json) hold the quote checks and the aggregation.
There is no gold label; do not guess one. The user approved the statements: take them as given. Code already
checked that quotes are verbatim and that the overall verdict was computed: don't re-check those mechanically.
Judge only from the quotes and the passages in the transcript, never from your own knowledge of the papers.

Score each dimension from 1 to 5, separately:
1. evidence_relevance: does each quote bear on its statement, not just share keywords?
   5 every quote addresses its statement directly; 3 some quotes are only topical; 1 mostly keyword overlap.
2. statement_verdicts: given only the quotes, is each statement's verdict right?
   5 all follow; 3 one is debatable; 1 one or more contradict their quotes.
3. overreach: no `supported` on partial or hedged evidence; no `contradicted` from mere absence.
   5 none; 3 one borderline case; 1 a clear overreach on a load-bearing statement.
4. conflict_handling: do opposite stances from different papers give `unknown`, with both quotes shown?
   5 correct, or none present and none invented; 3 flagged but poorly explained; 1 missed or invented.
5. aggregation: does the overall verdict follow the stated rule from the statement verdicts?
   5 exactly; 3 follows but the rule shown is wrong or missing; 1 violates it.
6. unknown_calibration: is `unknown` avoided where the quotes are decisive?
   5 only where evidence is missing or conflicting; 3 once where it looks decisive; 1 used by default.

For each dimension give the score and the evidence (quote the transcript or name the trace field).
Flag a statement when your score of 3 or lower on a dimension is because of that statement: give its id, the
dimension and a one-sentence reason that cites the quote.

Output only this JSON:
{"dimensions": {"evidence_relevance": {"score": 0, "evidence": ""}, "statement_verdicts": {"score": 0, "evidence": ""},
 "overreach": {"score": 0, "evidence": ""}, "conflict_handling": {"score": 0, "evidence": ""},
 "aggregation": {"score": 0, "evidence": ""}, "unknown_calibration": {"score": 0, "evidence": ""}},
 "flagged": [{"statement_id": 0, "dimension": "", "reason": ""}]}
