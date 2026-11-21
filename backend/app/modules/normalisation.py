"""Text normalisation. Produces a DERIVED copy; the original text is never modified."""
from __future__ import annotations

import re
import unicodedata

_QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u00a0": " "}
_WS = re.compile(r"\s+")
_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def clean_cell(value: str | None) -> str | None:
    """Strip whitespace; empty string becomes None (missing)."""
    if value is None:
        return None
    v = _WS.sub(" ", value.replace("\ufeff", "")).strip()
    return v or None


def normalise_text(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    for k, v in _QUOTES.items():
        t = t.replace(k, v)
    return _WS.sub(" ", t).strip().lower()


def redact_pii(text: str) -> str:
    """Minimal anonymisation before external LLM calls (phones, e-mails)."""
    t = _PHONE.sub("[PHONE]", text or "")
    return _EMAIL.sub("[EMAIL]", t)

