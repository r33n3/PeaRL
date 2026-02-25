"""Configuration for pearl-dev."""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel, Field

if sys.version_info < (3, 11):
    import tomli as _tomllib
else:
    import tomllib as _tomllib


class PearlDevConfig(BaseModel):
    """pearl-dev configuration loaded from .pearl/pearl-dev.toml."""

    project_id: str = Field(..., min_length=1)
    environment: str = "dev"
    package_path: str = ".pearl/compiled-context-package.json"
    audit_path: str = ".pearl/audit.jsonl"
    approvals_dir: str = ".pearl/approvals"
    auto_task_context: bool = True
    api_url: str = "http://localhost:8080/api/v1"


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from *start* (default cwd) looking for a `.pearl/` directory.

    Returns the directory that contains `.pearl/`.
    Raises FileNotFoundError if none found.
    """
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / ".pearl").is_dir():
            return parent
    raise FileNotFoundError(
        f"No .pearl/ directory found from {current} up to filesystem root"
    )


def load_config(project_root: Path | None = None) -> PearlDevConfig:
    """Load pearl-dev.toml from the project root.

    If *project_root* is None, :func:`find_project_root` is called first.
    """
    root = project_root or find_project_root()
    config_path = root / ".pearl" / "pearl-dev.toml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "rb") as f:
        raw = _tomllib.load(f)

    section = raw.get("pearl-dev", {})
    return PearlDevConfig(**section)
