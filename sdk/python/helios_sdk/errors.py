class HeliosError(Exception):
    """Base error for the Helios Python SDK."""


class HeliosConnectionError(HeliosError):
    """Raised when the Helios backend is unreachable."""


class HeliosAPIError(HeliosError):
    """Raised when the Helios API returns a non-success response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HeliosConfigurationError(HeliosError):
    """Raised for invalid v2 SDK configuration or conflicting reconfiguration."""


class HeliosInstrumentationError(HeliosError):
    """Raised when an optional instrumentation extra is missing or misused."""
