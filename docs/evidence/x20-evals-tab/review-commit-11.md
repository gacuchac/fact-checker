<!-- pass: commit | model: gpt-6-luna | base: commit d38fe36fd671e864b35194aa6655d56f5b93bded | exit: 0 | 2026-11-25 19:37:06 -->
VERDICT: CHANGES

C1: PASS — The subject states one goal: add Q17–Q40 to cover corpus abstracts.

C2: PASS — The diff adds all 24 named claim cases; for example, [Q17.yaml](evals/cases/Q17.yaml) defines Q17 with an expected verdict and evidence docs.

C3: PASS — The diff adds only the Q17–Q40 eval cases described in the message.

C4: FAIL — The plan calls for multi-abstract claim cases, but most additions cite just one abstract; the message itself says “each checked against its abstract.”

C5: N/A — The diff adds eval data and does not delete, skip, or loosen tests.