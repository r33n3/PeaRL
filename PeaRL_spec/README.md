# PeaRL v1.1 Strict Contracts Pack

This pack adds **deterministic machine contracts** for the PeaRL application design:

- **OpenAPI 3.1** contract for core APIs
- **JSON Schemas** (Draft 2020-12) for canonical entities
- **Example payloads** for common request/response flows
- **Validation notes** for autonomous coding pipelines

## Purpose

Use this pack with the markdown spec pack (v1) so an autonomous coding platform can implement PeaRL with tighter contracts and less ambiguity.

## Included Structure

- `openapi/pearl-api-v1.1.yaml`
- `schemas/` JSON Schema files
- `examples/` request/response payloads
- `docs/contract-conventions.md`
- `docs/implementation-notes.md`

## Suggested Agent Build Order

1. Implement schema validation layer using `schemas/`
2. Implement core entities and persistence models
3. Implement API routes from `openapi/pearl-api-v1.1.yaml`
4. Add request/response examples as API tests
5. Add compile and task packet generation logic
6. Add findings ingestion + remediation generation
7. Add approval/exception flows
8. Add MCP wrapper using the same request contracts

## Determinism Notes

- Prefer strict enum validation for risk/environment values
- Reject unknown fields on critical write endpoints (or quarantine on ingestion endpoints)
- Attach `trace_id` to all responses
- Support `Idempotency-Key` on ingestion and generation endpoints
- Version all compiled outputs and schemas

## Compatibility

- API base path: `/api/v1`
- OpenAPI version: `3.1.0`
- JSON Schema draft: `2020-12`

