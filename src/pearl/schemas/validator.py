"""Schema validation service using jsonschema library."""

from functools import lru_cache
from pathlib import Path

import jsonschema

from pearl.schemas.loader import load_json, make_ref_handlers
from pearl.schemas.registry import SCHEMA_REGISTRY


class SchemaValidator:
    """Validates JSON instances against PeaRL JSON Schemas."""

    def __init__(self, spec_dir: str | Path = "PeaRL_spec"):
        self.spec_dir = Path(spec_dir).resolve()
        self.schema_dir = self.spec_dir / "schemas"
        self.examples_dir = self.spec_dir / "examples"

    @lru_cache(maxsize=32)
    def _load_schema(self, schema_rel: str) -> dict:
        """Load and cache a schema by its relative path under schemas/."""
        return load_json(self.schema_dir / schema_rel)

    def validate(self, instance: dict, schema_name: str) -> None:
        """Validate an instance against a named schema.

        Args:
            instance: The JSON object to validate.
            schema_name: Logical name from SCHEMA_REGISTRY (e.g., "project").

        Raises:
            KeyError: If schema_name not in registry.
            jsonschema.ValidationError: If validation fails.
        """
        schema_rel = SCHEMA_REGISTRY[schema_name]
        self.validate_by_path(instance, schema_rel)

    def validate_by_path(self, instance: dict, schema_rel: str) -> None:
        """Validate an instance against a schema by relative path.

        Args:
            instance: The JSON object to validate.
            schema_rel: Relative path under schemas/ (e.g., "project/project.schema.json").

        Raises:
            jsonschema.ValidationError: If validation fails.
        """
        schema_path = self.schema_dir / schema_rel
        schema = self._load_schema(schema_rel)
        handlers = make_ref_handlers(schema_path.parent, self.schema_dir)
        resolver = jsonschema.RefResolver.from_schema(schema, handlers=handlers)
        jsonschema.validate(instance=instance, schema=schema, resolver=resolver)
