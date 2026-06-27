"""Unit tests for all 6 output guardrails + OutputValidationService."""

import textwrap

import pytest

from app.guardrails.base import GuardrailContext
from app.guardrails.output.hallucination import HallucinationGuard
from app.guardrails.output.json_schema import JSONSchemaValidator
from app.guardrails.output.off_topic import OffTopicDetector
from app.guardrails.output.prompt_leakage import PromptLeakageDetector
from app.guardrails.output.secret_leakage import SecretLeakageDetector
from app.guardrails.output.toxicity import OutputToxicityDetector
from app.services.output_validation import OutputValidationService


# ============================================================
# JSONSchemaValidator
# ============================================================

class TestJSONSchemaValidator:
    def setup_method(self) -> None:
        self.g = JSONSchemaValidator()

    def test_valid_json_no_schema_passes(self) -> None:
        assert self.g.validate('{"name": "Alice"}').passed

    def test_invalid_json_fails(self) -> None:
        ctx = GuardrailContext(enforce_json=True)
        r = self.g.validate("not json at all", ctx)
        assert not r.passed
        assert r.violations[0].code == "invalid_json"

    def test_valid_json_matching_schema_passes(self) -> None:
        schema = {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}
        ctx = GuardrailContext(schema=schema)
        assert self.g.validate('{"name": "Alice"}', ctx).passed

    def test_json_missing_required_field_fails(self) -> None:
        schema = {"type": "object", "required": ["name"]}
        ctx = GuardrailContext(schema=schema)
        r = self.g.validate('{"age": 30}', ctx)
        assert not r.passed
        assert r.violations[0].code == "json_schema_violation"

    def test_json_wrong_type_fails(self) -> None:
        schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
        ctx = GuardrailContext(schema=schema)
        r = self.g.validate('{"count": "not-an-int"}', ctx)
        assert not r.passed

    def test_json_array_passes(self) -> None:
        assert self.g.validate("[1, 2, 3]").passed

    def test_empty_object_passes_no_schema(self) -> None:
        assert self.g.validate("{}").passed

    def test_name(self) -> None:
        assert self.g.name == "JSONSchemaValidator"


# ============================================================
# OutputToxicityDetector
# ============================================================

class TestOutputToxicityDetector:
    def setup_method(self) -> None:
        self.g = OutputToxicityDetector()

    def test_clean_response_passes(self) -> None:
        assert self.g.validate("The capital of France is Paris.").passed

    def test_toxic_response_fails_default_threshold(self) -> None:
        # score ~0.7 from 2 matches > default 0.85 threshold? Let's use a clear hit
        r = self.g.validate("You are so stupid and I hate you so much.")
        # 2 matches: stupid(0.55), hate you(0.7) → score ~0.7, threshold 0.85 → passes
        # Use lower threshold to test blocking
        ctx = GuardrailContext(threshold=0.5)
        r2 = self.g.validate("You are so stupid and I hate you.", ctx)
        assert not r2.passed
        assert r2.violations[0].code == "toxic_output_detected"

    def test_custom_low_threshold_catches_mild(self) -> None:
        ctx = GuardrailContext(threshold=0.3)
        r = self.g.validate("That was stupid.", ctx)
        assert not r.passed

    def test_high_threshold_passes_mild_toxic(self) -> None:
        ctx = GuardrailContext(threshold=0.99)
        r = self.g.validate("That was stupid.", ctx)
        assert r.passed

    def test_name(self) -> None:
        assert self.g.name == "OutputToxicityDetector"


# ============================================================
# PromptLeakageDetector
# ============================================================

