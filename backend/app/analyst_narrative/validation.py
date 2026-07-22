"""Post-provider validation for narrative output.

Schema parsing is necessary but not sufficient: every evidence ID must exist
in the deterministic result, and prose must not introduce secrets, URLs, HTML,
or unsupported affirmative claims.
"""

from __future__ import annotations

import re
from typing import Iterable

from app.analyst_narrative.models import ProviderNarrative
from app.analyst_narrative.provider import NarrativeUnsafeOutputError

MAX_SUMMARY_LEN = 800
MAX_EXPLANATION_LEN = 600
MAX_REMEDIATION_LEN = 400
MAX_CAVEAT_LEN = 300
MAX_EXPLANATIONS = 40
MAX_CAVEATS = 12

_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_HTML_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_PROJECT_KEY_RE = re.compile(r"\bhel_proj_[A-Za-z0-9_]+\b")
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._\-+/=]{8,}\b", re.IGNORECASE)
_API_KEY_RE = re.compile(
    r"\b(?:sk|rk|pk)-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}\b"
)

# Affirmative unsupported claims — documentary limitation wording is allowed.
_UNSUPPORTED_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"estimated?\s+cost|cost\s+(?:is|was|of|equals|at)|"
    r"rag\s+quality\s+(?:is|was|good|poor|high|low)|"
    r"citation\s+quality|"
    r"hallucinati(?:on|ng|ed)|"
    r"evaluation\s+(?:score|quality|passed|failed)|"
    r"prompt\s+quality|"
    r"this\s+trace\s+is\s+(?:healthy|secure|optimal|correct)"
    r")\b"
)

_LIMITATION_ALLOW_RE = re.compile(
    r"(?i)\b(unavailable|not\s+performed|cannot|does\s+not|no\s+verified|"
    r"not\s+assess|without\s+assessing|excluded)\b"
)


def _scan_secrets(text: str) -> str | None:
    if _PROJECT_KEY_RE.search(text):
        return "project_api_key"
    if _JWT_RE.search(text):
        return "jwt_like"
    if _BEARER_RE.search(text):
        return "bearer_token"
    if _API_KEY_RE.search(text):
        return "api_key_pattern"
    return None


def _scan_markup(text: str) -> str | None:
    if _URL_RE.search(text):
        return "url"
    if _HTML_RE.search(text):
        return "html"
    return None


def _scan_unsupported_claim(text: str) -> str | None:
    match = _UNSUPPORTED_CLAIM_RE.search(text)
    if not match:
        return None
    # Documentary / negative framing of limitations is allowed.
    window_start = max(0, match.start() - 40)
    window = text[window_start : match.end() + 40]
    if _LIMITATION_ALLOW_RE.search(window):
        return None
    return match.group(1)


def _check_text(label: str, text: str, *, max_len: int) -> None:
    if not isinstance(text, str):
        raise NarrativeUnsafeOutputError(f"{label} must be a string")
    if len(text) > max_len:
        raise NarrativeUnsafeOutputError(f"{label} exceeds maximum length")
    secret = _scan_secrets(text)
    if secret:
        raise NarrativeUnsafeOutputError(f"{label} contains {secret}")
    markup = _scan_markup(text)
    if markup:
        raise NarrativeUnsafeOutputError(f"{label} contains {markup}")
    claim = _scan_unsupported_claim(text)
    if claim:
        raise NarrativeUnsafeOutputError(f"{label} contains unsupported claim")


def validate_provider_narrative(
    narrative: ProviderNarrative,
    *,
    allowed_evidence_ids: Iterable[str],
) -> ProviderNarrative:
    """Validate and return a cleaned narrative, or raise NarrativeUnsafeOutputError."""
    allowed = set(allowed_evidence_ids)
    _check_text("summary", narrative.summary, max_len=MAX_SUMMARY_LEN)

    if len(narrative.finding_explanations) > MAX_EXPLANATIONS:
        raise NarrativeUnsafeOutputError("too many finding explanations")
    if len(narrative.caveats) > MAX_CAVEATS:
        raise NarrativeUnsafeOutputError("too many caveats")

    seen: set[str] = set()
    for item in narrative.finding_explanations:
        eid = item.evidence_id
        if eid not in allowed:
            raise NarrativeUnsafeOutputError("unknown evidence_id")
        if eid in seen:
            raise NarrativeUnsafeOutputError("duplicate evidence_id")
        seen.add(eid)
        _check_text("explanation", item.explanation, max_len=MAX_EXPLANATION_LEN)
        _check_text("remediation", item.remediation, max_len=MAX_REMEDIATION_LEN)

    for caveat in narrative.caveats:
        _check_text("caveat", caveat, max_len=MAX_CAVEAT_LEN)

    # Return a fresh model so callers cannot mutate the validated instance later.
    return ProviderNarrative.model_validate(narrative.model_dump())
