"""Local OS leases shared by engine checkpoints and managed run ownership."""
import os
from contextlib import contextmanager
from pathlib import Path

class RunBusyError(RuntimeError):
    pass

@contextmanager
def ownership(path: Path):
    """An OS-held lease releases on process death without stale PID heuristics."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.resolve() != path.absolute():
        raise ValueError("Lease path must not redirect outside its owned location.")
    stream = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RunBusyError("Run checkpoint is already in use by another active invocation.") from None
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RunBusyError("Run checkpoint is already in use by another active invocation.") from None
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()
