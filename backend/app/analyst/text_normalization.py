"""Shared text normalization for privacy-sensitive values like status messages.

Used by both single-trace (analyst) and project-window (project_analyst) engines
to ensure consistent redaction across analyses.
"""

from __future__ import annotations

import re
from typing import Any

_DIGIT_RUN_RE = re.compile(r"\d+")
_WHITESPACE_RE = re.compile(r"\s+")

# Constants for status message normalization (must match project_analyst/thresholds.py)
SIGNATURE_TOKEN_MAX_LEN = 24  # tokens longer than this become <long>
SIGNATURE_MESSAGE_MAX_LEN = 64  # max length after normalization


def normalize_status_message(message: Any) -> str | None:
    """Collapse a status message into a bounded, redacted signature fragment.

    - whitespace runs collapse to one space,
    - digit runs collapse to ``#`` (request IDs, counts, timestamps),
    - any remaining token longer than ``SIGNATURE_TOKEN_MAX_LEN`` collapses to
      ``<long>`` (keys, JWTs, hashes, UUIDs, blobs),
    - the result is truncated to ``SIGNATURE_MESSAGE_MAX_LEN``.
    """
    if not isinstance(message, str):
        return None
    text = _WHITESPACE_RE.sub(" ", message).strip()
    if not text:
        return None
    text = _DIGIT_RUN_RE.sub("#", text)
    tokens = [
        token if len(token) <= SIGNATURE_TOKEN_MAX_LEN else "<long>"
        for token in text.split(" ")
    ]
    text = " ".join(tokens)
    if len(text) > SIGNATURE_MESSAGE_MAX_LEN:
        text = text[: SIGNATURE_MESSAGE_MAX_LEN - 1] + "…"
    return text
