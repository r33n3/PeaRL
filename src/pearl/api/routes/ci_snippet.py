"""CI snippet route — returns platform-appropriate CI YAML for a project."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.errors.exceptions import NotFoundError
from pearl.repositories.integration_repo import IntegrationEndpointRepository
from pearl.repositories.project_repo import ProjectRepository

router = APIRouter(tags=["CI Snippet"])


# ---------------------------------------------------------------------------
# YAML snippet templates
# ---------------------------------------------------------------------------

def _github_actions_snippet(project_id: str) -> str:
    return f"""\
# PeaRL governance gate
# Add to .github/workflows/pearl-gate.yml
#
# Required GitHub repository settings:
#   Secrets : PEARL_API_KEY, SNYK_TOKEN (if scan enabled)
#   Variables: PEARL_API_URL, PEARL_SCAN_ENABLED (set to 'true' to enable scanning)

name: PeaRL Gate

on:
  push:
    branches: [dev, main]
  pull_request:

env:
  PEARL_PROJECT_ID: {project_id}
  PEARL_API_URL: ${{{{ vars.PEARL_API_URL }}}}
  PEARL_API_KEY: ${{{{ secrets.PEARL_API_KEY }}}}

jobs:
  scan:
    name: Scan \u2192 PeaRL
    runs-on: ubuntu-latest
    if: vars.PEARL_SCAN_ENABLED == 'true'
    steps:
      - uses: actions/checkout@v4

      - name: Install Snyk
        run: npm install -g snyk

      - name: Run Snyk scan
        run: snyk test --json --all-projects > snyk_results.json || true
        env:
          SNYK_TOKEN: ${{{{ secrets.SNYK_TOKEN }}}}

      - name: Push findings to PeaRL
        run: |
          python3 - <<'EOF'
          import json, urllib.request, os, sys
          with open("snyk_results.json") as f:
              results = json.load(f)
          payload = json.dumps(results).encode()
          req = urllib.request.Request(
              f"{{os.environ['PEARL_API_URL']}}/projects/{{os.environ['PEARL_PROJECT_ID']}}/integrations/snyk/ingest",
              data=payload,
              headers={{
                  "X-API-Key": os.environ["PEARL_API_KEY"],
                  "Content-Type": "application/json",
              }},
              method="POST",
          )
          with urllib.request.urlopen(req, timeout=30) as resp:
              data = json.load(resp)
          print(f"PeaRL: {{data.get('findings_created', 0)}} findings ingested")
          EOF
        env:
          PEARL_API_URL: ${{{{ env.PEARL_API_URL }}}}
          PEARL_API_KEY: ${{{{ env.PEARL_API_KEY }}}}
          PEARL_PROJECT_ID: ${{{{ env.PEARL_PROJECT_ID }}}}

  gate:
    name: PeaRL Gate Check
    runs-on: ubuntu-latest
    needs: [scan]
    if: always()
    steps:
      - name: Evaluate promotion gate
        run: |
          python3 - <<'EOF'
          import json, urllib.request, urllib.error, os, sys
          payload = json.dumps({{
              "branch": os.environ["GITHUB_REF_NAME"],
              "commit_sha": os.environ["GITHUB_SHA"],
          }}).encode()
          req = urllib.request.Request(
              f"{{os.environ['PEARL_API_URL']}}/projects/{{os.environ['PEARL_PROJECT_ID']}}/promotions/evaluate",
              data=payload,
              headers={{
                  "X-API-Key": os.environ["PEARL_API_KEY"],
                  "Content-Type": "application/json",
              }},
              method="POST",
          )
          try:
              with urllib.request.urlopen(req, timeout=30) as resp:
                  result = json.load(resp)
          except urllib.request.HTTPError as e:
              print(f"::error::PeaRL gate request failed: {{e.code}} {{e.reason}}")
              sys.exit(1)
          except urllib.error.URLError as e:
              print(f"::error::PeaRL gate network error: {{e.reason}}")
              sys.exit(1)
          status = result.get("status", "unknown")
          blockers = result.get("blockers", [])
          print(f"PeaRL gate status: {{status}}")
          if blockers:
              print("Blockers:")
              for b in blockers:
                  print(f"  - {{b}}")
          if status != "passed":
              print(f"::error::PeaRL gate blocked \u2014 status={{status}}")
              sys.exit(1)
          print("Gate passed \u2713")
          EOF
        env:
          PEARL_API_URL: ${{{{ env.PEARL_API_URL }}}}
          PEARL_API_KEY: ${{{{ env.PEARL_API_KEY }}}}
          PEARL_PROJECT_ID: ${{{{ env.PEARL_PROJECT_ID }}}}
          GITHUB_REF_NAME: ${{{{ github.ref_name }}}}
          GITHUB_SHA: ${{{{ github.sha }}}}
