# Contract Conventions (v1.1)

## API Versioning
- URI versioning: `/api/v1`
- Schema versioning inside payloads: `schema_version`
- Backward-compatible additions preferred
- Breaking changes require new endpoint or version

## IDs
Use stable IDs with prefixes where helpful:
- `proj_*`, `job_*`, `pkg_*`, `tp_*`, `find_*`, `rs_*`, `appr_*`, `exc_*`

## Traceability
All responses SHOULD include:
- `trace_id`
- `timestamp`
- `schema_version` (for structured responses)

## Idempotency
The following endpoints SHOULD support `Idempotency-Key`:
- findings ingest
- compile context
- task packet generation
- remediation spec generation
- approval request creation

## Unknown Fields
- Strict endpoints (`context`, `compile`, `approval`) SHOULD reject unknown fields (HTTP 400)
- Ingestion endpoints MAY quarantine records and return partial acceptance summary

## Time Format
RFC 3339 timestamps with timezone offsets preferred.

## Security Classification Handling
Do not include raw sensitive payloads in logs unless explicitly required.
Return references/IDs and redacted summaries where possible.
