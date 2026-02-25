import json
from pathlib import Path
from urllib.parse import urlparse
try:
    import jsonschema
except ImportError:
    raise SystemExit("Install jsonschema: pip install jsonschema")

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
EX_DIR = ROOT / "examples"

def load_json(p):
    return json.loads(Path(p).read_text())

def make_handlers(schema_base: Path):
    def _https(uri: str):
        # Map https://pearl.local/schemas/... -> local schemas dir
        u = urlparse(uri)
        if u.netloc == "pearl.local" and u.path.startswith("/schemas/"):
            local_rel = u.path[len("/schemas/"):]
            return load_json(SCHEMA_DIR / local_rel)
        raise FileNotFoundError(f"Unsupported remote schema URI: {uri}")

    def _fileless(uri: str):
        # Relative refs like ../common/common-defs.schema.json or finding.schema.json
        return load_json((schema_base / uri).resolve())

    return {"https": _https, "http": _https, "": _fileless}

# Simple demo validations (expand in CI)
pairs = [
    ("project/create-project.request.json", "project/project.schema.json"),
    ("project/org-baseline.request.json", "project/org-baseline.schema.json"),
    ("project/app-spec.request.json", "project/application-spec.schema.json"),
    ("project/environment-profile.request.json", "project/environment-profile.schema.json"),
    ("compile/compiled-package.response.json", "context/compiled-context-package.schema.json"),
    ("task-packets/generate-task-packet.response.json", "context/task-packet.schema.json"),
    ("findings/findings-ingest.request.json", "findings/findings-ingest-request.schema.json"),
    ("remediation/generate-remediation-spec.response.json", "findings/remediation-spec.schema.json"),
    ("approvals/create-approval.request.json", "workflow/approval-request.schema.json"),
    ("approvals/decision.request.json", "workflow/approval-decision.schema.json"),
    ("exceptions/create-exception.request.json", "workflow/exception-record.schema.json"),
    ("reports/generate-report.request.json", "workflow/report-request.schema.json"),
    ("reports/generate-report.response.json", "workflow/report-response.schema.json"),
]

def validate(instance, schema_rel):
    schema_path = SCHEMA_DIR / schema_rel
    schema = load_json(schema_path)
    resolver = jsonschema.RefResolver.from_schema(schema, handlers=make_handlers(schema_path.parent))
    jsonschema.validate(instance=instance, schema=schema, resolver=resolver)

failed = 0
for ex_rel, schema_rel in pairs:
    try:
        validate(load_json(EX_DIR / ex_rel), schema_rel)
        print("OK ", ex_rel, "->", schema_rel)
    except Exception as e:
        failed += 1
        print("FAIL", ex_rel, "->", schema_rel, ":", e)

raise SystemExit(1 if failed else 0)
