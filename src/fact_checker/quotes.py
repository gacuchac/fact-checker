"""Verbatim quote checking with the N4 normaliser."""

import re
import unicodedata

MIN_WORDS = 5
QUOTE_MAP = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2010": "-",
        "\u2011": "-",
        "\u2212": "-",
        "\u00a0": " ",
        "\u2026": "...",
    }
)
LATEX_COMMAND = re.compile(r"\\(?:textbf|textit|emph|url|href|mathrm|text|mathbf)\{([^{}]*)\}(?:\{[^{}]*\})?")
HYPHENATION = re.compile(r"(?<=[a-z])-\s*(?=[a-z])")


def _strip_latex(text: str) -> str:
    text = LATEX_COMMAND.sub(r"\1", text)
    text = text.replace("\\times", "x")
    text = re.sub(r"\\([%&_#$])", r"\1", text)
    text = re.sub(r"\^\{?([^{}\s]*)\}?", r"^\1", text)
    return text.replace("$", "")


def normalise(text: str) -> str:
    """Return text normalised by rule N4: Unicode, LaTeX, whitespace, case, hyphenation and edge punctuation."""
    text = _strip_latex(unicodedata.normalize("NFKC", text).translate(QUOTE_MAP))
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return HYPHENATION.sub(" ", text).strip(" .,;:\"'")


def check_quote(quote: str, passage: str) -> bool:
    """Return True if quote is a verbatim, at least 5-word, ellipsis-free substring of passage after N4."""
    if "..." in quote or "\u2026" in quote:
        return False
    normalised = normalise(quote)
    return len(normalised.split()) >= MIN_WORDS and normalised in normalise(passage)
