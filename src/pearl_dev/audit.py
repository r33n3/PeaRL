"""Append-only audit logger for pearl-dev enforcement decisions."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    """Appends JSON-lines to .pearl/audit.jsonl with file locking."""

    def __init__(self, audit_path: Path) -> None:
        self._path = audit_path

    @property
    def path(self) -> Path:
        return self._path

    def log(
        self,
        event_type: str,
        action: str,
        decision: str,
        *,
        reason: str = "",
        trace_id: str = "",
        tool_name: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Append a single audit entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "action": action,
            "decision": decision,
            "reason": reason,
            "trace_id": trace_id,
            "tool_name": tool_name,
            "details": details or {},
        }
        line = json.dumps(entry, separators=(",", ":")) + "\n"

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._append_locked(line)

    def query(
        self,
        *,
        since: datetime | None = None,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Read back audit entries, optionally filtered."""
        if not self._path.exists():
            return []

        results: list[dict[str, Any]] = []
        for raw_line in self._path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            entry = json.loads(raw_line)
            if event_type and entry.get("event_type") != event_type:
                continue
            if since:
                ts = datetime.fromisoformat(entry["timestamp"])
                if ts < since:
                    continue
            results.append(entry)
        return results

    def _append_locked(self, line: str) -> None:
        """Append with OS-level file locking for concurrent safety."""
        fd = os.open(str(self._path), os.O_WRONLY | os.O_CREAT | os.O_APPEND)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                try:
                    os.write(fd, line.encode("utf-8"))
                finally:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX)
                try:
                    os.write(fd, line.encode("utf-8"))
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
