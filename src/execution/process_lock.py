"""Phase 9 process concurrency protection.

Single execution-owner lock using a persistent lock file in a Git-ignored
runtime directory. Prevents two bot copies from submitting duplicate orders.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LockResult:
    acquired: bool
    reason: str


class ProcessLock:
    """Persistent process-level execution lock."""

    def __init__(self, directory: str = ".execution_lock", lock_name: str = "execution.lock") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.directory / lock_name
        self._owner_pid = os.getpid()
        self._held = False

    def acquire(self, timeout_seconds: float = 5.0) -> LockResult:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                # O_CREAT | O_EXCL fails atomically if the file exists.
                fd = os.open(
                    str(self.lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                with os.fdopen(fd, "w") as fh:
                    fh.write(str(self._owner_pid))
                self._held = True
                return LockResult(acquired=True, reason="Lock acquired")
            except FileExistsError:
                # Check whether the lock holder is still alive.
                holder = self._read_holder()
                if holder is None or not self._is_pid_alive(holder):
                    self._stale_release()
                    continue
                time.sleep(0.1)
        return LockResult(acquired=False, reason="Execution lock held by another process")

    def release(self) -> None:
        if self._held and self.lock_path.exists():
            try:
                self.lock_path.unlink()
            except OSError:
                pass
        self._held = False

    def is_held(self) -> bool:
        return self._held

    def _read_holder(self) -> Optional[int]:
        try:
            with open(self.lock_path, "r") as fh:
                return int(fh.read().strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _stale_release(self) -> None:
        try:
            self.lock_path.unlink()
        except OSError:
            pass

    def __enter__(self) -> "ProcessLock":
        self.acquire()
        return self

    def __exit__(self, *args) -> None:
        self.release()


def current_pid() -> int:
    return os.getpid()
