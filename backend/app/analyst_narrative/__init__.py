"""Optional, evidence-constrained narrative layer for deterministic analysis.

Deterministic findings remain the source of truth. Narrative providers may only
explain existing evidence IDs and must never invent findings.
"""

from app.analyst_narrative.models import (
    NarrativeEvidenceBundle,
    NarrativeStatus,
    ProviderNarrative,
)
from app.analyst_narrative.provider import NarrativeProvider, NarrativeProviderError
from app.analyst_narrative.service import attach_narrative, resolve_narrative_config

__all__ = [
    "NarrativeEvidenceBundle",
    "NarrativeProvider",
    "NarrativeProviderError",
    "NarrativeStatus",
    "ProviderNarrative",
    "attach_narrative",
    "resolve_narrative_config",
]
