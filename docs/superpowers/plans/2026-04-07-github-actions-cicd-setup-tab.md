# GitHub Actions CI/CD Setup Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Setup" tab to the project detail page that generates and displays a ready-to-use GitHub Actions workflow file with a two-job pattern (opt-in scan + always-on gate check).

**Architecture:** Update the existing `ci_snippet.py` backend route with a new two-job YAML template, add a `useCiSnippet` React Query hook, create a `SetupTab` component with checklist + copy-able YAML, and wire the tab into `ProjectPage.tsx`.

**Tech Stack:** FastAPI (Python), React + TypeScript, React Query (`@tanstack/react-query`), Tailwind CSS

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `src/pearl/api/routes/ci_snippet.py` | Replace GitHub Actions template with two-job pattern |
| Create | `tests/test_ci_snippet.py` | Backend route tests |
| Create | `frontend/src/api/ciSnippet.ts` | `useCiSnippet` React Query hook |
| Create | `frontend/src/components/pipeline/SetupTab.tsx` | Checklist + YAML viewer component |
| Modify | `frontend/src/pages/ProjectPage.tsx` | Add "setup" tab |

---

## Task 1: Update backend CI snippet template

**Files:**
- Modify: `src/pearl/api/routes/ci_snippet.py`

- [ ] **Step 1: Replace `_github_actions_snippet` with the two-job template**

Open `src/pearl/api/routes/ci_snippet.py` and replace the entire `_github_actions_snippet` function:

```python
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
          import json, urllib.request, os, sys
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
```

- [ ] **Step 2: Update the GitHub Actions instructions list**

In the same file, replace the `instructions` list in the `else` branch (around line 147):

```python
        instructions = [
            "Add PEARL_API_KEY as a GitHub repository secret",
            f"Add PEARL_API_URL as a GitHub repository variable (e.g. http://your-pearl-host/api/v1)",
            "Set PEARL_SCAN_ENABLED=true as a repository variable only if you want PeaRL to run Snyk scans — skip if your org already pushes findings via Snyk Enterprise, SonarQube, or MASS",
            "Add SNYK_TOKEN as a repository secret (required only if PEARL_SCAN_ENABLED=true)",
            f"Commit .github/workflows/pearl-gate.yml — project ID {project_id} is already embedded",
        ]
```

- [ ] **Step 3: Commit**

```bash
git add src/pearl/api/routes/ci_snippet.py
git commit -m "feat: update GitHub Actions snippet to two-job gate+scan pattern"
```

---

## Task 2: Backend tests for ci_snippet route

**Files:**
- Create: `tests/test_ci_snippet.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for GET /projects/{project_id}/ci-snippet."""

import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_ci_snippet_returns_github_actions_by_default(client, db_session):
    """Returns GitHub Actions snippet when no ADO integration configured."""
    from pearl.repositories.project_repo import ProjectRepository
    from pearl.services.id_generator import generate_id

    repo = ProjectRepository(db_session)
    project = await repo.create(
        project_id=generate_id("proj"),
        name="Test Project",
        description="",
        environment="dev",
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/projects/{project.project_id}/ci-snippet")
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform"] == "github_actions"
    assert data["project_id"] == project.project_id
    assert "snippet" in data
    assert "instructions" in data


@pytest.mark.asyncio
async def test_ci_snippet_contains_project_id(client, db_session):
    """The project_id is embedded in the workflow YAML."""
    from pearl.repositories.project_repo import ProjectRepository
    from pearl.services.id_generator import generate_id

    repo = ProjectRepository(db_session)
    project = await repo.create(
        project_id=generate_id("proj"),
        name="Test Project",
        description="",
        environment="dev",
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/projects/{project.project_id}/ci-snippet")
    data = resp.json()
    assert project.project_id in data["snippet"]


@pytest.mark.asyncio
async def test_ci_snippet_contains_two_jobs(client, db_session):
    """Snippet contains both 'scan' and 'gate' jobs."""
    from pearl.repositories.project_repo import ProjectRepository
    from pearl.services.id_generator import generate_id

    repo = ProjectRepository(db_session)
    project = await repo.create(
        project_id=generate_id("proj"),
        name="Test Project",
        description="",
        environment="dev",
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/projects/{project.project_id}/ci-snippet")
    snippet = resp.json()["snippet"]
    assert "jobs:" in snippet
    assert "scan:" in snippet
    assert "gate:" in snippet
    assert "PEARL_SCAN_ENABLED" in snippet
    assert "promotions/evaluate" in snippet


@pytest.mark.asyncio
async def test_ci_snippet_404_for_unknown_project(client):
    """Returns 404 when project does not exist."""
    resp = await client.get("/api/v1/projects/proj_doesnotexist/ci-snippet")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ci_snippet_instructions_count(client, db_session):
    """Instructions list has exactly 5 items."""
    from pearl.repositories.project_repo import ProjectRepository
    from pearl.services.id_generator import generate_id

    repo = ProjectRepository(db_session)
    project = await repo.create(
        project_id=generate_id("proj"),
        name="Test Project",
        description="",
        environment="dev",
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/projects/{project.project_id}/ci-snippet")
    assert len(resp.json()["instructions"]) == 5
```

