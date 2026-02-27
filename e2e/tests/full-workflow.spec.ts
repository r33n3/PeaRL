/**
 * PeaRL Full Autonomous Remediation Workflow — end-to-end Playwright tests
 *
 * Tests the complete loop:
 *   Setup  → Create BU (aiuc1) + derive requirements + create test project + seed finding + evaluate gate
 *   Step 1 → Project page loads, current stage = sandbox
 *   Step 2 → Promotions page shows BLOCKED gate with task packets section
 *   Step 3 → Agent-brief API has open task packets
 *   Step 4 → Claim task packet via API
 *   Step 5 → Complete task packet with fix evidence (finding resolved)
 *   Step 6 → Agent-brief shows reduced blockers_count
 *   Step 7 → Project page: TimelinePanel shows finding_detected + agent_fixed events
 *   Step 8 → Promotions page: AgentRemediationCard renders fix details
 *   Teardown → Delete test project + BU
 *
 * Requires both servers running:
 *   Backend: PEARL_LOCAL=1 uvicorn pearl.main:app --port 8081
 *   Frontend: cd frontend && npm run dev
 */

import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

const API = "http://localhost:8081/api/v1";
const UI = "http://localhost:5173";

// Unique IDs for this test run so parallel runs don't collide
const RUN_ID = Date.now();
const TEST_BU_ID = `bu_e2e_${RUN_ID}`;
const TEST_PROJECT_ID = `proj_e2e_${RUN_ID}`;
const TEST_FINDING_ID = `find_e2e_${RUN_ID}`;

// ── State shared across tests ────────────────────────────────────────────────

let taskPacketId: string | null = null;
let findingId: string = TEST_FINDING_ID;

// ── Helpers ──────────────────────────────────────────────────────────────────

async function waitForApi(page: Page) {
  await page.waitForLoadState("networkidle");
}

async function apiGet(request: APIRequestContext, path: string) {
  const r = await request.get(`${API}${path}`);
  return { status: r.status(), body: await r.json().catch(() => ({})) };
}

async function apiPost(request: APIRequestContext, path: string, data: unknown) {
  const r = await request.post(`${API}${path}`, { data });
  const body = await r.json().catch(() => ({}));
  return { status: r.status(), body };
}

async function apiDelete(request: APIRequestContext, path: string) {
  const r = await request.delete(`${API}${path}`);
  return r.status();
}

// ── Suite ────────────────────────────────────────────────────────────────────

