# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.1.x   | Yes       |
| 1.0.x   | Critical fixes only |
| < 1.0   | No        |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Report vulnerabilities by opening a [GitHub Security Advisory](https://github.com/r33n3/PeaRL/security/advisories/new). This keeps the report private while we assess and patch.

Include:
- Description of the vulnerability and its potential impact
- Steps to reproduce or proof-of-concept
- Affected versions
- Any suggested mitigations

### What to expect

- **Acknowledgement** within 48 hours
- **Initial assessment** within 5 business days
- **Patch and disclosure** coordinated with you — we follow responsible disclosure

We will credit reporters in the release notes unless you prefer to remain anonymous.

## Security Design Notes

PeaRL is designed as a governance control plane — it sits between AI agents and production systems. The following properties are enforced by design:

- **No self-approval** — agents cannot approve their own governance requests (enforced at route level, not just policy)
- **No model calls in workers** — all gate evaluation is deterministic; no LLM calls in the governance path
- **Audit trail integrity** — client audit events are HMAC-signed; server-side events are append-only
- **Least-privilege MCP** — the `/mcp` endpoint requires a scoped service token (`mcp` scope), not general admin credentials
- **API key separation** — API keys are HMAC-hashed before storage; raw keys are never persisted

## Dependency Security

Dependencies are pinned with minimum secure versions in `pyproject.toml`. Dependabot monitors for CVEs. Critical CVEs are patched within 72 hours of a fix being available upstream.
