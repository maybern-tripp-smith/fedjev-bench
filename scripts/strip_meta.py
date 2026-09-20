"""Strip speaker names, titles, and meeting dates from text for Jev calls.

Keeps semantic content; use raw_text fields for ablation.
"""
from __future__ import annotations

import re

# Chair / speaker labels at line starts or inline
SPEAKER = re.compile(
    r"\b((?:Chair(?:man|woman)?|Vice\s+Chair(?:man|woman)?|Governor|President|"
    r"Mr\.|Ms\.|Mrs\.|Dr\.)\s+[A-Z][a-zA-Z\-']+(?:\s+[A-Z][a-zA-Z\-']+)?)\b"
)
DATE_PAT = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b"
)
ISO_DATE = re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b")
TITLE_LINE = re.compile(
    r"^(?:Transcript of |Opening Statement|Press Conference|FOMC Statement).*$",
    re.I | re.M,
)
PAGE_FURNITURE = re.compile(
    r"^(?:Page \d+ of \d+|PRELIMINARY|FINAL)\s*$", re.M
)


def strip_meta(text: str) -> str:
    """Return text with speaker names, titles, and meeting dates removed."""
    if not text:
        return ""
    out = PAGE_FURNITURE.sub("", text)
    out = TITLE_LINE.sub("", out)
    out = DATE_PAT.sub("[DATE]", out)
    out = ISO_DATE.sub("[DATE]", out)
    out = SPEAKER.sub("[SPEAKER]", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


if __name__ == "__main__":
    import sys

    raw = sys.stdin.read()
    print(strip_meta(raw))
