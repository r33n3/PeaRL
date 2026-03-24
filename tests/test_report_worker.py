"""Tests for report worker MinIO upload behavior."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# MinIO upload helper tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_minio_upload_returns_presigned_url():
    """_upload_report_artifact returns a presigned URL when MinIO call succeeds."""
    expected_url = "http://minio:9000/pearl-artifacts/reports/proj_test/security_summary/rpt_001.json?X-Amz-Signature=abc"

    mock_s3_client = AsyncMock()
    mock_s3_client.put_object = AsyncMock(return_value={})
    mock_s3_client.generate_presigned_url = AsyncMock(return_value=expected_url)
    mock_s3_client.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_s3_client.__aexit__ = AsyncMock(return_value=False)

    mock_aioboto3_session = MagicMock()
    mock_aioboto3_session.client = MagicMock(return_value=mock_s3_client)

    mock_aioboto3_mod = MagicMock()
    mock_aioboto3_mod.Session.return_value = mock_aioboto3_session

    with patch.dict("sys.modules", {"aioboto3": mock_aioboto3_mod}):
        # Re-import to ensure patched module is used
        from pearl.workers import report_worker
        url = await report_worker._upload_report_artifact(
            "rpt_001", "proj_test", "security_summary", {"data": "value"}
        )

    assert url == expected_url
    mock_s3_client.put_object.assert_called_once()
    call_kwargs = mock_s3_client.put_object.call_args[1]
    assert call_kwargs["Key"] == "reports/proj_test/security_summary/rpt_001.json"
    assert call_kwargs["ContentType"] == "application/json"


@pytest.mark.asyncio
async def test_minio_upload_sets_artifact_ref():
    """GenerateReportWorker.process includes artifact_url in result_refs when upload succeeds."""
    presigned_url = "http://minio:9000/pearl-artifacts/rpt_001.json?sig=abc"

    # Stub aioboto3 in sys.modules first so the worker module can be imported
    mock_aioboto3_mod = MagicMock()
    mock_aioboto3_mod.Session.return_value = MagicMock()

    with patch.dict("sys.modules", {"aioboto3": mock_aioboto3_mod}):
        import pearl.workers.report_worker as rw_mod

        # Now patch _upload_report_artifact at the module level to return the URL
        original_upload = rw_mod._upload_report_artifact
        rw_mod._upload_report_artifact = AsyncMock(return_value=presigned_url)
        try:
            mock_session = AsyncMock()
            mock_scalar_result = MagicMock()
            mock_scalar_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_scalar_result)
            mock_session.add = MagicMock()
            mock_session.flush = AsyncMock()

            worker = rw_mod.GenerateReportWorker()
            result = await worker.process(
                "job_001",
                {"project_id": "proj_test", "report_type": "security_summary"},
                mock_session,
            )
        finally:
            rw_mod._upload_report_artifact = original_upload

    assert len(result["result_refs"]) == 1
    ref = result["result_refs"][0]
    assert ref["artifact_url"] == presigned_url
    mock_session.add.assert_called_once()


@pytest.mark.asyncio
async def test_minio_upload_failure_does_not_raise():
    """_upload_report_artifact returns None gracefully on exception."""
    mock_s3_client = AsyncMock()
    # Simulate a generic error on put_object
    mock_s3_client.put_object = AsyncMock(
        side_effect=RuntimeError("NoSuchBucket")
    )
    mock_s3_client.__aenter__ = AsyncMock(return_value=mock_s3_client)
    mock_s3_client.__aexit__ = AsyncMock(return_value=False)

    mock_aioboto3_session = MagicMock()
    mock_aioboto3_session.client = MagicMock(return_value=mock_s3_client)

    mock_aioboto3_mod = MagicMock()
    mock_aioboto3_mod.Session.return_value = mock_aioboto3_session

    with patch.dict("sys.modules", {"aioboto3": mock_aioboto3_mod}):
        from pearl.workers import report_worker
        url = await report_worker._upload_report_artifact(
            "rpt_002", "proj_test", "security_summary", {"data": "value"}
        )

    assert url is None  # Must return None, not raise


@pytest.mark.asyncio
async def test_minio_upload_generic_exception_does_not_raise():
    """_upload_report_artifact returns None on any unexpected exception."""
    mock_aioboto3_mod = MagicMock()
    mock_aioboto3_mod.Session.side_effect = RuntimeError("unexpected error")

    with patch.dict("sys.modules", {"aioboto3": mock_aioboto3_mod}):
        from pearl.workers import report_worker
        url = await report_worker._upload_report_artifact(
            "rpt_003", "proj_test", "security_summary", {"data": "value"}
        )

    assert url is None


@pytest.mark.asyncio
async def test_worker_missing_project_id_raises():
    """GenerateReportWorker raises ValueError when project_id is missing."""
    # Use a stub aioboto3 module so the import succeeds in envs without it
    mock_aioboto3_mod = MagicMock()
    with patch.dict("sys.modules", {"aioboto3": mock_aioboto3_mod}):
        from pearl.workers import report_worker as rw_mod

        mock_session = AsyncMock()
        worker = rw_mod.GenerateReportWorker()

        with pytest.raises(ValueError, match="project_id"):
            await worker.process("job_001", {}, mock_session)
