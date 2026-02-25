"""Prefixed ID generation utility."""

import uuid


def generate_id(prefix: str) -> str:
    """Generate a prefixed unique ID.

    Args:
        prefix: The prefix (e.g., "proj_", "job_", "pkg_").

    Returns:
        A string like "proj_a1b2c3d4e5f6".
    """
    short_uuid = uuid.uuid4().hex[:16]
    return f"{prefix}{short_uuid}"
