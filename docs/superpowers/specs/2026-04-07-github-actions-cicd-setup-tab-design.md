# GitHub Actions CI/CD Setup Tab

**Date:** 2026-04-07  
**Status:** Approved for implementation

---

## Summary

Add a "Setup" tab to the project detail page (`ProjectPage.tsx`) that gives developers a ready-to-use GitHub Actions workflow file for connecting their repo to PeaRL's governance gates. The workflow supports two operating modes: enterprise (gate check only) and self-serve (scan + gate check).

---

## Background

PeaRL's `GET /projects/{id}/ci-snippet` endpoint already exists and returns a GitHub Actions YAML template. It is currently unreachable from the frontend. The existing template references unpublished custom Actions (`r33n3/pearl-actions/*`) and uses a single-job pattern. This design replaces the template with a self-contained two-job pattern and surfaces it in a new Setup tab.

---

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Location | Project detail page — new "Setup" tab | Contextual to the project, no dropdown needed |
| Tab content | Checklist + YAML snippet + copy button | Guided but not verbose |
| Workflow pattern | Two-job: scan (opt-in) + gate check (always) | Supports both enterprise and self-serve setups |
| Snippet implementation | Self-contained curl/shell — no external Actions | Works immediately, zero publishing dependencies |

---

## Workflow Design

### Job 1 — Scan (opt-in)

Controlled by a GitHub repo variable `PEARL_SCAN_ENABLED=true`. When enabled, runs Snyk and pushes results to PeaRL's ingest endpoint. Enterprise teams with Snyk/SonarQube already pushing findings to PeaRL leave this disabled.

### Job 2 — Gate Check (always runs)

Calls `POST /projects/{project_id}/promotions/evaluate` with:
- `branch` — from `${{ github.ref_name }}`
- `commit_sha` — from `${{ github.sha }}`

Parses the response `status` field. Exits 1 and prints `blockers` if status is not `"passed"`. Uses `if: always()` so it runs even when Job 1 is skipped.

### Full YAML template (generated per project)

```yaml
# PeaRL governance gate
# Docs: https://github.com/R33N3/PeaRL
name: PeaRL Gate

on:
  push:
    branches: [dev, main]
  pull_request:

env:
  PEARL_PROJECT_ID: {project_id}
  PEARL_API_URL: ${{ vars.PEARL_API_URL }}
  PEARL_API_KEY: ${{ secrets.PEARL_API_KEY }}

jobs:
  scan:
    name: Scan → PeaRL
    runs-on: ubuntu-latest
    if: vars.PEARL_SCAN_ENABLED == 'true'
    steps:
      - uses: actions/checkout@v4

      - name: Install Snyk
        run: npm install -g snyk

      - name: Run Snyk scan
        run: snyk test --json --all-projects > snyk_results.json || true
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}

      - name: Push findings to PeaRL
        run: |
          python3 - <<'EOF'
          import json, urllib.request, os, sys
          with open("snyk_results.json") as f:
              results = json.load(f)
          req = urllib.request.Request(
              f"{os.environ['PEARL_API_URL']}/projects/{os.environ['PEARL_PROJECT_ID']}/integrations/snyk/ingest",
              data=json.dumps(results).encode(),
              headers={"X-API-Key": os.environ["PEARL_API_KEY"], "Content-Type": "application/json"},
              method="POST",
          )
          with urllib.request.urlopen(req, timeout=30) as resp:
              data = json.load(resp)
          print(f"PeaRL: {data.get('findings_created', 0)} findings ingested")
          EOF

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
          payload = json.dumps({
              "branch": os.environ["GITHUB_REF_NAME"],
              "commit_sha": os.environ["GITHUB_SHA"],
          }).encode()
          req = urllib.request.Request(
              f"{os.environ['PEARL_API_URL']}/projects/{os.environ['PEARL_PROJECT_ID']}/promotions/evaluate",
              data=payload,
              headers={"X-API-Key": os.environ["PEARL_API_KEY"], "Content-Type": "application/json"},
              method="POST",
          )
          with urllib.request.urlopen(req, timeout=30) as resp:
              result = json.load(resp)
          status = result.get("status", "unknown")
          blockers = result.get("blockers", [])
          print(f"PeaRL gate status: {status}")
          if blockers:
              print("Blockers:")
              for b in blockers:
                  print(f"  - {b}")
          if status != "passed":
              print(f"::error::PeaRL gate blocked — status={status}")
              sys.exit(1)
          print("Gate passed.")
          EOF
        env:
          PEARL_API_URL: ${{ env.PEARL_API_URL }}
          PEARL_API_KEY: ${{ env.PEARL_API_KEY }}
          PEARL_PROJECT_ID: ${{ env.PEARL_PROJECT_ID }}
          GITHUB_REF_NAME: ${{ github.ref_name }}
          GITHUB_SHA: ${{ github.sha }}
```

---

## Setup Tab Checklist

Rendered above the snippet in the UI:

1. Add `PEARL_API_KEY` as a **GitHub repository secret**
2. Add `PEARL_API_URL` as a **GitHub repository variable** (e.g. `http://your-pearl-host/api/v1`)
3. Set `PEARL_SCAN_ENABLED=true` as a repository variable **only if** you want PeaRL to run Snyk scans — skip this if your org already pushes findings via Snyk Enterprise, SonarQube, or MASS
4. Add `SNYK_TOKEN` as a repository secret (required if `PEARL_SCAN_ENABLED=true`)
5. Commit `.github/workflows/pearl-gate.yml` to your repository

---

## Frontend Changes

### `ProjectPage.tsx`
- Add `"setup"` to the `activeTab` union type
- Add "Setup" tab button to the tab bar
- Render `<SetupTab projectId={projectId} />` when active

### New component: `frontend/src/components/pipeline/SetupTab.tsx`
- Fetches `GET /api/v1/projects/{id}/ci-snippet` via a new `useCiSnippet(projectId)` hook
- Renders checklist (static, from the instructions array in the API response)
- Renders YAML in a `<pre>` block with a Copy button (uses `navigator.clipboard.writeText`)
- Loading and error states

### New API hook: `frontend/src/api/projects.ts` (or new `ciSnippet.ts`)
- `useCiSnippet(projectId: string)` — React Query `useQuery` wrapping `GET /projects/{id}/ci-snippet`
- Returns `{ platform, snippet, instructions }`

---

## Backend Changes

### `src/pearl/api/routes/ci_snippet.py`
- Replace `_github_actions_snippet()` with the two-job template above
- `project_id` is interpolated into `PEARL_PROJECT_ID` env var and the ingest/evaluate URLs
- Update `instructions` list to match the new 5-step checklist
- Detection logic (ADO vs GitHub Actions) remains unchanged

---

## No Schema / Migration Changes

No new DB tables, columns, or migrations required. The endpoint reads existing project and integration data only.

---

## Testing

- `GET /api/v1/projects/proj_myapp001/ci-snippet` returns valid YAML with `proj_myapp001` interpolated
- YAML is parseable (`python3 -c "import yaml; yaml.safe_load(open('out.yml'))"`)
- Copy button copies to clipboard
- Checklist renders all 5 items from the `instructions` array
- Tab appears on project detail page and switches correctly
