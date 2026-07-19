"""Provider-neutral narrative interface and internal exceptions.

No FastAPI, database, WorkOS, or project-key dependencies. Providers receive
only a sanitized ``NarrativeEvidenceBundle``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.analyst_narrative.models import NarrativeEvidenceBundle, ProviderNarrative


class NarrativeProviderError(Exception):
    """Base class for narrative provider failures (never expose raw details)."""


class NarrativeConfigurationError(NarrativeProviderError):
    """Provider or credentials are not usable."""


class NarrativeTimeoutError(NarrativeProviderError):
    """Provider call timed out."""


class NarrativeRateLimitError(NarrativeProviderError):
    """Provider rate-limited the request (retryable once)."""


class NarrativeUnavailableError(NarrativeProviderError):
    """Provider returned a transient unavailability (retryable once)."""


class NarrativeInvalidOutputError(NarrativeProviderError):
    """Provider returned unusable structured output."""


class NarrativeUnsafeOutputError(NarrativeProviderError):
    """Provider output failed Helios safety validation."""


@runtime_checkable
class NarrativeProvider(Protocol):
    async def generate(
        self,
        *,
        bundle: NarrativeEvidenceBundle,
    ) -> ProviderNarrative:
        """Produce a structured narrative constrained to the evidence bundle."""
        ...
