"""Dependency injection container."""

from app.core.config import Settings, get_settings
from app.guardrails.input.jailbreak import JailbreakDetector
from app.guardrails.input.language import LanguageValidator
from app.guardrails.input.pii import PIIDetector
from app.guardrails.input.prompt_injection import PromptInjectionDetector
from app.guardrails.input.secrets import SecretDetector
from app.guardrails.input.token_length import TokenLengthValidator
from app.guardrails.input.toxicity import ToxicityDetector
from app.guardrails.output.hallucination import HallucinationGuard
from app.guardrails.output.json_schema import JSONSchemaValidator
from app.guardrails.output.off_topic import OffTopicDetector
from app.guardrails.output.prompt_leakage import PromptLeakageDetector
from app.guardrails.output.secret_leakage import SecretLeakageDetector
from app.guardrails.output.toxicity import OutputToxicityDetector
from app.providers.factory import ProviderFactory
from app.services.gateway import GatewayService
from app.services.output_validation import OutputValidationService
from app.services.policy import PolicyService
from app.services.validation import ValidationService


def _build_input_validation_service() -> ValidationService:
    return ValidationService(
        [
            PromptInjectionDetector(),
            JailbreakDetector(),
            PIIDetector(),
            SecretDetector(),
            TokenLengthValidator(),
            LanguageValidator(),
            ToxicityDetector(),
        ]
    )


def _build_output_validation_service() -> OutputValidationService:
    return OutputValidationService(
        [
            JSONSchemaValidator(),
            OutputToxicityDetector(),
            PromptLeakageDetector(),
            SecretLeakageDetector(),
            OffTopicDetector(),
            HallucinationGuard(),
        ]
    )


class Container:
    """Holds singleton service instances for the application lifetime."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider_factory = ProviderFactory()
        self.input_validation_service = _build_input_validation_service()
        self.output_validation_service = _build_output_validation_service()
        self.policy_service = PolicyService(
            policy_dir=settings.policy_dir,
            default_policy_id=settings.default_policy_id,
        )
        self.gateway_service = GatewayService(
            policy_service=self.policy_service,
            provider_factory=self.provider_factory,
            input_validator=self.input_validation_service,
            output_validator=self.output_validation_service,
        )

    def startup(self) -> None:
        self.policy_service.startup()

    def shutdown(self) -> None:
        self.policy_service.shutdown()


_container: Container | None = None


def init_container() -> Container:
    global _container
    _container = Container(settings=get_settings())
    _container.startup()
    return _container


def get_container() -> Container:
    if _container is None:
        raise RuntimeError("Container not initialised — call init_container() first")
    return _container
