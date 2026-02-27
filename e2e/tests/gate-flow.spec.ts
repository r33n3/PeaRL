/**
 * PeaRL Gate UI Workflow — end-to-end Playwright tests
 *
 * Covers the full contest-and-approve flow for proj_feu:
 *   1. Dashboard loads, proj_feu is visible
 *   2. Promotions page shows blocked gate with failing rules
 *   3. Contest a failing rule → submit for review
 *   4. Approvals page shows the pending exception
 *   5. Approve the exception on the detail page
 *   6. Return to Promotions → rule is now "Under review" / exception active
 *
 * beforeAll seeds proj_feu via the API (idempotent) so this suite can run
 * on a clean server without manual pre-seeding.
 */

import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

const API = "http://localhost:8081/api/v1";
const PROJECT_ID = "proj_feu";
const BASE = "http://localhost:5173";

// ── Seed helpers ─────────────────────────────────────────────────────────────

async function seedProjFeu(request: APIRequestContext) {
  // 1. Project (idempotent)
  const existing = await request.get(`${API}/projects/${PROJECT_ID}`);
  if (existing.status() !== 200) {
    const r = await request.post(`${API}/projects`, {
      data: {
        schema_version: "1.1",
        project_id: PROJECT_ID,
        name: "PeaRL — Feature-Environment Underwriter",
        description: "Self-referential PeaRL project for gate enforcement demo.",
        owner_team: "PeaRL Core",
        business_criticality: "high",
        external_exposure: "internal",
        ai_enabled: true,
      },
    });
    expect(r.status()).toBeLessThan(300);
  }

  // 2. Org baseline
  await request.post(`${API}/projects/${PROJECT_ID}/org-baseline`, {
    data: {
      schema_version: "1.1",
      kind: "PearlOrgBaseline",
      baseline_id: "orgb_feu_baseline",
      org_name: "PeaRL Demo Org",
      defaults: {
        data_privacy: {},
        security: {
          b004_2_rate_limits: true,
          b007_1_user_access_controls: true,
        },
        safety: {
          c002_1_pre_deployment_test_approval: true,
          c003_1_harmful_output_filtering: true,
        },
        reliability: {
          d003_1_tool_authorization_validation: true,
          d003_3_tool_call_log: true,
        },
        accountability: {
          e004_1_change_approval_policy_records: true,
          e015_1_logging_implementation: true,
          e016_1_text_ai_disclosure: true,
        },
        society: {},
      },
    },
  });

  // 3. Environment profile
  await request.post(`${API}/projects/${PROJECT_ID}/environment-profile`, {
    data: {
      schema_version: "1.1",
      profile_id: "envp_feu_sandbox",
      environment: "sandbox",
      delivery_stage: "prototype",
      risk_level: "low",
      autonomy_mode: "supervised_autonomous",
    },
  });

  // 4. Critical finding (gate blocker)
  const now = new Date().toISOString();
  await request.post(`${API}/findings/ingest`, {
    data: {
      schema_version: "1.0",
      source_batch: {
        batch_id: `batch_gateflow_${Date.now()}`,
        source_system: "e2e_gate_flow",
        received_at: now,
        trust_label: "trusted_internal",
      },
      findings: [
        {
          schema_version: "1.0",
          finding_id: "find_gateflow_critical_001",
          project_id: PROJECT_ID,
          environment: "sandbox",
          category: "security",
          severity: "critical",
          title: "Hardcoded API key detected in source",
          description: "A hardcoded API key was found. Must be moved to env vars before promotion.",
          status: "open",
          detected_at: now,
          source: {
            tool_name: "e2e_gate_flow",
            tool_type: "sast",
            trust_label: "trusted_internal",
          },
        },
      ],
    },
  });

  // 5. Gate evaluation (sandbox → dev)
  const ev = await request.post(
    `${API}/projects/${PROJECT_ID}/promotions/evaluate?source_environment=sandbox&target_environment=dev`
  );
  expect(ev.status()).toBe(200);
}

// ── Suite setup ──────────────────────────────────────────────────────────────

