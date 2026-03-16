"""
Typed exception hierarchy for RelayLLMs.

Replaces the string-prefix error signaling ("Error: ...") with proper
exception classes so the dispatcher can make smarter retry decisions.
"""


class ProviderError(Exception):
    """Base exception for all provider-related errors."""

    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class RateLimitError(ProviderError):
    """Raised when a provider returns a rate-limit (429) response."""
    pass


class AuthenticationError(ProviderError):
    """Raised when API key is invalid or missing."""
    pass


class ModelNotFoundError(ProviderError):
    """Raised when the requested model does not exist on the provider."""
    pass


class ProviderUnavailableError(ProviderError):
    """Raised when the provider is down or unreachable."""
    pass


class AllProvidersExhaustedError(Exception):
    """Raised when all providers have been tried and none succeeded."""

    def __init__(self, attempts: int, last_error: str):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"All {attempts} provider attempts failed. Last error: {last_error}"
        )