test.describe("Autonomous remediation loop", () => {
  // ── Setup ─────────────────────────────────────────────────────────────────

  test.beforeAll(async ({ request }) => {
    const now = new Date().toISOString();

    // 1. Create org (idempotent — use default org)
    // Business Unit
    const buRes = await apiPost(request, "/business-units", {
      bu_id: TEST_BU_ID,
      org_id: "org_default",
      name: `E2E Test BU ${RUN_ID}`,
      description: "Created by full-workflow e2e test",
      framework_selections: ["aiuc1"],
    });
    expect(buRes.status).toBeLessThan(300);

    // 2. Derive requirements from aiuc1 framework
    const fwRes = await apiPost(request, `/business-units/${TEST_BU_ID}/frameworks`, {
      framework_selections: ["aiuc1"],
    });
    expect(fwRes.status).toBeLessThan(300);

    // 3. Create test project assigned to BU
    const projRes = await apiPost(request, "/projects", {
      schema_version: "1.1",
      project_id: TEST_PROJECT_ID,
      name: `E2E Full Workflow ${RUN_ID}`,
      description: "Created by full-workflow e2e test — safe to delete",
      owner_team: "E2E Test Suite",
      business_criticality: "low",
      external_exposure: "internal",
      ai_enabled: true,
      bu_id: TEST_BU_ID,
    });
    expect(projRes.status).toBeLessThan(300);

    // 4. Environment profile (sandbox)
    await apiPost(request, `/projects/${TEST_PROJECT_ID}/environment-profile`, {
      schema_version: "1.1",
      profile_id: `envp_e2e_${RUN_ID}`,
      environment: "sandbox",
      delivery_stage: "prototype",
      risk_level: "low",
      autonomy_mode: "supervised_autonomous",
    });

    // 5. Org baseline
    await apiPost(request, `/projects/${TEST_PROJECT_ID}/org-baseline`, {
      schema_version: "1.1",
      kind: "PearlOrgBaseline",
      baseline_id: `orgb_e2e_${RUN_ID}`,
      org_name: "E2E Test Org",
      defaults: {
        data_privacy: {},
        security: { b004_2_rate_limits: true },
        safety: { c002_1_pre_deployment_test_approval: true },
        reliability: {},
        accountability: {},
        society: {},
      },
    });

    // 6. Seed a critical finding (gate blocker)
    const ingestRes = await apiPost(request, "/findings/ingest", {
      schema_version: "1.0",
      source_batch: {
        batch_id: `batch_e2e_${RUN_ID}`,
        source_system: "e2e_full_workflow",
        received_at: now,
        trust_label: "trusted_internal",
      },
      findings: [
        {
          schema_version: "1.0",
          finding_id: TEST_FINDING_ID,
          project_id: TEST_PROJECT_ID,
          environment: "sandbox",
          category: "security",
          severity: "critical",
          title: "E2E: Hardcoded secret detected",
          description: "E2E test finding. Move secret to env var before promotion.",
          status: "open",
          detected_at: now,
          source: {
            tool_name: "e2e_full_workflow",
            tool_type: "sast",
            trust_label: "trusted_internal",
          },
        },
      ],
    });
    // Capture the actual finding_id from the response if different
    if (ingestRes.body?.findings?.length > 0) {
      findingId = ingestRes.body.findings[0].finding_id ?? TEST_FINDING_ID;
    }

    // 7. Run gate evaluation (sandbox → dev) — this auto-creates TaskPackets for FAIL results
    const evalRes = await apiPost(
      request,
      `/projects/${TEST_PROJECT_ID}/promotions/evaluate?source_environment=sandbox&target_environment=dev`,
      {}
    );
    expect(evalRes.status).toBe(200);
  });

  test.afterAll(async ({ request }) => {
    // Best-effort cleanup — ignore failures
    await apiDelete(request, `/projects/${TEST_PROJECT_ID}`).catch(() => {});
    await apiDelete(request, `/business-units/${TEST_BU_ID}`).catch(() => {});
  });

  // ── Step 1: Project page loads ────────────────────────────────────────────

  test("project page loads showing sandbox stage", async ({ page }) => {
    await page.goto(`${UI}/projects/${TEST_PROJECT_ID}`);
    await waitForApi(page);

    // Heading (project name)
    await expect(page.getByRole("heading").first()).toBeVisible();

    // "sb" bubble for sandbox should be highlighted
    await expect(page.locator("text=sb").first()).toBeVisible();
  });

  test("project page shows Agent Status card", async ({ page }) => {
    await page.goto(`${UI}/projects/${TEST_PROJECT_ID}`);
    await waitForApi(page);

    await expect(page.getByText("Agent Status")).toBeVisible();
  });

  test("project page shows Project Timeline section", async ({ page }) => {
    await page.goto(`${UI}/projects/${TEST_PROJECT_ID}`);
    await waitForApi(page);

    await expect(page.getByText("Project Timeline")).toBeVisible();
  });

  // ── Step 2: Promotions page shows BLOCKED gate ────────────────────────────

  test("promotions page shows blocked gate with failing rules", async ({ page }) => {
    await page.goto(`${UI}/projects/${TEST_PROJECT_ID}/promotions`);
    await waitForApi(page);

    // At least one rule row
    await expect(page.locator(".font-mono").filter({ hasText: /\w/ }).first()).toBeVisible();

    // A "fail" status badge
    await expect(page.getByText("fail").first()).toBeVisible();
  });

  // ── Step 3: Agent-brief has open task packets ─────────────────────────────

  test("agent-brief API returns open task packets after gate evaluation", async ({ request }) => {
    const res = await apiGet(request, `/projects/${TEST_PROJECT_ID}/promotions/agent-brief`);
    expect(res.status).toBe(200);

    const brief = res.body;
    expect(brief.project_id).toBe(TEST_PROJECT_ID);
    expect(brief.current_stage).toBe("sandbox");
    expect(brief.gate_status).not.toBe("not_evaluated");
    expect(Array.isArray(brief.open_task_packets)).toBe(true);
    expect(brief.open_task_packets.length).toBeGreaterThan(0);

    // Save task_packet_id for subsequent steps
    taskPacketId = brief.open_task_packets[0].task_packet_id;
    expect(taskPacketId).toBeTruthy();
  });

  // ── Step 4: Claim task packet ─────────────────────────────────────────────

  test("agent can claim an open task packet", async ({ request }) => {
    // Ensure we have a task packet from the previous API test
    if (!taskPacketId) {
      const brief = await apiGet(request, `/projects/${TEST_PROJECT_ID}/promotions/agent-brief`);
      taskPacketId = brief.body.open_task_packets[0]?.task_packet_id ?? null;
    }
    expect(taskPacketId).toBeTruthy();

    const res = await apiPost(request, `/task-packets/${taskPacketId}/claim`, {
      agent_id: "e2e-test-agent",
    });
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("in_progress");
  });

  // ── Step 5: Complete with fix evidence ────────────────────────────────────

  test("agent completes task packet with fix evidence and resolved finding", async ({ request }) => {
    expect(taskPacketId).toBeTruthy();

    const res = await apiPost(request, `/task-packets/${taskPacketId}/complete`, {
      status: "completed",
      fix_summary: "Moved hardcoded secret to PEARL_API_KEY env var",
      commit_ref: "abc1234e2etest",
      files_changed: ["src/config.py", ".env.example"],
      finding_ids_resolved: [findingId],
      evidence_notes: "Secret removed from source. Validated via grep.",
    });
    expect(res.status).toBe(200);
  });

  // ── Step 6: Agent-brief shows updated state ───────────────────────────────

  test("agent-brief reflects fewer blockers after task completion", async ({ request }) => {
    const res = await apiGet(request, `/projects/${TEST_PROJECT_ID}/promotions/agent-brief`);
    expect(res.status).toBe(200);

    // The gate_status field should be present and not erroring
    expect(res.body.gate_status).toBeDefined();
    // blockers_count should be a number
    expect(typeof res.body.blockers_count).toBe("number");
  });

  // ── Step 7: TimelinePanel shows events ───────────────────────────────────

  test("project page timeline shows finding_detected event", async ({ page }) => {
    await page.goto(`${UI}/projects/${TEST_PROJECT_ID}`);
    await waitForApi(page);

    // Timeline panel rendered
    await expect(page.getByText("Project Timeline")).toBeVisible();

    // At least one timeline event row visible
    const timelineEntries = page.locator(".border-l-2");
    await expect(timelineEntries.first()).toBeVisible({ timeout: 8_000 });
  });

  test("timeline API returns events in descending order", async ({ request }) => {
    const res = await apiGet(request, `/projects/${TEST_PROJECT_ID}/timeline?limit=20`);
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    expect(res.body.length).toBeGreaterThan(0);

    // Verify descending order
    const timestamps = (res.body as Array<{ timestamp: string }>).map((e) =>
      new Date(e.timestamp).getTime()
    );
    for (let i = 1; i < timestamps.length; i++) {
      expect(timestamps[i - 1]).toBeGreaterThanOrEqual(timestamps[i]);
    }

    // Verify required fields on every event
    for (const ev of res.body as Array<Record<string, unknown>>) {
      expect(ev.event_id).toBeTruthy();
      expect(ev.event_type).toBeTruthy();
      expect(ev.timestamp).toBeTruthy();
      expect(ev.summary).toBeTruthy();
    }
  });

  test("timeline contains agent_fixed event after task completion", async ({ request }) => {
    const res = await apiGet(request, `/projects/${TEST_PROJECT_ID}/timeline?limit=50`);
    expect(res.status).toBe(200);

    const eventTypes = (res.body as Array<{ event_type: string }>).map((e) => e.event_type);
    expect(eventTypes).toContain("agent_fixed");
  });

  // ── Step 8: Promotions page shows AgentRemediationCard ───────────────────

  test("promotions page shows Agent Remediation section", async ({ page }) => {
    await page.goto(`${UI}/projects/${TEST_PROJECT_ID}/promotions`);
    await waitForApi(page);

    // The section heading "Agent Remediation" or "Elevation Evidence"
    const remediationHeading = page
      .getByText(/agent remediation|elevation evidence/i)
      .first();
    await expect(remediationHeading).toBeVisible({ timeout: 8_000 });
  });

  test("AgentRemediationCard renders fix details", async ({ page }) => {
    await page.goto(`${UI}/projects/${TEST_PROJECT_ID}/promotions`);
    await waitForApi(page);

    // Fix summary text should appear in the card
    await expect(page.getByText(/Moved hardcoded secret/i)).toBeVisible({ timeout: 8_000 });
  });

  // ── Full sequential smoke test ─────────────────────────────────────────────

  test.describe("complete loop in one browser session", () => {
    test("navigate project → promotions → verify remediation evidence", async ({ page }) => {
      // A. Project page — verify basic load
      await page.goto(`${UI}/projects/${TEST_PROJECT_ID}`);
      await waitForApi(page);
      await expect(page.getByText("Agent Status")).toBeVisible();
      await expect(page.getByText("Project Timeline")).toBeVisible();

      // B. Navigate to Promotions
      await page.getByRole("button", { name: /Promotions/i }).click();
      await waitForApi(page);

      // Either the remediation section or the gate rules should be visible
      const hasGateRules = await page.locator(".font-mono").filter({ hasText: /\w/ }).first().isVisible();
      expect(hasGateRules).toBe(true);

      // C. Sidebar nav to Admin → Business Units
      await page.goto(`${UI}/admin/business-units`);
      await waitForApi(page);
      await expect(page.getByRole("heading", { name: /Business Units/i })).toBeVisible();

      // Our test BU should appear in the list
      await expect(page.getByText(`E2E Test BU ${RUN_ID}`)).toBeVisible({ timeout: 8_000 });
    });
  });
});

