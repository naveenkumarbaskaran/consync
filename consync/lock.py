"""Lock file — advisory locking to prevent concurrent sync operations.

Uses a .consync.lock file in the project root during sync. If another
process is already syncing, the lock prevents corruption.

Features:
  - Advisory lock (not system-level flock — works on all OSes)
  - Stale lock detection (PID check — if process is dead, lock is reclaimed)
  - Configurable timeout
"""

from __future__ import annotations

import json
import logging
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

LOCK_FILENAME = ".consync.lock"
LOCK_TIMEOUT_SECONDS = 30  # Max age before considering stale


class LockError(Exception):
    """Raised when a lock cannot be acquired."""
    pass


class SyncLock:
    """Advisory lock file for preventing concurrent sync operations.

    Usage:
        with SyncLock(project_dir):
            # ... do sync ...
    """

    def __init__(self, project_dir: Path | None = None, timeout: float = LOCK_TIMEOUT_SECONDS):
        self.project_dir = project_dir or Path.cwd()
        self.lock_path = self.project_dir / LOCK_FILENAME
        self.timeout = timeout
        self._acquired = False

    def acquire(self) -> None:
        """Acquire the lock. Raises LockError if already held by another live process."""
        if self.lock_path.exists():
            info = self._read_lock()
            if info and self._is_stale(info):
                logger.warning(
                    "Removing stale lock (PID %s, created %s)",
                    info.get("pid"), info.get("created"),
                )
                self.lock_path.unlink(missing_ok=True)
            elif info:
                raise LockError(
                    f"Another consync process is running (PID {info.get('pid')}, "
                    f"started {info.get('created')}). "
                    f"If this is stale, delete {self.lock_path}"
                )

        # Write lock
        lock_info = {
            "pid": os.getpid(),
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "hostname": platform.node(),
        }
        self.lock_path.write_text(json.dumps(lock_info, indent=2))
        self._acquired = True
        logger.debug("Lock acquired: %s", self.lock_path)

    def release(self) -> None:
        """Release the lock."""
        if self._acquired and self.lock_path.exists():
            self.lock_path.unlink(missing_ok=True)
            self._acquired = False
            logger.debug("Lock released: %s", self.lock_path)

    def _read_lock(self) -> dict | None:
        """Read lock file contents."""
        try:
            return json.loads(self.lock_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def _is_stale(self, info: dict) -> bool:
        """Check if a lock is stale (process dead or too old)."""
        pid = info.get("pid")

        # Check if process is still alive
        if pid:
            try:
                os.kill(pid, 0)  # Signal 0 = check existence
            except ProcessLookupError:
                return True  # Process doesn't exist
            except PermissionError:
                pass  # Process exists but we can't signal it

        # Check age
        created = info.get("created", "")
        if created:
            try:
                lock_time = datetime.fromisoformat(created)
                age = (datetime.now(timezone.utc) - lock_time).total_seconds()
                if age > self.timeout:
                    return True
            except ValueError:
                pass

        return False

    def __enter__(self) -> "SyncLock":
        self.acquire()
        return self

    def __exit__(self, *_) -> None:
        self.release()
