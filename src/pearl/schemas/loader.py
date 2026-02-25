"""JSON Schema file loader with $ref resolution for pearl.local URIs."""

import json
from pathlib import Path
from urllib.parse import urlparse


def load_json(path: Path) -> dict:
    """Load a JSON file and return parsed dict."""
    return json.loads(path.read_text(encoding="utf-8"))


def make_ref_handlers(schema_base: Path, schema_dir: Path):
    """Create URI handlers for resolving $ref in JSON Schemas.

    Handles:
    - https://pearl.local/schemas/... -> local schemas directory
    - Relative refs like ../common/common-defs.schema.json
    """

    def _remote_handler(uri: str):
        u = urlparse(uri)
        if u.netloc == "pearl.local" and u.path.startswith("/schemas/"):
            local_rel = u.path[len("/schemas/"):]
            return load_json(schema_dir / local_rel)
        raise FileNotFoundError(f"Unsupported remote schema URI: {uri}")

    def _file_handler(uri: str):
        return load_json((schema_base / uri).resolve())

    return {"https": _remote_handler, "http": _remote_handler, "": _file_handler}
