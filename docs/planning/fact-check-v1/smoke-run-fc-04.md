# fc-04 smoke run and seed eval (2026-11-24)

The main session (Opus 5.5) broke the claims down using `docs/RUNBOOK.md`. The user had authorised an autonomous build, so the main session also confirmed the statements on the user's behalf. Each claim-verifier was a Sonnet subagent at high effort. `fc judge` called GPT-6 Sol live through Codex.

## Smoke run: spike-6a claims D1, D2 and D5

| Run | Statements | Overall (rule) | Quotes kept / dropped | Sol | sha256 equal at finalize, judge and show |
| --- | --- | --- | --- | --- | --- |
| D1, lost in the middle | 1 | supported (4) | 1 / 0 | 6×5, no flags | yes |
| D2, LongAlign compound | 3 | contradicted (2): "+30%" supported, "hurts short tasks" contradicted | 4 / 0 | 6×5, no flags | yes |
| D5, MoE routing (out of corpus) | 1 | unknown (3), no evidence | 0 / 0 | 6×5, no flags | yes |

Each expectation in the PRD's fc-04 Done-when item 3 held:
- D2 ends `contradicted` with the +30% statement `supported`;
- D5 ends `unknown`;
- every quote passed rule N4;
- `fc show` reflected `final.json`, with the same hash.

## Seed eval: V1–V6 in statements mode (`fc eval score evals/cases runs/eval-20261124-155042`)

- Accuracy 1.0 (6/6), statement accuracy 1.0, quote pass rate 1.0, gold-document recall 1.0.
- Sol needs_attention:
  - **V1:** overreach 1. The statement says models "perform best" at the beginning or end, but the quote says "often highest". Sol reads that hedge as narrower than an unqualified "perform best".
  - **V2:** overreach 1, evidence_relevance 3. The contradicting quote says "this benchmark" and never names MedQA, so the scope match is inferred.
  - **V3 to V6:** 5 on every dimension.
- **Reading:** the code labels and Sol disagree on V1 and V2. In both cases the gold label we wrote is the one in question, because it accepted a hedge (V1) or an implied scope (V2). That is the D1 path: the flags go to the user, and no verdict changes automatically. These two cases are the first input for calibrating Sol against hand labels.

## Preflight
The new runbook preflight (`fc finalize` and then `fc judge` on a copy of `tests/fixtures/spike6/V4`) exited 0 on both commands.
