# Progress: fact-check-v1

- I1 | 01-scope-options.md | 2026-11-24 14:22 | Scope + options; leaning BM25 (SQLite FTS5) passages, evidence-first tool call with verbatim quote check, ~24-30 labeled eval claims
- I1 (revised) | 01-scope-options.md | 2026-11-24 14:31 | Added Decision 0: claim decomposed into ≤5 falsifiable statements (explicit, hidden assumption, framing bias), retrieval + verbatim-cited verdict per statement, cross-paper conflict -> unknown
- I1 (revised 2) | 01-scope-options.md | 2026-11-24 14:35 | Sonnet 5.5 high for all LLM steps; interactive decomposition approved by user (typed hand-off decompose -> Confirmed -> verify); Sol (Codex judge --model gpt-6-sol) reviews final answer only, 6-dimension rubric
- I1 (revised 3) | 01-scope-options.md | 2026-11-24 14:39 | Corpus keeps latest listed version per paper (48 docs; 2307.03172v1, 2403.01432v1 dropped and logged); conflicts only across papers
- I2 | 02-chosen.md | 2026-11-24 14:51 | Spikes 1-6 (6 = Sonnet subagents): BM25 2-sentence passages k=5 (9/9 in top 5), no score threshold (falsified), verbatim-quote normalisation (11/11 real, 0/9 fake), Sol judge 14 s via codex, verdicts 6/6, decomposition core stable / periphery noisy; LLM steps via file-based LLMStep run by subagents, SDK backend later
- I2 (revised) | 02-chosen.md | 2026-11-24 14:54 | Entry point is a Claude session (decompose + confirm in chat) -> claim-verifier subagent (Sonnet 5.5 high) runs fc retrieve, verdicts, fc finalize, Sol judge; fc is a no-LLM toolkit; 5 typed contracts; Sol on every claim (~14 s), low score -> downgrade recommended
- I3 decisions D1-D4 | 03-decisions.md | 2026-11-24 14:57 | Low Sol score returns reasoning to main session; verifier at fact-checker/agents/claim-verifier.md; rubric in fact-checker/.claude/ approved; Opus decomposes, Sonnet finds
- I3 decision D5 | 03-decisions.md, architecture.md | 2026-11-24 14:59 | Contracts approved; architecture.md Status: approved, proposal copy in history/
- I3 | 03-solution-prd.md | 2026-11-24 15:04 | PRD: US-1..7 demo path (~30 min), US-8..11 evals/calibration; tasks fc-01..fc-09; prompts, runtime Sol rubric, eval plan; Evals flag yes (6-case seed before fc-07); 5 open items in section 13
- I3 decisions D6-D8 | 03-decisions.md | 2026-11-24 15:07 | Evals in parallel with build; 8 whole-run eval dimensions; 6-case seed expanded
- I3 decision D9 | 03-decisions.md | 2026-11-24 15:10 | Both defaults stand; user asked to start the build
- I3 decision D10 | 03-decisions.md | 2026-11-24 15:14 | Approved eval instrumentation: events.jsonl + fc show, headless-session harness, eval rubric in evals/judge/ on Luna
