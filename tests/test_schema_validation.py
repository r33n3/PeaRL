"""Test schema validation for all 13 example-to-schema pairs."""

import json
from pathlib import Path

import pytest

from pearl.schemas.registry import EXAMPLE_SCHEMA_PAIRS
from pearl.schemas.validator import SchemaValidator

SPEC_DIR = Path(__file__).resolve().parents[1] / "PeaRL_spec"


@pytest.fixture
def validator():
    return SchemaValidator(spec_dir=SPEC_DIR)


@pytest.mark.parametrize(
    "example_rel,schema_rel",
    EXAMPLE_SCHEMA_PAIRS,
    ids=[pair[0].split("/")[-1] for pair in EXAMPLE_SCHEMA_PAIRS],
)
def test_example_validates_against_schema(validator, example_rel, schema_rel):
    """Each example payload should validate against its corresponding schema."""
    example_path = SPEC_DIR / "examples" / example_rel
    instance = json.loads(example_path.read_text(encoding="utf-8"))
    # Should not raise
    validator.validate_by_path(instance, schema_rel)
