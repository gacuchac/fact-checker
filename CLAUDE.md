# fact-checker

Sessions run from the workspace root `~/Developing`, which holds the workflow and its rules (`~/Developing/CLAUDE.md`). If this session was opened inside this folder, stop and tell the user to reopen VS Code at `~/Developing`.

## What this project is
Command-line fact-checking system that verifies claims against a corpus of arXiv abstracts using retrieval plus LLM API calls, returning a verdict (supported, contradicted, unknown) with grounded evidence excerpts.

## Stack and commands
- Tests: `.venv/bin/python -m pytest -q`

## Project rules
Anything beyond the workspace rules goes here.
