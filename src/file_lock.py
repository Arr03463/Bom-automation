import os
import time
import uuid
from pathlib import Path

LOCK_SUFFIX = ".lock"
DEFAULT_LOCK_TIMEOUT_SECONDS = 10
LOCK_STALE_SECONDS = 30
LOCK_POLL_SECONDS = 0.05


class FileLock:
    """
    Minimal advisory lock built on atomic directory-entry creation
    (O_CREAT | O_EXCL), so concurrent AutoBOM processes serialize a
    read-modify-write cycle on a shared file instead of racing each other.
    Works the same way on Windows and POSIX with no extra dependency.

    Originally written for SupplierLookupCache; also used by
    FileTokenStore (token_store.py) to serialize DigiKey refresh-token
    rotation across processes sharing the same persistent directory --
    both are the same "shared file, concurrent writers" problem.

    acquire() returns True/False rather than proceeding either way -- a
    caller must never treat a timed-out acquire as if it held the lock.

    Each holder writes a random owner token into the lock file. release()
    and stale reclamation both re-check that token before deleting the
    lock file, so a process can never delete a lock that a *different*
    holder currently owns (e.g. a lock this instance considered stale and
    already lost to a successor that re-acquired it).
    """

    def __init__(self, target_path, timeout=None):
        self.lock_path = Path(str(target_path) + LOCK_SUFFIX)
        self.timeout = timeout if timeout is not None else DEFAULT_LOCK_TIMEOUT_SECONDS
        self._owner_token = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    @property
    def acquired(self):
        return self._owner_token is not None

    def acquire(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        owner_token = f"{os.getpid()}:{uuid.uuid4().hex}"

        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, owner_token.encode("utf-8"))
                finally:
                    os.close(fd)
                self._owner_token = owner_token
                return True
            except FileExistsError:
                self._reclaim_if_stale()
                if time.monotonic() >= deadline:
                    # Give up without ever claiming ownership. The caller
                    # must treat this as "no lock" and skip the operation
                    # that required exclusivity -- never proceed as if
                    # locked.
                    return False
                time.sleep(LOCK_POLL_SECONDS)

    def _reclaim_if_stale(self):
        try:
            age = time.time() - self.lock_path.stat().st_mtime
        except OSError:
            return

        if age < LOCK_STALE_SECONDS:
            return

        try:
            self.lock_path.unlink()
        except OSError:
            pass

    def _current_owner_token(self):
        try:
            return self.lock_path.read_text(encoding="utf-8")
        except OSError:
            return None

    def release(self):
        if self._owner_token is None:
            return

        # Only remove the lock file if it still holds the token we wrote.
        # If it holds a different token, this lock was reclaimed as stale
        # and re-acquired by another holder while we still thought we
        # owned it -- deleting it now would drop that holder's lock out
        # from under it.
        if self._current_owner_token() == self._owner_token:
            try:
                self.lock_path.unlink()
            except OSError:
                pass

        self._owner_token = None
