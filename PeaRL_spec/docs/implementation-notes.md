# Implementation Notes for Autonomous Coding Platforms

## Recommended Stack (Reference, not required)
- API: FastAPI (Python) or Go/Node equivalent
- Validation: JSON Schema validator + typed models
- DB: Postgres
- Queue/Cache: Redis
- Object Store: S3/MinIO
- MCP Server: thin adapter over REST API

## Validation Strategy
- Validate request body against JSON Schema first
- Map to domain model
- Enforce authz scopes
- Execute domain logic
- Validate response payload against schema in integration tests

## Contract Tests
Use the files in `examples/` as:
- golden requests
- golden responses
- regression fixtures for compile/task packet/remediation flows

## Repo Integration
Generated project artifacts are expected under `.pearl/generated/`.
This strict pack defines API and entity shapes, not the generation templates themselves.
