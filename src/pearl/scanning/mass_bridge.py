"""HTTP client for MASS 2.0 API and IngestFinding mapper."""
from __future__ import annotations

import asyncio
import structlog

import httpx

logger = structlog.get_logger(__name__)

_RAI_CATEGORIES = {"bias", "toxicity"}


class MassClient:
    """Async HTTP client for MASS 2.0 scan API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = httpx.AsyncClient(timeout=30)

    async def create_scan(
        self,
        target_url: str,
        target_type: str,
        project_id: str,
    ) -> str:
        """Submit a new scan and return the scan_id."""
        # MASS 2.0 expects deployment_path, github_url, or api_url — not target_url
        body: dict = {"pearl_project_id": project_id}
        if target_url.startswith(("http://", "https://")):
            body["api_url"] = target_url
        else:
            body["deployment_path"] = target_url
        r = await self._client.post(
            f"{self._base}/scans",
            json=body,
            headers=self._headers,
        )
        r.raise_for_status()
        return r.json()["scan_id"]

    async def wait_for_completion(self, scan_id: str, timeout: int = 600) -> dict:
        """Poll until the scan finishes, returning the full report dict."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        async with httpx.AsyncClient(timeout=15) as client:
            while loop.time() < deadline:
                r = await client.get(
                    f"{self._base}/scans/{scan_id}",
                    headers=self._headers,
                )
                r.raise_for_status()
                data = r.json()
                if data.get("status") in ("complete", "failed", "error"):
                    return data
                await asyncio.sleep(15)
        raise TimeoutError(
            f"MASS scan {scan_id} did not complete within {timeout}s"
        )

    async def get_verdict(self, scan_id: str) -> dict:
        """GET /scans/{scan_id}/verdict — returns verdict dict or {} on error."""
        try:
            resp = await self._client.get(
                f"{self._base}/scans/{scan_id}/verdict",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("MASS verdict fetch failed scan_id=%s status=%s", scan_id, exc.response.status_code)
            return {}
        except Exception as exc:
            logger.warning("MASS verdict fetch error scan_id=%s: %s", scan_id, exc)
            return {}

    async def get_compliance(self, scan_id: str) -> dict:
        """GET /scans/{scan_id}/compliance — returns compliance dict or {} on error."""
        try:
            resp = await self._client.get(
                f"{self._base}/scans/{scan_id}/compliance",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("MASS compliance fetch failed scan_id=%s status=%s", scan_id, exc.response.status_code)
            return {}
        except Exception as exc:
            logger.warning("MASS compliance fetch error scan_id=%s: %s", scan_id, exc)
            return {}

    async def get_policies(self, scan_id: str) -> list[dict]:
        """GET /scans/{scan_id}/policies — returns list of {policy_type, content} or [] on error."""
        try:
            resp = await self._client.get(
                f"{self._base}/scans/{scan_id}/policies",
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
            # Accept list or dict keyed by policy_type
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [{"policy_type": k, "content": v} for k, v in data.items()]
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning("MASS policies fetch failed scan_id=%s status=%s", scan_id, exc.response.status_code)
            return []
        except Exception as exc:
            logger.warning("MASS policies fetch error scan_id=%s: %s", scan_id, exc)
            return []


def mass_finding_to_pearl(f: dict, project_id: str) -> dict:
    """Map a MASS 2.0 finding dict to PeaRL IngestFinding format."""
    compliance_refs = list(f.get("owasp_ids") or []) + list(f.get("mitre_ids") or [])
    category = f.get("category", "unknown")
    scan_id = f.get("scan_id", "")

    return {
        "external_id": f.get("finding_id") or f.get("id"),
        "title": f.get("title", ""),
        "description": f.get("description", ""),
        "category": "responsible_ai" if category in _RAI_CATEGORIES else "security",
        "severity": (f.get("severity") or "medium").upper(),
        "tool_name": f"mass_scan_{category}",
        "source": {
            "system": "mass_scan",
            "tool": "mass2",
            "trust_label": "trusted_external",
        },
        "project_id": project_id,
        "confidence": float(f.get("confidence") or 0.8),
        "cwe_ids": list(f.get("cwe_ids") or []),
        "compliance_refs": compliance_refs,
        "evidence": f.get("evidence") or {},
        "metadata": {
            "component": f.get("target_component"),
            "scan_id": scan_id,
        },
        "status": "closed" if f.get("false_positive") else "open",
    }
