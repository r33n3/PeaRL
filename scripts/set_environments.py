"""
Set EnvironmentProfile for each demo project so the pipeline dashboard
places them in the correct stage column.
"""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

API = "http://localhost:8080/api/v1"

# project_id → (environment, delivery_stage, risk_level, autonomy_mode)
PROJECTS = {
    "proj_fraudshield":  ("prod",    "prod",       "critical", "supervised_autonomous"),
    "proj_codepilot":    ("prod",    "prod",       "moderate", "assistive"),
    "proj_priceoracle":  ("preprod", "hardening",  "critical", "supervised_autonomous"),
    "proj_sentinel":     ("preprod", "hardening",  "critical", "supervised_autonomous"),
    "proj_mediassist":   ("preprod", "pilot",      "critical", "assistive"),
    "proj_nexusllm":     ("preprod", "hardening",  "high",     "supervised_autonomous"),
    "proj_dataops":      ("prod",    "prod",       "high",     "supervised_autonomous"),
    "proj_riskcopilot":  ("dev",     "prototype",  "high",     "assistive"),
}


def main():
    c = httpx.Client(base_url=API, timeout=30)

    for pid, (env, stage, risk, autonomy) in PROJECTS.items():
        profile = {
            "schema_version": "1.1",
            "profile_id": f"envp_{pid}",
            "environment": env,
            "delivery_stage": stage,
            "risk_level": risk,
            "autonomy_mode": autonomy,
        }
        r = c.post(f"/projects/{pid}/environment-profile", json=profile)
        status = "✓" if r.status_code in (200, 201, 202) else f"✗ {r.status_code}"
        print(f"  {status}  {pid:<22}  →  {env}")
        if r.status_code not in (200, 201, 202):
            print(f"       {r.text[:200]}")

    print("\nDone. Refresh http://localhost:5177 — projects should be in correct pipeline columns.")


if __name__ == "__main__":
    main()