"""


def _azure_devops_snippet(project_id: str) -> str:
    return f"""\
# Add to azure-pipelines.yml
# Required: set PEARL_PROJECT_ID, PEARL_API_URL variables and PEARL_API_KEY secret in pipeline settings

trigger:
  branches:
    include:
      - dev
      - main

pool:
  vmImage: ubuntu-latest

steps:
  - checkout: self

  - task: UsePythonVersion@0
    inputs:
      versionSpec: '3.11'

  - script: pip install requests
    displayName: Install PeaRL bridge deps

  - script: npm install -g snyk
    displayName: Install Snyk CLI

  - script: snyk test --json --all-projects > snyk_results.json || true
    displayName: Run Snyk scan
    env:
      SNYK_TOKEN: $(SNYK_TOKEN)

  - script: |
      python - <<'EOF'
      import json, requests, os, sys
      results = json.load(open("snyk_results.json"))
      resp = requests.post(
          f"{{os.environ['PEARL_API_URL']}}/api/v1/projects/{project_id}/integrations/snyk/ingest",
          json=results,
          headers={{"X-API-Key": os.environ["PEARL_API_KEY"]}},
          timeout=30,
      )
      resp.raise_for_status()
      data = resp.json()
      print(f"PeaRL: {{data.get('findings_created',0)}} findings created, {{data.get('critical',0)}} critical, {{data.get('high',0)}} high")
      if data.get("critical", 0) + data.get("high", 0) > 0:
          print("##vso[task.logissue type=error]Snyk found HIGH/CRITICAL vulnerabilities — gate blocked")
          sys.exit(1)
      EOF
    displayName: Push Snyk results to PeaRL
    env:
      PEARL_API_URL: $(PEARL_API_URL)
      PEARL_API_KEY: $(PEARL_API_KEY)
"""


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/projects/{project_id}/ci-snippet", status_code=200)
async def get_ci_snippet(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a platform-appropriate CI YAML snippet for the given project.

    Detects whether an Azure DevOps integration is configured at the org level.
    If so, returns an Azure Pipelines snippet; otherwise returns a GitHub Actions snippet.
    """
    # 1. Verify project exists
    project_repo = ProjectRepository(db)
    project = await project_repo.get(project_id)
    if not project:
        raise NotFoundError("Project", project_id)

    # 2. Detect CI/CD platform from org-level integrations
    integration_repo = IntegrationEndpointRepository(db)
    ado_row = await integration_repo.get_org_by_adapter_type("azure_devops")

    if ado_row is not None:
        platform = "azure_devops"
        snippet = _azure_devops_snippet(project_id)
        instructions = [
            f"Add PEARL_PROJECT_ID = {project_id} as a pipeline variable",
            "Add PEARL_API_KEY as a secret pipeline variable",
            "Add PEARL_API_URL = http://your-pearl-instance/api/v1 as a pipeline variable",
            "Add SNYK_TOKEN as a secret pipeline variable (optional for public repos)",
            "Commit azure-pipelines.yml to your repository root",
        ]
    else:
        platform = "github_actions"
        snippet = _github_actions_snippet(project_id)
        instructions = [
            "Add PEARL_API_KEY as a GitHub repository secret",
            f"Add PEARL_API_URL as a GitHub repository variable (e.g. http://your-pearl-host/api/v1)",
            "Set PEARL_SCAN_ENABLED=true as a repository variable only if you want PeaRL to run Snyk scans — skip if your org already pushes findings via Snyk Enterprise, SonarQube, or MASS",
            "Add SNYK_TOKEN as a repository secret (required only if PEARL_SCAN_ENABLED=true)",
            f"Commit .github/workflows/pearl-gate.yml — project ID {project_id} is already embedded",
        ]

    return {
        "project_id": project_id,
        "platform": platform,
        "snippet": snippet,
        "instructions": instructions,
    }
