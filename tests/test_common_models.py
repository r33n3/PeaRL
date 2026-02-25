"""Test common Pydantic models and error responses."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from pearl.models.common import (
    ErrorDetail,
    ErrorResponse,
    Integrity,
    Reference,
    TraceabilityRef,
)
from pearl.models.enums import HashAlgorithm, ReferenceKind

SPEC_DIR = Path(__file__).resolve().parents[1] / "PeaRL_spec"


def test_error_response_matches_example():
    """ErrorResponse model should serialize to match the validation-error example."""
    example_path = SPEC_DIR / "examples" / "errors" / "validation-error.response.json"
    expected = json.loads(example_path.read_text(encoding="utf-8"))

    error_resp = ErrorResponse(
        schema_version="1.1",
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="Request body failed schema validation",
            details={
                "field": "environment",
                "expected": ["sandbox", "dev", "pilot", "preprod", "prod"],
            },
            trace_id="trc_err_001",
            timestamp=datetime(2026, 2, 21, 10, 30, 0, tzinfo=timezone.utc).replace(
                tzinfo=None
            ),
        ),
    )

    dumped = error_resp.model_dump(mode="json", exclude_none=True)
    assert dumped["schema_version"] == expected["schema_version"]
    assert dumped["error"]["code"] == expected["error"]["code"]
    assert dumped["error"]["message"] == expected["error"]["message"]
    assert dumped["error"]["details"] == expected["error"]["details"]
    assert dumped["error"]["trace_id"] == expected["error"]["trace_id"]


def test_error_response_rejects_unknown_fields():
    """ErrorResponse should reject unknown fields (extra='forbid')."""
    with pytest.raises(ValidationError):
        ErrorResponse(
            schema_version="1.1",
            error=ErrorDetail(
                code="TEST",
                message="test",
                trace_id="trc_test_001",
                timestamp=datetime.now(timezone.utc),
            ),
            unknown_field="should fail",
        )


def test_integrity_model():
    """Integrity model with required and optional fields."""
    integrity = Integrity(signed=True, hash="a" * 64, hash_alg=HashAlgorithm.SHA256)
    assert integrity.signed is True
    assert integrity.hash_alg == "sha256"

    # Minimal (only required)
    minimal = Integrity(signed=False)
    assert minimal.hash is None


def test_integrity_rejects_short_hash():
    """Integrity should reject hash shorter than 16 chars."""
    with pytest.raises(ValidationError):
        Integrity(signed=True, hash="short")


def test_traceability_ref():
    """TraceabilityRef model."""
    ref = TraceabilityRef(
        trace_id="trc_12345678",
        source_refs=["org_baseline_v1", "app_spec_v1"],
    )
    assert ref.trace_id == "trc_12345678"
    assert len(ref.source_refs) == 2


def test_traceability_ref_rejects_short_trace_id():
    """TraceabilityRef should reject trace_id shorter than 8 chars."""
    with pytest.raises(ValidationError):
        TraceabilityRef(trace_id="short")


def test_reference_model():
    """Reference model with required and optional fields."""
    ref = Reference(ref_id="test_ref", kind=ReferenceKind.ARTIFACT, summary="A test")
    assert ref.kind == "artifact"
    assert ref.uri is None
