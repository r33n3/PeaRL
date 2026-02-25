"""Loads and caches the compiled context package from disk."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pearl.models.compiled_context import CompiledContextPackage


class IntegrityError(Exception):
    """Raised when the package hash does not match."""


class ContextLoader:
    """Loads `.pearl/compiled-context-package.json`, validates via Pydantic, verifies integrity hash."""

    def __init__(self, package_path: Path) -> None:
        self._path = package_path
        self._cached_package: CompiledContextPackage | None = None
        self._cached_mtime: float | None = None

    @property
    def path(self) -> Path:
        return self._path

    def load(self, *, verify_integrity: bool = True) -> CompiledContextPackage:
        """Load and return the compiled context package.

        Uses file mtime caching — only re-parses when the file changes.
        """
        if not self._path.exists():
            raise FileNotFoundError(f"Package not found: {self._path}")

        current_mtime = self._path.stat().st_mtime
        if self._cached_package is not None and self._cached_mtime == current_mtime:
            return self._cached_package

        raw_text = self._path.read_text(encoding="utf-8")
        raw_data = json.loads(raw_text)

        # Validate with Pydantic
        package = CompiledContextPackage.model_validate(raw_data)

        # Verify integrity hash
        if verify_integrity:
            self._verify_hash(raw_data, package)

        self._cached_package = package
        self._cached_mtime = current_mtime
        return package

    def invalidate(self) -> None:
        """Force reload on next call to load()."""
        self._cached_package = None
        self._cached_mtime = None

    @staticmethod
    def _verify_hash(raw_data: dict, package: CompiledContextPackage) -> None:
        """Verify the integrity hash in the package metadata.

        The hash is computed over {"project_id": ..., "package_id": ...}
        matching the server-side compute_integrity() logic.
        """
        integrity = package.package_metadata.integrity
        if not integrity.hash:
            return  # No hash to verify

        project_id = package.project_identity.project_id
        package_id = package.package_metadata.package_id
        check_data = {"project_id": project_id, "package_id": package_id}
        canonical = json.dumps(check_data, sort_keys=True, separators=(",", ":"))
        computed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

        if computed != integrity.hash:
            raise IntegrityError(
                f"Hash mismatch: expected {integrity.hash}, computed {computed}"
            )
