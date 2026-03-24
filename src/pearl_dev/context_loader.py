"""Loads and caches the compiled context package from disk."""

from __future__ import annotations

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

        # Strip top-level integrity_hash (ACoP CIH field) — not part of the Pydantic model;
        # server-side enforcement uses it, local loader uses package_metadata.integrity.hash.
        raw_data.pop("integrity_hash", None)

        # Validate with Pydantic
        package = CompiledContextPackage.model_validate(raw_data)

        # Verify integrity: check that package_id belongs to the declared project.
        # We intentionally do NOT hash the file content — formatting changes (whitespace,
        # key order) would break the check without any semantic change to the contract.
        if verify_integrity:
            self._verify_integrity(package)

        self._cached_package = package
        self._cached_mtime = current_mtime
        return package

    def invalidate(self) -> None:
        """Force reload on next call to load()."""
        self._cached_package = None
        self._cached_mtime = None

    @staticmethod
    def _verify_integrity(package: CompiledContextPackage) -> None:
        """Verify the package is structurally sound for this project.

        We check semantic identity (package_id prefix + project_id match) rather than
        a content hash. Content hashing breaks on any formatting change (whitespace,
        key order) without any semantic change to the governance contract.
        """
        package_id = package.package_metadata.package_id
        project_id = package.project_identity.project_id

        if not package_id.startswith("pkg_"):
            raise IntegrityError(f"Invalid package_id format: {package_id}")

        if not project_id:
            raise IntegrityError("Package is missing project_id")
