"""Unit tests for the policy layer: models, loader, service, and policy-aware validation."""

import textwrap
from pathlib import Path

import pytest

from app.core.exceptions import PolicyInvalidError, PolicyNotFoundError
from app.guardrails.input.prompt_injection import PromptInjectionDetector
from app.guardrails.input.pii import PIIDetector
from app.guardrails.input.token_length import TokenLengthValidator
from app.policies.loader import PolicyLoader
from app.policies.models import Policy, InputGuardrailsConfig
from app.services.policy import PolicyService
from app.services.validation import ValidationService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DEFAULT_YAML = textwrap.dedent("""\
    id: test_policy
    version: "1.0"
    provider:
      name: openai
      model: gpt-4o
    input_guardrails:
      prompt_injection:
        enabled: true
        threshold: 0.75
      pii:
        enabled: true
        entities: [EMAIL]
      token_length:
        enabled: true
        max_tokens: 100
      language:
        enabled: false
    output_guardrails:
      toxicity:
        enabled: true
    retry:
      max_attempts: 2
""")


@pytest.fixture()
def policy_dir(tmp_path: Path) -> Path:
    (tmp_path / "test_policy.yaml").write_text(DEFAULT_YAML, encoding="utf-8")
    return tmp_path


@pytest.fixture()
def loader() -> PolicyLoader:
    return PolicyLoader()


@pytest.fixture()
def policy(loader: PolicyLoader, policy_dir: Path) -> Policy:
    return loader.load(policy_dir / "test_policy.yaml")


# ---------------------------------------------------------------------------
# PolicyLoader
# ---------------------------------------------------------------------------

