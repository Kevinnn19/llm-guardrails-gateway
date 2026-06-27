"""Policy domain models — typed representation of a policy YAML file.

Every field matches the default.yaml schema. Pydantic validates on load,
so an invalid YAML never silently reaches the guardrail chain.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

Action = Literal["block", "warn", "log"]


class _GuardrailBase(BaseModel):
    enabled: bool = True
    action: Action = "block"


# ---------------------------------------------------------------------------
# Input guardrail configs
# ---------------------------------------------------------------------------

class PromptInjectionConfig(_GuardrailBase):
    threshold: float = Field(default=0.75, ge=0.0, le=1.0)


class JailbreakConfig(_GuardrailBase):
    threshold: float = Field(default=0.75, ge=0.0, le=1.0)


class PIIConfig(_GuardrailBase):
    entities: list[str] = ["EMAIL", "PHONE", "SSN", "CREDIT_CARD"]


class SecretsConfig(_GuardrailBase):
    pass


class TokenLengthConfig(_GuardrailBase):
    max_tokens: int = Field(default=4096, gt=0)


class LanguageConfig(_GuardrailBase):
    enabled: bool = False
    allowed: list[str] = ["en"]


class ToxicityInputConfig(_GuardrailBase):
    threshold: float = Field(default=0.85, ge=0.0, le=1.0)


class InputGuardrailsConfig(BaseModel):
    prompt_injection: PromptInjectionConfig = Field(default_factory=PromptInjectionConfig)
    jailbreak: JailbreakConfig = Field(default_factory=JailbreakConfig)
    pii: PIIConfig = Field(default_factory=PIIConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    token_length: TokenLengthConfig = Field(default_factory=TokenLengthConfig)
    language: LanguageConfig = Field(default_factory=LanguageConfig)
    toxicity: ToxicityInputConfig = Field(default_factory=ToxicityInputConfig)


# ---------------------------------------------------------------------------
# Output guardrail configs
# ---------------------------------------------------------------------------

class JSONSchemaConfig(_GuardrailBase):
    enabled: bool = False
    schema_ref: str | None = None
    enforce_json: bool = False


class ToxicityOutputConfig(_GuardrailBase):
    threshold: float = Field(default=0.85, ge=0.0, le=1.0)


class PromptLeakageConfig(_GuardrailBase):
    pass


class SecretLeakageConfig(_GuardrailBase):
    pass


class OffTopicConfig(_GuardrailBase):
    enabled: bool = False
    action: Action = "warn"


class HallucinationConfig(_GuardrailBase):
    enabled: bool = False
    action: Action = "warn"


class OutputGuardrailsConfig(BaseModel):
    json_schema: JSONSchemaConfig = Field(default_factory=JSONSchemaConfig)
    toxicity: ToxicityOutputConfig = Field(default_factory=ToxicityOutputConfig)
    prompt_leakage: PromptLeakageConfig = Field(default_factory=PromptLeakageConfig)
    secret_leakage: SecretLeakageConfig = Field(default_factory=SecretLeakageConfig)
    off_topic: OffTopicConfig = Field(default_factory=OffTopicConfig)
    hallucination: HallucinationConfig = Field(default_factory=HallucinationConfig)


# ---------------------------------------------------------------------------
# Provider config
# ---------------------------------------------------------------------------

class ProviderConfig(BaseModel):
    name: str = "openai"
    model: str = "gpt-4o"
    timeout_seconds: float = Field(default=30.0, gt=0)


# ---------------------------------------------------------------------------
# Retry config
# ---------------------------------------------------------------------------

RetryStrategy = Literal["correct_and_retry", "static_fallback"]


class RetryConfig(BaseModel):
    max_attempts: int = Field(default=3, ge=0)
    strategy: RetryStrategy = "correct_and_retry"
    fallback_message: str = (
        "I'm unable to process this request safely. Please rephrase or contact support."
    )


# ---------------------------------------------------------------------------
# Compliance config
# ---------------------------------------------------------------------------

class ComplianceConfig(BaseModel):
    block_topics: list[str] = []
    require_citations: bool = False
    block_competitors: list[str] = []


# ---------------------------------------------------------------------------
# Root policy model
# ---------------------------------------------------------------------------

class Policy(BaseModel):
    id: str
    version: str = "1.0"
    description: str = ""
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    input_guardrails: InputGuardrailsConfig = Field(default_factory=InputGuardrailsConfig)
    output_guardrails: OutputGuardrailsConfig = Field(default_factory=OutputGuardrailsConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)

    def litellm_model(self) -> str:
        """Return the LiteLLM-routed model string, e.g. 'openai/gpt-4o'."""
        name = self.provider.name
        model = self.provider.model
        # Avoid double-prefixing if model already contains a slash
        return model if "/" in model else f"{name}/{model}"

    def enabled_input_guardrails(self) -> list[str]:
        ig = self.input_guardrails
        return [
            name for name, cfg in {
                "prompt_injection": ig.prompt_injection,
                "jailbreak": ig.jailbreak,
                "pii": ig.pii,
                "secrets": ig.secrets,
                "token_length": ig.token_length,
                "language": ig.language,
                "toxicity": ig.toxicity,
            }.items()
            if cfg.enabled
        ]

    def enabled_output_guardrails(self) -> list[str]:
        og = self.output_guardrails
        return [
            name for name, cfg in {
                "json_schema": og.json_schema,
                "toxicity": og.toxicity,
                "prompt_leakage": og.prompt_leakage,
                "secret_leakage": og.secret_leakage,
                "off_topic": og.off_topic,
                "hallucination": og.hallucination,
            }.items()
            if cfg.enabled
        ]
