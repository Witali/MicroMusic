"""Local immutable records, content bindings and process-scoped file leases."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import uuid


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                       allow_nan=False) + '\n').encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def publish_once(pending, path):
    # Windows rename is atomic and refuses an existing destination. POSIX
    # rename would overwrite it, so use an atomic exclusive hard link there.
    if os.name == 'nt':
        os.rename(pending, path)
    else:
        os.link(pending, path)


def immutable_bytes(path, data):
    """Publish a fully written record atomically, without replacing an existing one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.' + uuid.uuid4().hex + '.partial')
    with pending.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        try:
            publish_once(pending, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError('Immutable campaign record conflict')
    finally:
        pending.unlink(missing_ok=True)
    return digest(data)


def immutable(path, value):
    return immutable_bytes(path, encoded(value))


def current(path, value):
    """Mutable convenience pointer; immutable records remain authoritative."""
    path = Path(path)
    pending = path.with_name(path.name + '.' + uuid.uuid4().hex + '.partial')
    with pending.open('xb') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())
    pending.replace(path)


class Lease:
    """An OS lock is released on process exit; a leftover file is not ownership."""
    def __init__(self, path):
        self.path, self.stream = Path(path), None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open('a+b')
        stream.seek(0, 2)
        if not stream.tell():
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            stream.close()
            return False
        self.stream = stream
        return True

    def release(self):
        if self.stream is not None:
            if os.name == 'nt':
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close()
            self.stream = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError('Campaign lease is already held by another process')
        return self

    def __exit__(self, *_):
        self.release()


def available(path):
    lease = Lease(path)
    result = lease.acquire()
    lease.release()
    return result


def pid_alive(pid):
    if isinstance(pid, bool) or not isinstance(pid, int) or pid < 1:
        raise ValueError('Expected a positive process identity')
    if os.name == 'nt':
        import ctypes as ct
        kernel = ct.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ct.c_uint32, ct.c_int, ct.c_uint32]
        kernel.OpenProcess.restype = ct.c_void_p
        handle = kernel.OpenProcess(0x1000, 0, pid)
        if not handle:
            # Invalid PID means exited; denied query is conservatively alive.
            return ct.get_last_error() != 87
        try:
            code = ct.c_uint32()
            if not kernel.GetExitCodeProcess(ct.c_void_p(handle), ct.byref(code)):
                return True
            return code.value == 259
        finally:
            kernel.CloseHandle(ct.c_void_p(handle))
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