class TestPolicyLoader:
    def test_load_valid_yaml(self, loader: PolicyLoader, policy_dir: Path) -> None:
        p = loader.load(policy_dir / "test_policy.yaml")
        assert p.id == "test_policy"
        assert p.version == "1.0"

    def test_load_injects_id_from_filename(self, loader: PolicyLoader, tmp_path: Path) -> None:
        yaml_path = tmp_path / "my_custom.yaml"
        yaml_path.write_text("version: '2.0'\n", encoding="utf-8")
        p = loader.load(yaml_path)
        assert p.id == "my_custom"

    def test_load_missing_file_raises(self, loader: PolicyLoader, tmp_path: Path) -> None:
        with pytest.raises(PolicyNotFoundError):
            loader.load(tmp_path / "nonexistent.yaml")

    def test_load_invalid_yaml_raises(self, loader: PolicyLoader, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("key: [unclosed bracket\n", encoding="utf-8")
        with pytest.raises(PolicyInvalidError, match="YAML parse error"):
            loader.load(bad)

    def test_load_non_mapping_raises(self, loader: PolicyLoader, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(PolicyInvalidError, match="must be a YAML mapping"):
            loader.load(bad)

    def test_load_directory_returns_all(self, loader: PolicyLoader, policy_dir: Path, tmp_path: Path) -> None:
        # Add a second valid policy
        (policy_dir / "second.yaml").write_text("id: second\nversion: '1.0'\n", encoding="utf-8")
        policies = loader.load_directory(policy_dir)
        assert "test_policy" in policies
        assert "second" in policies

    def test_load_directory_skips_invalid(self, loader: PolicyLoader, policy_dir: Path) -> None:
        (policy_dir / "broken.yaml").write_text("key: [unclosed\n", encoding="utf-8")
        # Should not raise — just skips broken file
        policies = loader.load_directory(policy_dir)
        assert "test_policy" in policies
        assert "broken" not in policies

    def test_load_directory_empty_dir(self, loader: PolicyLoader, tmp_path: Path) -> None:
        assert loader.load_directory(tmp_path) == {}


# ---------------------------------------------------------------------------
# Policy model helpers
# ---------------------------------------------------------------------------

class TestPolicyModel:
    def test_litellm_model_no_slash(self, policy: Policy) -> None:
        assert policy.litellm_model() == "openai/gpt-4o"

    def test_litellm_model_already_prefixed(self) -> None:
        p = Policy(id="x", provider={"name": "openai", "model": "openai/gpt-4o"})  # type: ignore[arg-type]
        assert p.litellm_model() == "openai/gpt-4o"

    def test_enabled_input_guardrails(self, policy: Policy) -> None:
        enabled = policy.enabled_input_guardrails()
        assert "prompt_injection" in enabled
        assert "pii" in enabled
        assert "language" not in enabled  # disabled in fixture

    def test_enabled_output_guardrails(self, policy: Policy) -> None:
        enabled = policy.enabled_output_guardrails()
        assert "toxicity" in enabled
        assert "json_schema" not in enabled  # disabled by default

    def test_defaults_are_sane(self) -> None:
        p = Policy(id="minimal")
        assert p.retry.max_attempts == 3
        assert p.provider.model == "gpt-4o"
        assert p.input_guardrails.pii.enabled is True


# ---------------------------------------------------------------------------
# PolicyService
# ---------------------------------------------------------------------------

class TestPolicyService:
    def test_get_loaded_policy(self, policy_dir: Path) -> None:
        svc = PolicyService(policy_dir)
        svc.reload_all()
        p = svc.get("test_policy")
        assert p.id == "test_policy"

    def test_get_missing_raises(self, policy_dir: Path) -> None:
        svc = PolicyService(policy_dir)
        svc.reload_all()
        with pytest.raises(PolicyNotFoundError):
            svc.get("does_not_exist")

    def test_get_default_when_none(self, policy_dir: Path) -> None:
        svc = PolicyService(policy_dir, default_policy_id="test_policy")
        svc.reload_all()
        assert svc.get(None).id == "test_policy"

    def test_list_all(self, policy_dir: Path) -> None:
        svc = PolicyService(policy_dir)
        svc.reload_all()
        assert len(svc.list_all()) == 1

    def test_policy_ids(self, policy_dir: Path) -> None:
        svc = PolicyService(policy_dir)
        svc.reload_all()
        assert "test_policy" in svc.policy_ids()

    def test_reload_one(self, policy_dir: Path) -> None:
        svc = PolicyService(policy_dir)
        svc.reload_all()
        # Modify file and reload
        (policy_dir / "test_policy.yaml").write_text(
            DEFAULT_YAML.replace('version: "1.0"', 'version: "2.0"'), encoding="utf-8"
        )
        svc.reload_one("test_policy")
        assert svc.get("test_policy").version == "2.0"

    def test_reload_one_missing_raises(self, policy_dir: Path) -> None:
        svc = PolicyService(policy_dir)
        svc.reload_all()
        with pytest.raises(PolicyNotFoundError):
            svc.reload_one("ghost")

    def test_reload_all_returns_loaded_ids(self, policy_dir: Path) -> None:
        svc = PolicyService(policy_dir)
        loaded, errors = svc.reload_all()
        assert "test_policy" in loaded
        assert errors == {}

    def test_reload_all_missing_dir(self, tmp_path: Path) -> None:
        svc = PolicyService(tmp_path / "nonexistent")
        loaded, errors = svc.reload_all()
        assert loaded == []

    def test_on_file_change_reloads(self, policy_dir: Path) -> None:
        svc = PolicyService(policy_dir)
        svc.reload_all()
        (policy_dir / "test_policy.yaml").write_text(
            DEFAULT_YAML.replace('version: "1.0"', 'version: "3.0"'), encoding="utf-8"
        )
        svc._on_file_change(policy_dir / "test_policy.yaml")
        assert svc.get("test_policy").version == "3.0"


# ---------------------------------------------------------------------------
# ValidationService.validate_with_policy
# ---------------------------------------------------------------------------

class TestValidationServiceWithPolicy:
    def _make_svc(self) -> ValidationService:
        return ValidationService([
            PromptInjectionDetector(),
            PIIDetector(),
            TokenLengthValidator(),
        ])

    def _make_policy(self, overrides: dict) -> Policy:
        """Build a Policy from DEFAULT_YAML with inline overrides via loader."""
        import yaml
        base = yaml.safe_load(DEFAULT_YAML)
        base.update(overrides)
        return Policy.model_validate(base)

    def test_policy_enabled_guardrail_runs(self) -> None:
        svc = self._make_svc()
        policy = self._make_policy({})
        # PII is enabled — email should be caught
        r = svc.validate_with_policy("contact alice@test.com", policy)
        assert not r.passed
        assert any(v.guardrail == "PIIDetector" for v in r.violations)

    def test_policy_disabled_guardrail_skipped(self) -> None:
        svc = self._make_svc()
        # Disable PII
        import yaml
        raw = yaml.safe_load(DEFAULT_YAML)
        raw["input_guardrails"]["pii"]["enabled"] = False
        policy = Policy.model_validate(raw)
        r = svc.validate_with_policy("contact alice@test.com", policy)
        # PII disabled — no violation for email
        assert not any(v.guardrail == "PIIDetector" for v in r.violations)

    def test_policy_token_limit_applied(self) -> None:
        svc = self._make_svc()
        # max_tokens: 100 in fixture → ~400 chars
        long_text = "word " * 200  # ~200 tokens >> 100
        policy = self._make_policy({})
        r = svc.validate_with_policy(long_text, policy)
        assert not r.passed
        assert any(v.code == "token_limit_exceeded" for v in r.violations)

    def test_clean_input_passes_all(self) -> None:
        svc = self._make_svc()
        policy = self._make_policy({})
        r = svc.validate_with_policy("What is the capital of France?", policy)
        assert r.passed

    def test_unknown_guardrail_name_is_skipped_gracefully(self) -> None:
        """A guardrail not in the config map is simply skipped — no crash."""
        from app.guardrails.base import AbstractGuardrail, GuardrailContext
        from app.guardrails.result import ValidationResult

        class WeirdGuardrail(AbstractGuardrail):
            @property
            def name(self) -> str:
                return "WeirdGuardrailNotInMap"
            def validate(self, content: str, context: GuardrailContext | None = None) -> ValidationResult:
                return ValidationResult.ok()

        svc = ValidationService([WeirdGuardrail()])
        policy = self._make_policy({})
        r = svc.validate_with_policy("hello", policy)
        assert r.passed
