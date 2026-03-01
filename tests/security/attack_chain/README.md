# PeaRL Attack Chain Eval Harness

Tests that verify the 7-level autonomous agent attack chain is blocked at each level.

**Reference:** `docs/security_research/pearl_autonomous_attack_research.md`

---

## Structure

| File | Level | Description | Requires Live Server? |
|---|---|---|---|
| `test_l1_mcp.py` | L1 | MCP tool abuse — exception creation spam, AGP-01 detection | No |
| `test_l2_schema.py` | L2 | OpenAPI schema discovery blocked in production mode | No |
| `test_l3_api.py` | L3 | Direct API exploitation — RequireReviewer gates | No |
| `test_l4_evidence.py` | L4 | Evidence poisoning — false_positive role gate | No |
| `test_l5_social.py` | L5 | Static analysis — no bypass documentation in source | No |
| `test_l6_config.py` | L6 | Config tampering — Bash guard blocks PEARL_LOCAL_REVIEWER writes | No |
| `test_l7_process.py` | L7 | Process/API control — Bash guard blocks governance curl | No |
| `results/` | — | Output directory for test runs (gitignored) | — |

All tests except L5–L7 use the in-memory SQLite database via the shared conftest
fixtures (no external services needed). L5–L7 are pure static analysis / subprocess
tests that do not require a running server at all.

---

## Running

```bash
# All attack chain tests
PEARL_LOCAL=1 pytest tests/security/attack_chain/ -v

# Single level
PEARL_LOCAL=1 pytest tests/security/attack_chain/test_l3_api.py -v

# Full security test suite
PEARL_LOCAL=1 pytest tests/security/ -v
```

---

## Note on L6 and L7

`test_l6_config.py` and `test_l7_process.py` test `scripts/pearl_bash_guard.py`
directly — they are unit tests of the hook script, not tests against the PeaRL API.
The shared `conftest.py` auth/project fixtures are not needed for these two files.

The bash guard intentionally does **not** block general system commands (`ps`, `kill`,
`docker compose restart`, `systemctl`). These are needed for legitimate autonomous
prototyping workflows. The guard only blocks PeaRL governance bypass patterns:
- Direct governance API calls via curl (`/approvals/*/decide`, `/exceptions/*/decide`)
- Shell writes of `PEARL_LOCAL_REVIEWER` to config files

OS-level controls (chmod 400 .env, server user separation) are documented in
`docs/security_research/SECURITY_HARDENING.md` as the complementary hard controls
for the process/config attack surface.

---

## Control Map

| Level | Attack | Hard Control | File |
|---|---|---|---|
| L1 | MCP exception spam | RequireReviewer on decide endpoints | `dependencies.py` |
| L2 | OpenAPI schema discovery | `openapi_url=None` in prod | `main.py` |
| L3 | Direct API call (no role) | RequireReviewer dependency | `dependencies.py` |
| L4 | Bulk false_positive marking | REVIEWER_ROLES check in route | `findings.py` |
| L5 | Social engineering via docs | Stripped bypass documentation | `dependencies.py` |
| L6 | Config tampering (.env write) | Bash guard + chmod 400 .env | `pearl_bash_guard.py` |
| L7 | Governance API bypass via curl | Bash guard pattern match | `pearl_bash_guard.py` |