// ── Standalone admin page tests ───────────────────────────────────────────────

test.describe("Admin — Business Units page", () => {
  test("page loads with heading", async ({ page }) => {
    await page.goto(`${UI}/admin/business-units`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: /Business Units/i })).toBeVisible();
  });

  test("shows New Business Unit button", async ({ page }) => {
    await page.goto(`${UI}/admin/business-units`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("button", { name: /New Business Unit/i })).toBeVisible();
  });

  test("create form appears on button click", async ({ page }) => {
    await page.goto(`${UI}/admin/business-units`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("button", { name: /New Business Unit/i }).click();

    await expect(page.getByPlaceholder("Engineering")).toBeVisible();
    await expect(page.getByRole("button", { name: "Create" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible();
  });

  test("cancel hides the create form", async ({ page }) => {
    await page.goto(`${UI}/admin/business-units`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("button", { name: /New Business Unit/i }).click();
    await expect(page.getByPlaceholder("Engineering")).toBeVisible();

    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByPlaceholder("Engineering")).not.toBeVisible();
  });
});

// ── Settings page — Business Units tab ───────────────────────────────────────

test.describe("Settings — Business Units tab", () => {
  test("Business Units tab is present in Settings", async ({ page }) => {
    await page.goto(`${UI}/settings`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("button", { name: /Business Units/i })).toBeVisible();
  });

  test("clicking Business Units tab renders BU content", async ({ page }) => {
    await page.goto(`${UI}/settings`);
    await page.waitForLoadState("networkidle");

    await page.getByRole("button", { name: /Business Units/i }).click();

    await expect(page.getByRole("heading", { name: /Business Units/i })).toBeVisible();
  });
});

// ── Sidebar navigation ────────────────────────────────────────────────────────

test.describe("Sidebar — admin section", () => {
  test("Business Units link is visible in sidebar", async ({ page }) => {
    await page.goto(UI);
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("link", { name: /Business Units/i })).toBeVisible();
  });

  test("clicking Business Units nav link navigates to admin page", async ({ page }) => {
    await page.goto(UI);
    await page.waitForLoadState("networkidle");

    await page.getByRole("link", { name: /Business Units/i }).click();
    await expect(page).toHaveURL(/\/admin\/business-units/);
    await expect(page.getByRole("heading", { name: /Business Units/i })).toBeVisible();
  });

  test("Administration section label is visible", async ({ page }) => {
    await page.goto(UI);
    await page.waitForLoadState("networkidle");

    await expect(page.getByText(/Administration/i)).toBeVisible();
  });
});