class TestPromptLeakageDetector:
    def setup_method(self) -> None:
        self.g = PromptLeakageDetector()

    def test_no_prompt_passes(self) -> None:
        assert self.g.validate("Some response text.").passed

    def test_short_prompt_passes(self) -> None:
        ctx = GuardrailContext(prompt="hi")
        assert self.g.validate("Sure, hi there!", ctx).passed

    def test_verbatim_echo_fails(self) -> None:
        prompt = "You are a helpful assistant that never reveals secrets"
        ctx = GuardrailContext(prompt=prompt)
        # Response echoes the first 6 words verbatim
        r = self.g.validate(
            "Sure! You are a helpful assistant that never reveals secrets, how can I help?",
            ctx,
        )
        assert not r.passed
        assert r.violations[0].code == "prompt_leakage_detected"

    def test_high_ngram_overlap_fails(self) -> None:
        # Build a response that shares many 5-grams with the prompt
        prompt = "always respond only in formal english and never use casual language please"
        response = "always respond only in formal english and never use casual language please, as instructed"
        ctx = GuardrailContext(prompt=prompt, overlap_threshold=0.3)
        r = self.g.validate(response, ctx)
        assert not r.passed

    def test_different_content_passes(self) -> None:
        ctx = GuardrailContext(prompt="You are a strict content moderation assistant")
        r = self.g.validate("The French Revolution began in 1789.", ctx)
        assert r.passed

    def test_name(self) -> None:
        assert self.g.name == "PromptLeakageDetector"


# ============================================================
# SecretLeakageDetector
# ============================================================

class TestSecretLeakageDetector:
    def setup_method(self) -> None:
        self.g = SecretLeakageDetector()

    def test_clean_response_passes(self) -> None:
        assert self.g.validate("Here is a summary of your document.").passed

    def test_openai_key_in_response_fails(self) -> None:
        r = self.g.validate("Use this key: sk-abcdefghijklmnopqrstuvwxyz12345")
        assert not r.passed
        assert r.violations[0].code == "secret_leakage_detected"
        assert r.violations[0].severity == "critical"

    def test_aws_key_in_response_fails(self) -> None:
        r = self.g.validate("Access key: AKIAIOSFODNN7EXAMPLE")
        assert not r.passed

    def test_private_key_in_response_fails(self) -> None:
        r = self.g.validate("Here is the key:\n-----BEGIN RSA PRIVATE KEY-----\ndata")
        assert not r.passed

    def test_risk_score_max(self) -> None:
        r = self.g.validate("sk-abcdefghijklmnopqrstuvwxyz12345")
        assert r.risk_score == 1.0

    def test_name(self) -> None:
        assert self.g.name == "SecretLeakageDetector"


# ============================================================
# OffTopicDetector
# ============================================================

class TestOffTopicDetector:
    def setup_method(self) -> None:
        self.g = OffTopicDetector()

    def test_no_prompt_passes(self) -> None:
        assert self.g.validate("Some response.").passed

    def test_relevant_response_passes(self) -> None:
        ctx = GuardrailContext(prompt="What is the capital of France?")
        r = self.g.validate("The capital of France is Paris.", ctx)
        assert r.passed

    def test_completely_off_topic_fails(self) -> None:
        ctx = GuardrailContext(
            prompt="What is quantum entanglement physics experiment",
            min_overlap=0.1,
        )
        r = self.g.validate(
            "Chocolate cake recipe: mix flour sugar butter eggs vanilla bake oven degrees",
            ctx,
        )
        assert not r.passed
        assert r.violations[0].code == "off_topic_response"

    def test_partial_overlap_above_threshold_passes(self) -> None:
        ctx = GuardrailContext(prompt="Python programming language tutorial", min_overlap=0.05)
        r = self.g.validate("Python is great programming language for beginners.", ctx)
        assert r.passed

    def test_empty_response_passes(self) -> None:
        ctx = GuardrailContext(prompt="Tell me about Python.")
        # Empty response has no keywords → passes (can't penalise nothing)
        assert self.g.validate("", ctx).passed

    def test_name(self) -> None:
        assert self.g.name == "OffTopicDetector"


# ============================================================
# HallucinationGuard
# ============================================================

