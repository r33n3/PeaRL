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
# Add to .github/workflows/pearl-scan.yml
# Required: set PEARL_PROJECT_ID variable and PEARL_API_KEY secret in repo settings

name: PeaRL Gate Scan
on:
  push:
    branches: [dev, main]
  pull_request:

jobs:
  pearl-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Snyk SCA Scan → PeaRL
        uses: r33n3/pearl-actions/snyk@v1
        with:
          project_id: {project_id}
          pearl_api_url: ${{{{ vars.PEARL_API_URL }}}}
          pearl_api_key: ${{{{ secrets.PEARL_API_KEY }}}}
          snyk_token: ${{{{ secrets.SNYK_TOKEN }}}}

      - name: MASS AI Security Scan → PeaRL
        uses: r33n3/pearl-actions/mass@v1
        with:
          project_id: {project_id}
          pearl_api_url: ${{{{ vars.PEARL_API_URL }}}}
          pearl_api_key: ${{{{ secrets.PEARL_API_KEY }}}}
          anthropic_api_key: ${{{{ secrets.ANTHROPIC_API_KEY }}}}
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
            f"Add PEARL_PROJECT_ID = {project_id} as a repository variable",
            "Add PEARL_API_KEY as a repository secret",
            "Add PEARL_API_URL = http://your-pearl-instance/api/v1 as a repository variable",
            "Add SNYK_TOKEN as a repository secret (optional for public repos)",
            "Add ANTHROPIC_API_KEY as a repository secret (for AI projects)",
        ]

    return {
        "project_id": project_id,
        "platform": platform,
        "snippet": snippet,
        "instructions": instructions,
    }
