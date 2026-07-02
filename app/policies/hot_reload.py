"""PolicyHotReloader — watches a directory for YAML changes and reloads policies.

Uses watchdog's Observer in a background thread. When any .yaml file in the
watched directory is created or modified, the registered callback is called
with the changed file path so PolicyService can reload just that policy.

The reloader is fully decoupled from PolicyService — it only calls a callback.
This makes it independently testable and replaceable (e.g. swap watchdog for
inotify on Linux without touching PolicyService).
"""

import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import (
    FileCreatedEvent,
    FileModifiedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from app.core.logging import logger


class _PolicyFileHandler(FileSystemEventHandler):
    """Handles FS events — delegates to the reload callback for .yaml files."""

    def __init__(self, on_change: Callable[[Path], None]) -> None:
        super().__init__()
        self._on_change = on_change

    def _handle(self, event: FileSystemEvent) -> None:
        path = Path(str(event.src_path))
        if path.suffix == ".yaml":
            logger.info("policy_file_changed path={}", path.name)
            self._on_change(path)

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._handle(event)

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._handle(event)


class PolicyHotReloader:
    """Watches a directory and calls *on_change* whenever a .yaml file changes."""

    def __init__(self, watch_dir: Path, on_change: Callable[[Path], None]) -> None:
        self._watch_dir = watch_dir
        self._handler = _PolicyFileHandler(on_change)
        self._observer: BaseObserver | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the background file-watcher thread."""
        with self._lock:
            if self._observer is not None:
                return  # already running
            observer = Observer()
            observer.schedule(self._handler, str(self._watch_dir), recursive=False)
            observer.start()
            self._observer = observer
            logger.info("policy_hot_reload started dir={}", self._watch_dir)

    def stop(self) -> None:
        """Stop the file-watcher thread gracefully."""
        with self._lock:
            if self._observer is None:
                return
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("policy_hot_reload stopped")

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()