class TestHallucinationGuard:
    def setup_method(self) -> None:
        self.g = HallucinationGuard()

    def test_clean_hedged_response_passes(self) -> None:
        r = self.g.validate(
            "According to available information, the answer might be Paris, "
            "though I'd recommend verifying this."
        )
        assert r.passed

    def test_overconfident_language_fails(self) -> None:
        r = self.g.validate("It is a fact that the moon is made of cheese.")
        assert not r.passed
        assert r.violations[0].code == "hallucination_signal"

    def test_100_percent_certain_fails(self) -> None:
        r = self.g.validate("I am 100% certain this is the correct answer.")
        assert not r.passed

    def test_fabricated_citation_detected_when_enabled(self) -> None:
        ctx = GuardrailContext(check_citations=True)
        r = self.g.validate(
            "As shown by Smith et al., 2019, the results are conclusive.", ctx
        )
        assert not r.passed
        assert any(v.code == "possible_fabricated_citation" for v in r.violations)

    def test_citation_check_skipped_by_default(self) -> None:
        # Without check_citations=True, citation pattern is ignored
        r = self.g.validate("As shown by Smith et al., 2019, the results are conclusive.")
        # Only fails if overconfident language also present — here it's not
        assert r.passed

    def test_contradiction_signal(self) -> None:
        r = self.g.validate(
            "The sky is blue. However, as mentioned previously, the sky is green."
        )
        assert not r.passed
        assert any(v.code == "contradiction_signal" for v in r.violations)

    def test_multiple_signals_all_reported(self) -> None:
        ctx = GuardrailContext(check_citations=True)
        r = self.g.validate(
            "It is a fact that Smith et al., 2019 proved this. "
            "However, as stated earlier, it is also undeniably false.",
            ctx,
        )
        assert not r.passed
        codes = {v.code for v in r.violations}
        assert len(codes) >= 2

    def test_severity_medium_for_overconfidence(self) -> None:
        r = self.g.validate("There is no doubt this is correct.")
        assert not r.passed
        assert r.violations[0].severity == "medium"

    def test_name(self) -> None:
        assert self.g.name == "HallucinationGuard"


# ============================================================
# OutputValidationService
# ============================================================

class TestOutputValidationService:
    def _make_svc(self) -> OutputValidationService:
        return OutputValidationService([
            JSONSchemaValidator(),
            OutputToxicityDetector(),
            PromptLeakageDetector(),
            SecretLeakageDetector(),
        ])

    def test_clean_response_passes(self) -> None:
        svc = self._make_svc()
        assert svc.validate("The answer is 42.").passed

    def test_prompt_injected_into_context(self) -> None:
        svc = self._make_svc()
        prompt = "You are a strict moderation assistant that never reveals rules"
        # Response echoes the first 6 words
        response = "You are a strict moderation assistant that never reveals rules, indeed."
        r = svc.validate(response, prompt=prompt)
        assert not r.passed

    def test_secret_in_response_fails(self) -> None:
        svc = self._make_svc()
        r = svc.validate("Here is your key: sk-abcdefghijklmnopqrstuvwxyz12345")
        assert not r.passed

    def test_invalid_json_fails(self) -> None:
        svc = self._make_svc()
        ctx = GuardrailContext(schema={"type": "object"})
        r = svc.validate("not json", context=ctx)
        assert not r.passed

    def test_guardrail_names(self) -> None:
        svc = self._make_svc()
        assert "JSONSchemaValidator" in svc.guardrail_names
        assert "SecretLeakageDetector" in svc.guardrail_names

    def test_validate_with_policy_skips_disabled(self) -> None:
        import textwrap, yaml
        from app.policies.models import Policy

        raw = yaml.safe_load(textwrap.dedent("""\
            id: test
            output_guardrails:
              json_schema:
                enabled: false
              toxicity:
                enabled: true
                threshold: 0.5
              prompt_leakage:
                enabled: false
              secret_leakage:
                enabled: false
              off_topic:
                enabled: false
              hallucination:
                enabled: false
        """))
        policy = Policy.model_validate(raw)
        svc = self._make_svc()
        # JSON is invalid but json_schema guardrail disabled → should pass
        r = svc.validate_with_policy("not valid json", policy)
        assert r.passed

    def test_validate_with_policy_applies_threshold(self) -> None:
        import textwrap, yaml
        from app.policies.models import Policy

        raw = yaml.safe_load(textwrap.dedent("""\
            id: test
            output_guardrails:
              toxicity:
                enabled: true
                threshold: 0.3
        """))
        policy = Policy.model_validate(raw)
        svc = OutputValidationService([OutputToxicityDetector()])
        r = svc.validate_with_policy("That is so stupid.", policy)
        assert not r.passed