test.describe("Gate contest → approve flow", () => {
  test.beforeAll(async ({ request }) => {
    await seedProjFeu(request);
  });

  // ── helpers ──────────────────────────────────────────────────────────────

  async function waitForApi(page: Page) {
    await page.waitForLoadState("networkidle");
  }

  // ── 1. Dashboard ────────────────────────────────────────────────────────

  test("dashboard loads and shows proj_feu", async ({ page }) => {
    await page.goto(BASE);
    await waitForApi(page);

    await expect(page.getByRole("heading").first()).toBeVisible();
    await expect(page.getByText(PROJECT_ID).first()).toBeVisible();
  });

  // ── 2. Promotions page — gate is blocked ────────────────────────────────

  test("promotions page shows gate rules for proj_feu", async ({ page }) => {
    await page.goto(`${BASE}/projects/${PROJECT_ID}/promotions`);
    await waitForApi(page);

    const ruleRows = page.locator(".font-mono").filter({ hasText: /\w+ \w+/ });
    await expect(ruleRows.first()).toBeVisible();
  });

  test("gate has at least one failing rule with a Contest button", async ({ page }) => {
    await page.goto(`${BASE}/projects/${PROJECT_ID}/promotions`);
    await waitForApi(page);

    const contestBtn = page.getByRole("button", { name: "Contest" }).first();
    await expect(contestBtn).toBeVisible();
  });

  // ── 3. Contest a failing rule ────────────────────────────────────────────

  test("contest modal opens, accepts input, and submits", async ({ page }) => {
    await page.goto(`${BASE}/projects/${PROJECT_ID}/promotions`);
    await waitForApi(page);

    const contestBtn = page.getByRole("button", { name: "Contest" }).first();
    await contestBtn.click();

    await expect(page.getByRole("heading", { name: "Contest Rule" })).toBeVisible();

    const riskAcceptanceRadio = page.getByRole("radio", { name: /risk acceptance/i });
    await riskAcceptanceRadio.click();
    await expect(riskAcceptanceRadio).toBeChecked();

    await page.getByPlaceholder(/explain why/i).fill(
      "Playwright e2e test: accepting risk for demo purposes. Not exploitable in sandbox."
    );

    const submitBtn = page.getByRole("button", { name: "Submit for Review" });
    await expect(submitBtn).toBeEnabled();
    await submitBtn.click();

    await expect(page.getByRole("heading", { name: "Contest Rule" })).not.toBeVisible({
      timeout: 8_000,
    });
  });

  // ── 4. Approvals page — pending exception appears ────────────────────────

  test("approvals page shows a pending exception after contest", async ({ page }) => {
    await page.goto(`${BASE}/approvals`);
    await waitForApi(page);

    const exceptionsTab = page.getByRole("button", { name: /exceptions/i });
    await exceptionsTab.click();

    const exceptionCard = page.locator(".stagger-item").first();
    await expect(exceptionCard).toBeVisible({ timeout: 8_000 });

    await expect(page.getByText(PROJECT_ID).first()).toBeVisible();
  });

  // ── 5. Approve the exception ─────────────────────────────────────────────

  test("analyst can approve the pending exception", async ({ page }) => {
    await page.goto(`${BASE}/approvals`);
    await waitForApi(page);

    await page.getByRole("button", { name: /exceptions/i }).click();

    const firstCard = page.locator(".stagger-item").first();
    await expect(firstCard).toBeVisible({ timeout: 8_000 });
    await firstCard.click();

    await expect(page).toHaveURL(/\/approvals\/appr_/);
    await waitForApi(page);

    const approveBtn = page.getByRole("button", { name: /approve/i });
    await expect(approveBtn).toBeVisible();
    await approveBtn.click();

    await expect(approveBtn).not.toBeVisible({ timeout: 8_000 });
  });

  // ── 6. Back on Promotions — exception active or under review ─────────────

  test("after approval, rule shows exception active or under review", async ({ page }) => {
    await page.goto(`${BASE}/projects/${PROJECT_ID}/promotions`);
    await waitForApi(page);

    const resolvedIndicator = page
      .locator(".font-mono")
      .filter({ hasText: /under review|exception active/i })
      .first();

    await expect(resolvedIndicator).toBeVisible({ timeout: 10_000 });
  });

  // ── 7. Full end-to-end smoke (sequential) ───────────────────────────────

  test.describe("full gate contest → approve → confirm flow", () => {
    test("complete workflow in one session", async ({ page }) => {
      // Step A: Navigate to Promotions
      await page.goto(`${BASE}/projects/${PROJECT_ID}/promotions`);
      await waitForApi(page);

      const progressText = page.locator(".font-mono").filter({ hasText: /\d+\/\d+/ }).first();
      await expect(progressText).toBeVisible();

      // Step B: Contest the first failing rule
      const contestBtn = page.getByRole("button", { name: "Contest" }).first();
      await expect(contestBtn).toBeVisible();
      await contestBtn.click();

      await expect(page.getByRole("heading", { name: "Contest Rule" })).toBeVisible();
      await page
        .getByPlaceholder(/explain why/i)
        .fill("Full flow e2e: risk accepted for this demo environment.");
      await page.getByRole("button", { name: "Submit for Review" }).click();
      await expect(page.getByRole("heading", { name: "Contest Rule" })).not.toBeVisible({
        timeout: 8_000,
      });

      // Step C: Go to Approvals → Exceptions tab → open detail
      await page.goto(`${BASE}/approvals`);
      await waitForApi(page);
      await page.getByRole("button", { name: /exceptions/i }).click();

      const card = page.locator(".stagger-item").first();
      await expect(card).toBeVisible({ timeout: 8_000 });
      await card.click();

      await expect(page).toHaveURL(/\/approvals\/appr_/);
      await waitForApi(page);

      // Step D: Approve
      const approveBtn = page.getByRole("button", { name: /approve/i });
      await expect(approveBtn).toBeVisible();
      await approveBtn.click();
      await expect(approveBtn).not.toBeVisible({ timeout: 8_000 });

      // Step E: Return to Promotions — contested rule resolved
      await page.goto(`${BASE}/projects/${PROJECT_ID}/promotions`);
      await waitForApi(page);

      const resolved = page
        .locator(".font-mono")
        .filter({ hasText: /under review|exception active/i })
        .first();
      await expect(resolved).toBeVisible({ timeout: 10_000 });
    });
  });
});
