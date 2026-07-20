"""Machine-readable synchronization status helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import atomic_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_status(status_dir: Path) -> dict[str, Any]:
    path = status_dir / "current.json"
    if not path.exists():
        return {"source": "Malawi HMIS DHIS2", "status": "never_run", "published": False}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"status": "unreadable", "published": False}
    except (OSError, json.JSONDecodeError):
        return {"source": "Malawi HMIS DHIS2", "status": "unreadable", "published": False}


def write_status(status_dir: Path, status: dict[str, Any]) -> None:
    atomic_json(status_dir / "current.json", status)
