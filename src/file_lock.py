import os
import time
import uuid
from pathlib import Path

LOCK_SUFFIX = ".lock"
DEFAULT_LOCK_TIMEOUT_SECONDS = 10
LOCK_STALE_SECONDS = 30
LOCK_POLL_SECONDS = 0.05


class LockAcquisitionError(RuntimeError):
    """
    Raised by FileLock.__enter__() when the lock could not be acquired
    within its timeout. `with FileLock(...):` is fail-closed by design --
    entering the block always means the lock is actually held, so
    protected code can never run believing it is exclusive when it isn't
    (see the Codex F1 finding: a caller using `with` must not be able to
    proceed after a failed/timed-out acquire).

    Callers that want to skip the protected operation on a timeout
    instead of raising (e.g. SupplierLookupCache.save(), which treats "no
    lock" as "skip this save, try again next time") should call
    acquire()/release() manually and check the boolean return value
    rather than using `with`.
    """


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

    def __init__(self, target_path, timeout=None, stale_after=None):
        self.lock_path = Path(str(target_path) + LOCK_SUFFIX)
        self.timeout = timeout if timeout is not None else DEFAULT_LOCK_TIMEOUT_SECONDS
        # How long an unreleased lock file must sit untouched before a
        # waiting acquirer treats it as abandoned (a holder that crashed
        # without releasing) rather than a slow-but-live operation. Must
        # stay comfortably longer than the slowest legitimate protected
        # operation using this lock instance, or a live holder's lock can
        # be reclaimed out from under it -- see DigiKeyClient's DigiKey
        # token-refresh lock, which uses a longer value than the
        # SupplierLookupCache default because its protected operation
        # includes a real HTTP round trip.
        self.stale_after = stale_after if stale_after is not None else LOCK_STALE_SECONDS
        self._owner_token = None

    def __enter__(self):
        if not self.acquire():
            raise LockAcquisitionError(
                f"Could not acquire lock within {self.timeout}s: {self.lock_path}"
            )
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

        if age < self.stale_after:
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