- [ ] **Step 2: Run tests — expect failures before Task 1 is complete, then pass**

```bash
PEARL_LOCAL=1 pytest tests/test_ci_snippet.py -v
```

Expected after Task 1 is complete:
```
PASSED tests/test_ci_snippet.py::test_ci_snippet_returns_github_actions_by_default
PASSED tests/test_ci_snippet.py::test_ci_snippet_contains_project_id
PASSED tests/test_ci_snippet.py::test_ci_snippet_contains_two_jobs
PASSED tests/test_ci_snippet.py::test_ci_snippet_404_for_unknown_project
PASSED tests/test_ci_snippet.py::test_ci_snippet_instructions_count
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_ci_snippet.py
git commit -m "test: ci_snippet route — two-job template and project_id embedding"
```

---

## Task 3: Frontend API hook

**Files:**
- Create: `frontend/src/api/ciSnippet.ts`

- [ ] **Step 1: Create the hook file**

```typescript
// frontend/src/api/ciSnippet.ts
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

export interface CiSnippetResponse {
  project_id: string;
  platform: "github_actions" | "azure_devops";
  snippet: string;
  instructions: string[];
}

export function useCiSnippet(projectId: string | undefined) {
  return useQuery({
    queryKey: ["ci-snippet", projectId],
    queryFn: () =>
      apiFetch<CiSnippetResponse>(`/projects/${projectId}/ci-snippet`),
    enabled: !!projectId,
    staleTime: 5 * 60 * 1000, // snippet rarely changes — cache 5 min
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/ciSnippet.ts
git commit -m "feat: useCiSnippet React Query hook"
```

---

## Task 4: SetupTab component

**Files:**
- Create: `frontend/src/components/pipeline/SetupTab.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/pipeline/SetupTab.tsx
import { useState } from "react";
import { Copy, Check, Terminal, AlertCircle } from "lucide-react";
import { useCiSnippet } from "@/api/ciSnippet";
import { VaultCard } from "@/components/shared/VaultCard";

interface SetupTabProps {
  projectId: string | undefined;
}

export function SetupTab({ projectId }: SetupTabProps) {
  const { data, isLoading, isError } = useCiSnippet(projectId);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!data?.snippet) return;
    await navigator.clipboard.writeText(data.snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-bone-muted text-sm font-mono py-12 justify-center">
        <Terminal size={14} className="animate-pulse" /> Generating workflow...
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 text-dried-blood-bright text-sm font-mono py-12 justify-center">
        <AlertCircle size={14} /> Failed to load CI snippet
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-sm font-mono text-bone-bright uppercase tracking-widest mb-1">
          CI/CD Setup
        </h2>
        <p className="text-xs font-mono text-bone-muted">
          Add this workflow to your repository to connect PeaRL governance gates to your CI pipeline.
        </p>
      </div>

      {/* Checklist */}
      <VaultCard title="Setup Checklist" icon={<Check size={14} />}>
        <ol className="space-y-2">
          {data.instructions.map((instruction, i) => (
            <li key={i} className="flex items-start gap-3 text-xs font-mono text-bone-dim">
              <span className="shrink-0 w-5 h-5 rounded border border-white/20 flex items-center justify-center text-xs text-bone-muted">
                {i + 1}
              </span>
              <span className="leading-relaxed">{instruction}</span>
            </li>
          ))}
        </ol>
      </VaultCard>

      {/* Snippet */}
      <VaultCard
        title={data.platform === "github_actions" ? "GitHub Actions Workflow" : "Azure Pipelines"}
        icon={<Terminal size={14} />}
        action={
          <button
            onClick={handleCopy}
            className="flex items-center gap-1.5 text-xs font-mono px-3 py-1 rounded border border-white/20 text-bone-muted hover:text-bone-bright hover:border-white/40 transition-colors"
          >
            {copied ? (
              <><Check size={11} className="text-cold-teal" /> Copied</>
            ) : (
              <><Copy size={11} /> Copy</>
            )}
          </button>
        }
      >
        <div className="text-xs font-mono text-bone-dim mb-2">
          Save as{" "}
          <code className="text-cold-teal bg-white/5 px-1 rounded">
            {data.platform === "github_actions"
              ? ".github/workflows/pearl-gate.yml"
              : "azure-pipelines.yml"}
          </code>
        </div>
        <pre className="text-xs font-mono text-green-300/80 bg-black/30 rounded p-4 overflow-x-auto whitespace-pre leading-relaxed border border-white/5">
          {data.snippet}
        </pre>
      </VaultCard>
    </div>
  );
}
```

