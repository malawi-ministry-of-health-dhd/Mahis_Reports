"""Atomic local persistence and last-known-good retention for DHIS2 data."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from .exceptions import DHIS2StorageError


def atomic_json(path: Path, value: Any) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception as exc:
        try: os.unlink(temporary)
        except OSError: pass
        raise DHIS2StorageError(f"Unable to atomically write {path.name}") from exc


def atomic_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    """Atomically publish records as Parquet in the destination directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".parquet", dir=path.parent)
    os.close(fd)
    try:
        frame = pd.DataFrame(rows)
        for column in ("value", "numerator", "denominator"):
            if column in frame.columns:
                frame[column] = frame[column].map(lambda value: float(value) if value is not None else None)
        frame.to_parquet(temporary, index=False, engine="pyarrow")
        os.replace(temporary, path)
    except Exception as exc:
        try: os.unlink(temporary)
        except OSError: pass
        raise DHIS2StorageError(f"Unable to atomically publish {path.name}") from exc


def store_raw_audit(directory: Path, sync_run_id: str, request_id: str, metadata: dict[str, Any], payload: dict[str, Any]) -> Path:
    """Store request metadata and response without authentication material."""
    response_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    audit = dict(metadata)
    audit["response_checksum_sha256"] = hashlib.sha256(response_bytes).hexdigest()
    audit["response"] = payload
    path = directory / sync_run_id / f"{request_id}.json"
    atomic_json(path, audit)
    return path


@contextmanager
def exclusive_sync_lock(status_dir: Path) -> Iterator[None]:
    """Prevent concurrent sync publication with an atomic create lock."""
    status_dir.mkdir(parents=True, exist_ok=True)
    lock = status_dir / ".sync_running"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(fd, str(os.getpid()).encode("ascii")); os.close(fd)
    except FileExistsError as exc:
        raise DHIS2StorageError("Another DHIS2 synchronization is already running") from exc
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)
