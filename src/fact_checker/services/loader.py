"""Loading of the prompt texts shipped as package data."""

from importlib.resources import files


def load_prompt(name: str) -> str:
    """Return the text of prompts/<name>.md; raises FileNotFoundError if there is no such prompt."""
    return (files("fact_checker.services") / "prompts" / f"{name}.md").read_text(encoding="utf-8")
