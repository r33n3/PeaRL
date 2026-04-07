# Scanner Enrichment + Modular Guardrails Design

**Date:** 2026-04-07  
**Status:** Approved for implementation

---

## Summary

Extend PeaRL's existing MASS 2.0 integration to pull enrichment data (verdict, compliance, policies) after findings are ingested, store scanner-generated policies in a new modular table, surface them in the Guardrails tab with source attribution, extend the promotion gate to consume verdict risk level, and stamp auto-resolved findings with the confirming scanner. The same pattern applies to Snyk and SonarQube going forward.

---

## What Already Exists (do not rebuild)

| Component | Location |
|---|---|
| MASS findings ingest | `src/pearl/api/routes/scanning.py:471` |
| `mass2_marker` finding with `scan_id` + `risk_score` | `scanning.py:566` |
| Auto-resolve findings on re-scan | `scanning.py:556` |
| `AI_RISK_ACCEPTABLE` gate (reads `risk_score` from marker) | `gate_evaluator.py:968` |
| `COMPREHENSIVE_AI_SCAN` gate | `gate_evaluator.py:1526` |
| `GET /projects/{id}/recommended-guardrails` endpoint | `src/pearl/api/routes/guardrails.py:177` |
| GuardrailsTab component | `frontend/src/components/pipeline/GuardrailsTab.tsx` |
| Snyk and SonarQube ingest routes | `scanning.py` |

---

## What This Adds (6 targeted changes)

### 1. Enrichment pullback — BackgroundTask in MASS ingest

After `mass_ingest` stores findings and commits, it fires a FastAPI `BackgroundTask` with `(project_id, scan_id)`. The task calls three new `MassClient` methods:

```
GET /scans/{scan_id}/verdict     → stored in mass2_marker.full_data["verdict"]
GET /scans/{scan_id}/compliance  → stored in mass2_marker.full_data["compliance"]
GET /scans/{scan_id}/policies    → upserted into scanner_policy_store per policy_type
```

Also sets `mass2_marker.full_data["has_agent_trace"] = bool` from the markdown report availability.

Enrichment failures are logged as warnings — they do not fail the ingest response. Ingest remains fast; enrichment arrives within seconds.

### 2. New table — `scanner_policy_store`

One Alembic migration. Schema:

| Column | Type | Notes |
|---|---|---|
| `id` | `String(64) PK` | `sps_` prefix via `generate_id` |
| `project_id` | `String(128) FK → projects` | indexed |
| `source` | `String(50)` | `"mass"`, `"snyk"`, `"sonarqube"`, `"pearl"` |
| `scan_id` | `String(128)` | which scan produced this |
| `policy_type` | `String(50)` | `"cedar"`, `"bedrock"`, `"litellm"`, `"nginx"`, `"nemo"` |
| `content` | `JSON` | raw policy content from scanner |
| `updated_at` | `DateTime` | upserted per `(project_id, source, policy_type)` |

New `ScannerPolicyRepository` with `upsert(project_id, source, scan_id, policy_type, content)` and `list_by_project(project_id)`.

### 3. `recommended-guardrails` endpoint merges scanner policies

`GET /projects/{id}/recommended-guardrails` already returns PeaRL-generated entries. Extend it to also query `scanner_policy_store` for the project and append each row as a guardrail entry with `source` set to the scanner name. PeaRL-generated entries get `source: "pearl"`.

Response entry shape (extended):

```json
{
  "id": "mass-cedar-proj_benderbox",
  "name": "Cedar Policy — MASS 2.0",
  "source": "mass",
  "policy_type": "cedar",
  "content": { ... },
  "category": "access_control",
  "severity": "high"
}
```

### 4. GuardrailsTab source badge

Each guardrail card renders a small source badge based on the `source` field:
- `"pearl"` → no badge (existing behavior, unlabelled)
- `"mass"` → `MASS 2.0` badge
- `"snyk"` → `Snyk` badge  
- `"sonarqube"` → `SonarQube` badge

Badge uses existing `PlatformTag`-style styling already in GuardrailsTab.

### 5. `confirmed_by` stamp on auto-resolve

