"""PolicyService — the authoritative in-memory policy store.

Responsibilities:
  - Load all policies from the policy directory at startup.
  - Serve policies by id (raises PolicyNotFoundError if absent).
  - Expose reload_one() and reload_all() for the API and the hot-reloader.
  - Start/stop the PolicyHotReloader background thread.

The internal cache (_policies dict) is protected by a read/write lock so
hot-reload writes never race with request-time reads.
"""

import threading
from pathlib import Path

from app.core.exceptions import PolicyNotFoundError
from app.core.logging import logger
from app.policies.hot_reload import PolicyHotReloader
from app.policies.loader import PolicyLoader
from app.policies.models import Policy


class PolicyService:
    """Thread-safe in-memory policy store with hot-reload support."""

    def __init__(self, policy_dir: Path, default_policy_id: str = "default") -> None:
        self._dir = policy_dir
        self._default_id = default_policy_id
        self._loader = PolicyLoader()
        self._policies: dict[str, Policy] = {}
        self._lock = threading.RLock()
        self._reloader = PolicyHotReloader(
            watch_dir=policy_dir,
            on_change=self._on_file_change,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(self) -> None:
        """Load all policies and start the file watcher."""
        self.reload_all()
        if self._dir.exists():
            self._reloader.start()

    def shutdown(self) -> None:
        """Stop the file watcher."""
        self._reloader.stop()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, policy_id: str | None = None) -> Policy:
        """Return the policy for *policy_id*, or the default policy if None."""
        pid = policy_id or self._default_id
        with self._lock:
            policy = self._policies.get(pid)
        if policy is None:
            raise PolicyNotFoundError(f"Policy '{pid}' not found")
        return policy

    def list_all(self) -> list[Policy]:
        with self._lock:
            return list(self._policies.values())

    def policy_ids(self) -> list[str]:
        with self._lock:
            return list(self._policies.keys())

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload_all(self) -> tuple[list[str], dict[str, str]]:
        """Reload every .yaml file from disk. Returns (loaded_ids, errors)."""
        loaded: list[str] = []
        errors: dict[str, str] = {}

        if not self._dir.exists():
            logger.warning("Policy directory does not exist: {}", self._dir)
            return loaded, errors

        new_policies = self._loader.load_directory(self._dir)
        with self._lock:
            self._policies = new_policies

        loaded = list(new_policies.keys())
        logger.info("policies_reloaded count={} ids={}", len(loaded), loaded)
        return loaded, errors

    def reload_one(self, policy_id: str) -> None:
        """Reload a single policy by id. Raises PolicyNotFoundError if missing."""
        path = self._dir / f"{policy_id}.yaml"
        policy = self._loader.load(
            path
        )  # raises PolicyNotFoundError/PolicyInvalidError
        with self._lock:
            self._policies[policy.id] = policy
        logger.info("policy_reloaded id={}", policy.id)

    def _on_file_change(self, path: Path) -> None:
        """Callback from PolicyHotReloader — reload the changed policy file."""
        policy_id = path.stem
        try:
            self.reload_one(policy_id)
        except Exception as exc:
            logger.error("policy_reload_failed id={} error={}", policy_id, exc)
