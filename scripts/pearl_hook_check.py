#!/usr/bin/env python3
"""
Claude Code UserPromptSubmit hook — PeaRL project auto-registration.

Fires on every prompt submission. Checks for .pearl.yaml in CWD:
- If project is already registered → silent (no output, no tokens)
- If project is unregistered AND .pearl.yaml has all required fields → auto-registers silently
- If project is unregistered AND fields are missing → tells Claude to ask the user
- If API is unreachable or any error → silent (never blocks the prompt)
"""
import sys
from pathlib import Path

REQUIRED_FIELDS = ["name", "owner_team", "business_criticality", "external_exposure", "ai_enabled"]


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--cwd", default=None)
    args, _ = parser.parse_known_args()

    root = Path(args.cwd).resolve() if args.cwd else Path.cwd()
    pearl_yaml = root / ".pearl.yaml"
    if not pearl_yaml.exists():
        sys.exit(0)

    try:
        import yaml
        config = yaml.safe_load(pearl_yaml.read_text())
    except Exception:
        sys.exit(0)

    project_id = config.get("project_id")
    api_url = config.get("api_url", "http://localhost:8081/api/v1").rstrip("/")
    if not project_id:
        sys.exit(0)

    try:
        import httpx
        r = httpx.get(f"{api_url}/projects/{project_id}", timeout=2)
        if r.status_code == 200:
            sys.exit(0)  # Already registered — silent
        if r.status_code != 404:
            sys.exit(0)  # Unexpected status — don't block
    except Exception:
        sys.exit(0)  # API unreachable — silent

    # Project not registered. Try auto-registration if all fields are present.
    missing = [f for f in REQUIRED_FIELDS if f not in config]
    if not missing:
        payload = {
            "schema_version": "1.1",
            "project_id": project_id,
            "name": config["name"],
            "owner_team": config["owner_team"],
            "business_criticality": config["business_criticality"],
            "external_exposure": config["external_exposure"],
            "ai_enabled": config["ai_enabled"],
        }
        if config.get("description"):
            payload["description"] = config["description"]
        if config.get("bu_id"):
            payload["bu_id"] = config["bu_id"]

        try:
            import httpx
            r = httpx.post(f"{api_url}/projects", json=payload, timeout=5)
            if r.status_code in (201, 409):
                print(f"✓ PeaRL: project '{project_id}' registered. Dashboard: http://localhost:5173/projects/{project_id}")
            else:
                print(f"⚠️  PeaRL: auto-registration failed ({r.status_code}). Run manually or check API.")
        except Exception as exc:
            print(f"⚠️  PeaRL: auto-registration failed ({exc}). Is PeaRL running at {api_url}?")
    else:
        # Fields missing — ask Claude to collect them interactively
        print(
            f"⚠️  PeaRL: project '{project_id}' not registered. "
            f".pearl.yaml is missing: {', '.join(missing)}.\n"
            f"Please ask the user for these values and call pearl_register_project, "
            f"then write the values back into .pearl.yaml so future sessions are silent."
        )

    sys.exit(0)  # Always exit 0 — never block the prompt


if __name__ == "__main__":
    main()
