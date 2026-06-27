"""PolicyLoader — reads a YAML file and returns a validated Policy model.

Raises PolicyInvalidError if the YAML is malformed or fails Pydantic validation.
Raises PolicyNotFoundError if the file does not exist.
"""

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.core.exceptions import PolicyInvalidError, PolicyNotFoundError
from app.core.logging import logger
from app.policies.models import Policy


class PolicyLoader:
    """Loads and validates Policy objects from YAML files on disk."""

    def load(self, path: Path) -> Policy:
        """Parse *path* into a validated Policy.

        Args:
            path: Absolute or relative path to a .yaml policy file.

        Returns:
            Validated Policy instance.

        Raises:
            PolicyNotFoundError: File does not exist.
            PolicyInvalidError:  YAML parse error or Pydantic validation failure.
        """
        if not path.exists():
            raise PolicyNotFoundError(f"Policy file not found: {path}")

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise PolicyInvalidError(f"YAML parse error in {path.name}: {exc}") from exc

        if not isinstance(raw, dict):
            raise PolicyInvalidError(f"Policy file {path.name} must be a YAML mapping")

        # Inject filename stem as id if not present
        raw.setdefault("id", path.stem)

        try:
            policy = Policy.model_validate(raw)
        except ValidationError as exc:
            raise PolicyInvalidError(
                f"Policy validation failed for {path.name}: {exc}"
            ) from exc

        logger.debug("policy_loaded id={} version={}", policy.id, policy.version)
        return policy

    def load_directory(self, directory: Path) -> dict[str, Policy]:
        """Load all .yaml files in *directory*, keyed by policy id.

        Skips files that fail to load (logs a warning) so one bad file
        doesn't block all others from loading.
        """
        policies: dict[str, Policy] = {}
        for yaml_file in sorted(directory.glob("*.yaml")):
            try:
                policy = self.load(yaml_file)
                policies[policy.id] = policy
            except (PolicyNotFoundError, PolicyInvalidError) as exc:
                logger.warning(
                    "Skipping invalid policy file {}: {}", yaml_file.name, exc
                )
        return policies