The existing auto-resolve loop in `mass_ingest` (line 556) flips `status = "resolved"`. Extend it to also write to `full_data`:

```python
f.full_data = {**(f.full_data or {}), "confirmed_by": "mass2", "confirmed_scan_id": body.scan_id}
```

Findings list and finding detail show: **"Resolved — confirmed by MASS 2.0"** using the `confirmed_by` field.

Same pattern applied to Snyk ingest auto-resolve (`confirmed_by: "snyk"`) and SonarQube (`confirmed_by: "sonarqube"`).

### 6. Gate reads `verdict.risk_level` from marker

`_eval_ai_risk_acceptable` in `gate_evaluator.py` currently reads `ctx.mass_risk_score`. Extend `GateContext` to also load `mass_verdict_risk_level` from `marker.full_data.get("verdict", {}).get("risk_level")`.

Gate logic addition: if `risk_level` is `"critical"` or `"high"`, block regardless of numeric `risk_score`. This means MASS's own qualitative verdict has gate authority, not just the numeric score.

---

## Modular Pattern for Future Scanners

Any new scanner integration follows this pattern:

1. Ingest endpoint stamps `confirmed_by: "{scanner}"` on auto-resolved findings
2. Enrichment BackgroundTask pulls policies → `scanner_policy_store` with `source="{scanner}"`
3. `recommended-guardrails` automatically includes their rows (no endpoint change needed)
4. GuardrailsTab automatically renders their source badge (no UI change needed once badge logic uses `source` field)

---

## Data Flow Summary

```
MASS scan completes
  → MASS pushes findings to POST /integrations/mass/ingest
      → findings stored immediately
      → auto-resolve findings absent from scan (confirmed_by="mass2")
      → BackgroundTask fires:
          → GET verdict    → mass2_marker.full_data.verdict
          → GET compliance → mass2_marker.full_data.compliance
          → GET policies   → scanner_policy_store (source="mass")
  → ingest returns fast

User opens Guardrails tab
  → GET /recommended-guardrails
      → PeaRL-generated entries (source="pearl")
      → scanner_policy_store entries (source="mass", "snyk", etc.)
  → GuardrailsTab renders with source badges

Promotion gate evaluated
  → AI_RISK_ACCEPTABLE: checks risk_score AND verdict.risk_level
  → blocks if risk_level is "critical" or "high"
```

---

## No New Pages or Tabs

Everything surfaces within existing UI: Guardrails tab (source badges), Findings list (`confirmed_by` label), Promotion gate (verdict-aware blocking). No new navigation required.

---

## Files to Change

| Action | File |
|---|---|
| Modify | `src/pearl/scanning/mass_bridge.py` — add `get_verdict()`, `get_compliance()`, `get_policies()` to `MassClient` |
| Modify | `src/pearl/api/routes/scanning.py` — add BackgroundTask to `mass_ingest`, add `confirmed_by` to resolve loop |
| Create | `src/pearl/db/models/scanner_policy.py` — `ScannerPolicyRow` model |
| Create | `src/pearl/db/migrations/versions/006_add_scanner_policy_store.py` — migration 005 is reserved for lifespan ALTER TABLE cleanup |
| Create | `src/pearl/repositories/scanner_policy_repo.py` — `ScannerPolicyRepository` |
| Modify | `src/pearl/api/routes/guardrails.py` — merge scanner policies into response |
| Modify | `src/pearl/services/promotion/gate_evaluator.py` — add `mass_verdict_risk_level` to context + gate check |
| Modify | `frontend/src/components/pipeline/GuardrailsTab.tsx` — source badge per entry |

---

## Testing

- `test_mass_enrichment.py` — BackgroundTask fires, MassClient methods called, marker updated, policies upserted
- `test_scanner_policy_store.py` — upsert, list by project, source filtering
- `test_recommended_guardrails.py` — scanner policies appear in response with correct `source` field
- `test_gate_evaluator.py` — `"high"` verdict blocks gate; `"low"` passes; missing verdict falls back to `risk_score`
- `test_confirmed_by.py` — auto-resolve stamps `confirmed_by` + `confirmed_scan_id`