- [ ] **Step 2: Check VaultCard accepts an `action` prop — if not, adjust**

```bash
grep -n "action\|Action\|children\|interface VaultCard" /mnt/c/Users/bradj/Development/PeaRL/frontend/src/components/shared/VaultCard.tsx | head -20
```

If `VaultCard` doesn't have an `action` prop, replace the `action={...}` usage with a wrapper `div` containing the title and copy button side-by-side:

```tsx
<VaultCard title="">
  <div className="flex justify-between items-center mb-3">
    <span className="text-xs font-mono text-bone-muted uppercase tracking-widest">
      {data.platform === "github_actions" ? "GitHub Actions Workflow" : "Azure Pipelines"}
    </span>
    <button onClick={handleCopy} ...>...</button>
  </div>
  {/* rest of content */}
</VaultCard>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/pipeline/SetupTab.tsx frontend/src/api/ciSnippet.ts
git commit -m "feat: SetupTab component with checklist and copy-able YAML snippet"
```

---

## Task 5: Wire Setup tab into ProjectPage

**Files:**
- Modify: `frontend/src/pages/ProjectPage.tsx`

- [ ] **Step 1: Add import at top of file** (after line 13, with other pipeline component imports)

```tsx
import { SetupTab } from "@/components/pipeline/SetupTab";
```

- [ ] **Step 2: Update the `activeTab` type** (line 29)

```tsx
const [activeTab, setActiveTab] = useState<"overview" | "guardrails" | "setup">("overview");
```

- [ ] **Step 3: Add "setup" to the tab bar array** (line 207)

```tsx
{(["overview", "guardrails", "setup"] as const).map((tab) => (
```

- [ ] **Step 4: Add the Setup tab render block** — add after the guardrails block (after line 225):

```tsx
      {/* Setup tab */}
      {activeTab === "setup" && (
        <SetupTab projectId={projectId} />
      )}
```

- [ ] **Step 5: Verify frontend builds without TypeScript errors**

```bash
docker compose exec frontend sh -c "cd /app && npx tsc --noEmit 2>&1" | grep -E "SetupTab|setup|ciSnippet" || echo "No errors for new files"
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ProjectPage.tsx
git commit -m "feat: add Setup tab to project detail page"
```

---

## Task 6: Smoke test end-to-end

- [ ] **Step 1: Verify backend snippet endpoint**

```bash
curl -s -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk" \
  http://localhost:8080/api/v1/projects/proj_myapp001/ci-snippet | python3 -m json.tool
```

Expected: JSON with `platform: "github_actions"`, `snippet` containing `scan:` and `gate:` job keys, and `instructions` array with 5 items.

- [ ] **Step 2: Validate the YAML is well-formed**

```bash
curl -s -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk" \
  http://localhost:8080/api/v1/projects/proj_myapp001/ci-snippet \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['snippet'])" \
  | python3 -c "import sys; import yaml; yaml.safe_load(sys.stdin.read()); print('YAML valid')"
```

Expected: `YAML valid`

- [ ] **Step 3: Verify in the browser**

1. Open `http://localhost:5177`
2. Navigate to any project
3. Click the **setup** tab
4. Confirm checklist shows 5 numbered steps
5. Confirm YAML snippet is visible and scrollable
6. Click **Copy** — paste into a text editor and verify content

- [ ] **Step 4: Run full backend test suite**

```bash
PEARL_LOCAL=1 pytest tests/test_ci_snippet.py tests/test_project_api.py -v
```

Expected: all pass.

- [ ] **Step 5: Final commit if any cleanup needed**

```bash
git add -p  # stage only intentional changes
git commit -m "chore: ci-snippet smoke test fixes"
```
