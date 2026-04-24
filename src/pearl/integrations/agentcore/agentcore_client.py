"""Async client for AWS AgentCore control-plane API.

Wraps aioboto3 calls for Cedar policy deployment.  When ``gateway_arn`` is
empty (unconfigured or dry-run mode) every mutating method logs the intent
and returns a synthetic response so the worker pipeline proceeds without
requiring live AWS credentials.
"""
from __future__ import annotations

import json
import structlog

logger = structlog.get_logger(__name__)

_SERVICE = "bedrock-agentcore-control"


class AgentCoreClient:
    """Deploys Cedar policy bundles to an AWS AgentCore gateway.

    Requires ``aioboto3`` at runtime (optional dependency — not needed for
    dry-run or local dev).

    Parameters
    ----------
    gateway_arn:
        AgentCore gateway ARN.  Empty string → dry-run mode.
    aws_region:
        AWS region for the AgentCore control-plane endpoint.
    aws_access_key_id / aws_secret_access_key:
        Optional explicit credentials.  If omitted the default boto3 credential
        chain (environment variables, ~/.aws/credentials, instance role) is used.
    """

    def __init__(
        self,
        gateway_arn: str,
        aws_region: str = "us-east-1",
        aws_access_key_id: str = "",
        aws_secret_access_key: str = "",
    ) -> None:
        self.gateway_arn = gateway_arn
        self.aws_region = aws_region
        self._access_key = aws_access_key_id
        self._secret_key = aws_secret_access_key  # nosec B107

    @property
    def _dry_run(self) -> bool:
        return not self.gateway_arn

    def _make_session(self):
        """Return (aioboto3.Session, client_kwargs).  Deferred import."""
        import aioboto3  # type: ignore[import]

        client_kwargs: dict = {"region_name": self.aws_region}
        if self._access_key and self._secret_key:
            client_kwargs["aws_access_key_id"] = self._access_key
            client_kwargs["aws_secret_access_key"] = self._secret_key  # nosec B106
        return aioboto3.Session(), client_kwargs

    async def deploy_policy_bundle(self, bundle_json: dict) -> str:
        """Deploy a Cedar policy bundle to the AgentCore gateway.

        Calls ``PutGatewayPolicy`` on the bedrock-agentcore-control endpoint.
        Returns the AgentCore policy version / deployment ID, or a synthetic
        ``dryrun_<org_id>`` identifier in dry-run mode.

        Reference:
            https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/
        """
        if self._dry_run:
            org_id = bundle_json.get("metadata", {}).get("org_id", "unknown")
            synthetic_id = f"dryrun_{org_id}"
            logger.info(
                "AgentCoreClient: dry-run — skipping deploy gateway_arn='' synthetic_id=%s",
                synthetic_id,
            )
            return synthetic_id

        session, kwargs = self._make_session()
        async with session.client(_SERVICE, **kwargs) as client:
            response = await client.put_gateway_policy(
                gatewayIdentifier=self.gateway_arn,
                policyDocument=json.dumps(bundle_json),
            )

        deployment_id: str = (
            response.get("policyVersion")
            or response.get("deploymentId")
            or ""
        )
        logger.info(
            "AgentCoreClient: deployed gateway=%s deployment_id=%s",
            self.gateway_arn,
            deployment_id,
        )
        return deployment_id

    async def get_current_policy_hash(self) -> str | None:
        """Fetch the hash tag of the currently active Cedar bundle.

        Returns ``None`` in dry-run mode or if no policy is deployed.
        PeaRL tags each deployed bundle with ``pearl:bundle_hash`` via
        ``TagResource`` after a successful deployment.
        """
        if self._dry_run:
            return None

        session, kwargs = self._make_session()
        async with session.client(_SERVICE, **kwargs) as client:
            try:
                response = await client.get_gateway_policy(
                    gatewayIdentifier=self.gateway_arn,
                )
            except Exception as exc:
                logger.warning(
                    "AgentCoreClient: get_current_policy_hash failed gateway=%s: %s",
                    self.gateway_arn,
                    exc,
                )
                return None

        tags: dict = response.get("tags") or {}
        return tags.get("pearl:bundle_hash")
