"""Gateway-specific exceptions."""


class AiGatewayError(Exception):
    """Base exception for AI gateway failures."""


class UnsupportedProviderError(AiGatewayError):
    """Raised when a gateway provider is not supported."""


class GatewayToolArgumentError(AiGatewayError):
    """Raised when a provider returns malformed tool arguments."""


class StructuredOutputValidationError(AiGatewayError):
    """Raised when structured model output cannot be validated."""
