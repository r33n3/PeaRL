"""HTTP client for MASS 2.0 API and IngestFinding mapper."""
from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_RAI_CATEGORIES = {"bias", "toxicity"}


class MassClient:
    """Async HTTP client for MASS 2.0 scan API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def create_scan(
        self,
        target_url: str,
        target_type: str,
        project_id: str,
    ) -> str:
        """Submit a new scan and return the scan_id."""
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self._base}/scans",
                json={
                    "target_url": target_url,
                    "target_type": target_type,
                    "pearl_project_id": project_id,
                },
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
