"""JSON schema validator for LLM responses."""

import json
from typing import Any

import jsonschema

from app.guardrails.base import AbstractGuardrail, GuardrailContext
from app.guardrails.result import ValidationResult, Violation


class JSONSchemaValidator(AbstractGuardrail):
    """Checks that the LLM response is valid JSON and matches an expected schema.

    Only activates when context contains 'schema' (a JSON Schema dict) or
    'enforce_json=True'. Without either, plain-text responses pass through.
    """

    @property
    def name(self) -> str:
        return "JSONSchemaValidator"

    def validate(self, content: str, context: GuardrailContext | None = None) -> ValidationResult:
        ctx = context or {}
        schema: dict[str, Any] | None = ctx.get("schema")
        enforce_json: bool = bool(ctx.get("enforce_json", False))

        if not enforce_json and schema is None:
            return ValidationResult.ok()

        try:
            parsed: Any = json.loads(content)
        except json.JSONDecodeError as exc:
            return ValidationResult.fail(
                violations=[Violation(
                    guardrail=self.name,
                    code="invalid_json",
                    message=f"Response is not valid JSON: {exc.msg}",
                    severity="high",
                    score=0.9,
                )],
                risk_score=0.9,
            )

        if schema is None:
            return ValidationResult.ok()

        try:
            jsonschema.validate(instance=parsed, schema=schema)
        except jsonschema.ValidationError as exc:
            return ValidationResult.fail(
                violations=[Violation(
                    guardrail=self.name,
                    code="json_schema_violation",
                    message=f"Schema violation: {exc.message}",
                    severity="high",
                    score=0.85,
                )],
                risk_score=0.85,
            )

        return ValidationResult.ok()
