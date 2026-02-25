"""Integrity hash computation for compiled artifacts."""

import hashlib
import json
from datetime import datetime, timezone

from pearl.models.common import Integrity


def compute_integrity(data: dict) -> Integrity:
    """Compute SHA-256 hash of canonical JSON representation."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    hash_value = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return Integrity(
        signed=False,
        hash=hash_value,
        hash_alg="sha256",
        compiled_at=datetime.now(timezone.utc),
    )
