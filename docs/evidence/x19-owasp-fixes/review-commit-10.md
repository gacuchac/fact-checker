<!-- pass: commit | model: gpt-6-luna | base: commit 9a8ac381bdadb73d95dd692f95eb8fc0d6811cdb | exit: 0 | 2026-11-25 18:36:34 -->
VERDICT: CHANGES
C1: PASS — The subject names one goal: adding the `fc eval run-claims` command.
C2: FAIL — The plan requires each case to run with `work=out/<id>`, but the command passes a temporary directory instead: `with tempfile.TemporaryDirectory() as scratch:` and `outcome = run_claim_case(case, ROOT, clients, settings, secrets, Path(scratch))` [src/fact_checker/cli.py]. Thus the command does not fully implement the planned per-case run location.
C3: PASS — The diff adds the claim-case command, filters statement-mode cases for the existing prepare and score commands, and documents the new command, as described by the message and plan.
C4: PASS — The command advances US-8 by running and scoring the planned claim-mode eval cases.
C5: N/A — The diff does not add, delete, skip, loosen, or game any tests.