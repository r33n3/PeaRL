#!/usr/bin/env bash
# SessionStart hook — auto-triggers MASS 2.0 scan in background when a
# .pearl.yaml is detected in the current working directory.
#
# Runs async (non-blocking). The scan result is pushed to PeaRL and
# findings feed gate evaluation (AI_SCAN_COMPLETED, AI_RISK_ACCEPTABLE, etc.)
#
# Requires: mass-scan CLI installed (cd MASS-2.0/sdk && pip install -e .)

set -euo pipefail

PEARL_YAML="${PWD}/.pearl.yaml"

# Not a PeaRL project — exit silently
if [ ! -f "$PEARL_YAML" ]; then
    exit 0
fi

# Not installed — exit silently
if ! command -v mass-scan &>/dev/null; then
    exit 0
fi

# Extract project_id from .pearl.yaml
PROJECT_ID=$(python3 -c "
import sys, re
try:
    content = open('${PEARL_YAML}').read()
    m = re.search(r'project_id:\s*(\S+)', content)
    print(m.group(1) if m else '')
except Exception:
    print('')
" 2>/dev/null)

if [ -z "$PROJECT_ID" ]; then
    exit 0
fi

PEARL_API_URL="${PEARL_API_URL:-http://localhost:8081/api/v1}"
PEARL_API_TOKEN="${PEARL_API_TOKEN:-}"
LOG_FILE="/tmp/mass-scan-${PROJECT_ID}.log"

# Capture git context if available
COMMIT_SHA=""
BRANCH=""
if command -v git &>/dev/null && git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
    COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "")
    BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
fi

EXTRA_ARGS=""
[ -n "$COMMIT_SHA" ] && EXTRA_ARGS="$EXTRA_ARGS --commit-sha $COMMIT_SHA"
[ -n "$BRANCH" ]     && EXTRA_ARGS="$EXTRA_ARGS --branch $BRANCH"
[ -n "$PEARL_API_TOKEN" ] && EXTRA_ARGS="$EXTRA_ARGS --pearl-api-token $PEARL_API_TOKEN"

# Launch scan in background — results pushed to PeaRL asynchronously
nohup mass-scan \
    --project-id "$PROJECT_ID" \
    --target-path "$PWD" \
    --pearl-api-url "$PEARL_API_URL" \
    --fail-on-risk-score 999 \
    $EXTRA_ARGS \
    > "$LOG_FILE" 2>&1 &

SCAN_PID=$!

# Tell Claude the scan started (shown as a system message)
cat <<JSON
{
  "systemMessage": "MASS 2.0 scan started for ${PROJECT_ID} (pid ${SCAN_PID}). Findings will flow to PeaRL as gates are checked.\nLog: ${LOG_FILE}"
}
JSON
