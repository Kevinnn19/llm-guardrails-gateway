"""Domain exceptions for the guardrails gateway.

All exceptions carry a machine-readable `code` so API middleware can map
them to consistent HTTP responses without isinstance chains.
"""


class GatewayError(Exception):
    """Base exception for all gateway errors."""

    code: str = "gateway_error"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# --- Input validation ---


class InputValidationError(GatewayError):
    """Input guardrail validation failed."""

    code = "input_validation_failed"
    http_status = 400


class PromptInjectionError(InputValidationError):
    code = "prompt_injection_detected"


class JailbreakError(InputValidationError):
    code = "jailbreak_detected"


class PIIDetectedError(InputValidationError):
    code = "pii_detected"


class SecretDetectedError(InputValidationError):
    code = "secret_detected"


class TokenLimitError(InputValidationError):
    code = "token_limit_exceeded"


class ToxicInputError(InputValidationError):
    code = "toxic_input_detected"


# --- Output validation ---


class OutputValidationError(GatewayError):
    """Output guardrail validation failed."""

    code = "output_validation_failed"
    http_status = 422


class JSONSchemaValidationError(OutputValidationError):
    code = "json_schema_violation"


class PromptLeakageError(OutputValidationError):
    code = "prompt_leakage_detected"


class ToxicOutputError(OutputValidationError):
    code = "toxic_output_detected"


# --- Policy ---


class PolicyNotFoundError(GatewayError):
    code = "policy_not_found"
    http_status = 404


class PolicyInvalidError(GatewayError):
    code = "policy_invalid"
    http_status = 422


# --- Provider ---


class ProviderError(GatewayError):
    code = "provider_error"
    http_status = 502


class ProviderNotFoundError(GatewayError):
    code = "provider_not_found"
    http_status = 400


# --- Retry ---


class MaxRetriesExceededError(GatewayError):
    code = "max_retries_exceeded"
    http_status = 422
