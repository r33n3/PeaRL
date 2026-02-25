"""Tests for ScanTarget Pydantic models."""

import pytest
from pydantic import ValidationError

from pearl.models.scan_target import (
    ScanTarget,
    ScanTargetCreate,
    ScanTargetDiscovery,
    ScanTargetUpdate,
)


class TestScanTarget:
    def test_valid_scan_target(self):
        st = ScanTarget(
            schema_version="1.1",
            scan_target_id="scnt_abc123",
            project_id="proj_test",
            repo_url="https://github.com/org/repo",
            branch="main",
            tool_type="mass",
            scan_frequency="daily",
            status="active",
        )
        assert st.scan_target_id == "scnt_abc123"
        assert st.tool_type.value == "mass"

    def test_invalid_scan_target_id_pattern(self):
        with pytest.raises(ValidationError):
            ScanTarget(
                schema_version="1.1",
                scan_target_id="bad_id",
                project_id="proj_test",
                repo_url="https://github.com/org/repo",
                tool_type="mass",
            )

    def test_invalid_project_id_pattern(self):
        with pytest.raises(ValidationError):
            ScanTarget(
                schema_version="1.1",
                scan_target_id="scnt_abc123",
                project_id="bad_project",
                repo_url="https://github.com/org/repo",
                tool_type="mass",
            )

    def test_invalid_tool_type(self):
        with pytest.raises(ValidationError):
            ScanTarget(
                schema_version="1.1",
                scan_target_id="scnt_abc123",
                project_id="proj_test",
                repo_url="https://github.com/org/repo",
                tool_type="unknown_tool",
            )

    def test_optional_fields_default_none(self):
        st = ScanTarget(
            schema_version="1.1",
            scan_target_id="scnt_abc123",
            project_id="proj_test",
            repo_url="https://github.com/org/repo",
            tool_type="mass",
        )
        assert st.environment_scope is None
        assert st.labels is None
        assert st.last_scanned_at is None
        assert st.last_scan_status is None


class TestScanTargetCreate:
    def test_valid_create(self):
        body = ScanTargetCreate(
            repo_url="https://github.com/org/repo",
            tool_type="mass",
        )
        assert body.branch == "main"
        assert body.scan_frequency.value == "daily"

    def test_missing_repo_url_fails(self):
        with pytest.raises(ValidationError):
            ScanTargetCreate(tool_type="mass")


class TestScanTargetDiscovery:
    def test_serializes_correctly(self):
        d = ScanTargetDiscovery(
            scan_target_id="scnt_abc",
            project_id="proj_test",
            repo_url="https://github.com/org/repo",
            branch="main",
            scan_frequency="daily",
        )
        data = d.model_dump()
        assert data["scan_target_id"] == "scnt_abc"
        assert data["environment_scope"] is None
        assert data["labels"] is None


class TestScanTargetUpdate:
    def test_partial_update(self):
        u = ScanTargetUpdate(branch="develop", scan_frequency="weekly")
        assert u.branch == "develop"
        assert u.status is None  # not provided
