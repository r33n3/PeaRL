"""Async CloudWatch Logs Insights client for AgentCore decision log queries.

Uses aioboto3 to run a Logs Insights query against the AgentCore decision log
group and return the raw results.  The caller is responsible for parsing.

Dry-run mode (empty ``log_group_arn``) returns an empty result list so the
worker pipeline can proceed without live AWS credentials.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_SERVICE = "logs"
_QUERY_POLL_INTERVAL = 2  # seconds between status checks


class CloudWatchClient:
    """Queries CloudWatch Logs Insights for AgentCore decision events.

    Parameters
    ----------
    log_group_arn:
        ARN of the CloudWatch log group that receives AgentCore decision logs.
        Empty string → dry-run (returns empty results immediately).
    aws_region:
        AWS region for the CloudWatch endpoint.
    aws_access_key_id / aws_secret_access_key:
        Optional explicit credentials.  Defaults to the boto3 credential chain.
    query_timeout:
        Maximum seconds to wait for a Logs Insights query to complete.
    """

    # Logs Insights query that extracts AgentCore policy evaluation events.
    # AgentCore emits one JSON log record per Cedar evaluation decision.
    _QUERY = (
        "fields @timestamp, gatewayIdentifier, principalId, action, "
        "resource, decision, policyHash, requestId "
        "| filter ispresent(decision) "
        "| sort @timestamp asc "
        "| limit 10000"
    )

    def __init__(
        self,
        log_group_arn: str,
        aws_region: str = "us-east-1",
        aws_access_key_id: str = "",
        aws_secret_access_key: str = "",
        query_timeout: int = 60,
    ) -> None:
        self.log_group_arn = log_group_arn
        self.aws_region = aws_region
        self._access_key = aws_access_key_id
        self._secret_key = aws_secret_access_key  # nosec B107
        self.query_timeout = query_timeout

    @property
    def _dry_run(self) -> bool:
        return not self.log_group_arn

    def _make_session(self):
        import aioboto3  # type: ignore[import]

        kwargs: dict = {"region_name": self.aws_region}
        if self._access_key and self._secret_key:
            kwargs["aws_access_key_id"] = self._access_key
            kwargs["aws_secret_access_key"] = self._secret_key  # nosec B106
        return aioboto3.Session(), kwargs

    async def query_decision_logs(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict]:
        """Run a Logs Insights query and return decision log entries.

        Each entry is a flat dict with keys matching the query fields:
        ``@timestamp``, ``gatewayIdentifier``, ``principalId``, ``action``,
        ``resource``, ``decision``, ``policyHash``, ``requestId``.

        Returns an empty list in dry-run mode.
        """
        if self._dry_run:
            logger.info(
                "CloudWatchClient: dry-run — returning empty log entries "
                "start=%s end=%s",
                start_time.isoformat(),
                end_time.isoformat(),
            )
            return []

        session, kwargs = self._make_session()
        async with session.client(_SERVICE, **kwargs) as client:
            start_epoch = int(start_time.timestamp())
            end_epoch = int(end_time.timestamp())

            resp = await client.start_query(
                logGroupName=self._log_group_name(),
                startTime=start_epoch,
                endTime=end_epoch,
                queryString=self._QUERY,
                limit=10000,
            )
            query_id: str = resp["queryId"]

            # Poll until complete or timeout
            elapsed = 0
            while elapsed < self.query_timeout:
                await asyncio.sleep(_QUERY_POLL_INTERVAL)
                elapsed += _QUERY_POLL_INTERVAL

                status_resp = await client.get_query_results(queryId=query_id)
                status: str = status_resp.get("status", "")

                if status == "Complete":
                    return self._parse_results(status_resp.get("results", []))

                if status in ("Failed", "Cancelled", "Timeout"):
                    logger.warning(
                        "CloudWatchClient: query %s ended with status=%s",
                        query_id,
                        status,
                    )
                    return []

            logger.warning(
                "CloudWatchClient: query %s timed out after %ds",
                query_id,
                self.query_timeout,
            )
            return []

    def _log_group_name(self) -> str:
        """Extract log group name from ARN (or return as-is if already a name)."""
        # ARN format: arn:aws:logs:<region>:<account>:log-group:<name>
        if self.log_group_arn.startswith("arn:"):
            parts = self.log_group_arn.split(":")
            if len(parts) >= 7:
                return ":".join(parts[6:])
        return self.log_group_arn

    @staticmethod
    def _parse_results(raw_results: list) -> list[dict]:
        """Convert Logs Insights result format to flat dicts."""
        entries = []
        for row in raw_results:
            entry: dict = {}
            for field in row:
                entry[field.get("field", "")] = field.get("value", "")
            if entry:
                entries.append(entry)
        return entries
