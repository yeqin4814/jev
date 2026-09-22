#!/usr/bin/env bash
# Smoke test for Jev decision engine skills (AgentJev-0.6B on DGX Blackwell).
# Supports both:
#   1. Cloudflare Tunnel: JEV_BASE_URL=https://api.clinivisa.com bash smoke_jev.sh
#   2. LAN Direct:        JEV_HOST=192.168.0.106 bash smoke_jev.sh
set -euo pipefail

BASE_URL="${JEV_BASE_URL:-}"
HOST="${JEV_HOST:-api.clinivisa.com}"

if [[ -n "$BASE_URL" ]]; then
  HEALTH_URL="${BASE_URL}/health"
  INFO_URL="${BASE_URL}/api/info"
  DECIDE_URL="${BASE_URL}/v1/decide"
  EVALUATE_URL="${BASE_URL}/api/evaluate"
  SYSTEMONE_URL="${BASE_URL}/v1/systemone"
  TARGET="$BASE_URL (Cloudflare Tunnel)"
elif [[ "$HOST" == *"clinivisa.com"* ]]; then
  HEALTH_URL="https://${HOST}/health"
  INFO_URL="https://${HOST}/api/info"
  DECIDE_URL="https://${HOST}/v1/decide"
  EVALUATE_URL="https://${HOST}/api/evaluate"
  SYSTEMONE_URL="https://${HOST}/v1/systemone"
  TARGET="https://$HOST (Cloudflare Tunnel)"
else
  HEALTH_URL="http://${HOST}:9010/health"
  INFO_URL="http://${HOST}:8149/api/info"
  DECIDE_URL="http://${HOST}:8765/v1/decide"
  EVALUATE_URL="http://${HOST}:8149/api/evaluate"
  SYSTEMONE_URL="http://${HOST}:9010/v1/systemone"
  TARGET="$HOST (LAN direct ports :8149, :8765, :9010)"
fi

PASS=0
FAIL=0

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
check() {
  local name="$1" expected="$2" actual="$3"
  if [[ "$actual" == *"$expected"* ]]; then
    green "✓ $name"
    PASS=$((PASS + 1))
  else
    red "✗ $name — expected '$expected', got: $actual"
    FAIL=$((FAIL + 1))
  fi
}

echo "━━━ Jev Skill Smoke Tests (AgentJev-0.6B) ━━━"
echo "Target: $TARGET"
echo

# 1. Health check
echo "── 1. Gateway & Engine Health Check ──"
H=$(curl -sf "$HEALTH_URL" 2>&1 || echo '{"error":"unreachable"}')
check "Health check returns 200" '"gateway":"ok"' "$H"
check "AgentJev engine is healthy" '"agent_jev":"ok"' "$H"

# 2. AgentJev Info
echo
echo "── 2. Native AgentJev Metadata (/api/info) ──"
I=$(curl -sf "$INFO_URL" 2>&1 || echo '{"error":"unreachable"}')
check "Info returns model" '"AgentJev-0.6B"' "$I"
check "Info supports choice" '"choice"' "$I"
check "Info supports boolean" '"boolean"' "$I"

# 3. Simple decide (/v1/decide)
echo
echo "── 3. OpenJev Decision API (/v1/decide) ──"
D=$(curl -sf "$DECIDE_URL" \
  -H 'content-type: application/json' \
  -d '{
    "state": "Customer says: my credit card was charged twice",
    "criterion": "Route to correct team",
    "options": [
      {"id": "billing", "description": "Payments, invoices, charges"},
      {"id": "tech_support", "description": "Product bugs and crashes"},
      {"id": "security", "description": "Account compromise"}
    ]
  }' 2>&1 || echo '{"error":"failed"}')
check "Decide returns choice" '"choice"' "$D"
check "Decide picks billing" '"billing"' "$D"
check "Decide has probabilities" '"probabilities"' "$D"
check "Decide backed by agent-jev-0.6b" '"agent-jev-0.6b"' "$D"

# 4. Native AgentJev evaluate (/api/evaluate)
echo
echo "── 4. Native AgentJev Typed Evaluation (/api/evaluate) ──"
E=$(curl -sf "$EVALUATE_URL" \
  -H 'content-type: application/json' \
  -d '{
    "state": "Production database latency jumped to 5000ms with CPU at 99%",
    "questions": [
      {
        "id": "q1",
        "type": "choice",
        "question": "Which triage priority?",
        "options": ["P0 Outage", "P1 Urgent", "P2 Routine"]
      }
    ]
  }' 2>&1 || echo '{"error":"failed"}')
check "Evaluate returns results" '"results"' "$E"
check "Evaluate picks P0 Outage" '"P0 Outage"' "$E"
check "Evaluate reports wall_ms" '"wall_ms"' "$E"

# 5. Legacy systemone shim
echo
echo "── 5. Legacy SystemOne Compatibility Shim (/v1/systemone) ──"
S=$(curl -sf "$SYSTEMONE_URL" \
  -H 'content-type: application/json' \
  -d '{
    "state": {"ticket": "Our production database is returning errors and the CEO demo is in 30 minutes"},
    "questions": {
      "team": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {"database": "DB ops and queries", "frontend": "UI issues", "network": "Connectivity"}
      }
    }
  }' 2>&1 || echo '{"error":"failed"}')
check "SystemOne returns answers" '"answers"' "$S"
check "SystemOne returns choice" '"choice"' "$S"
check "SystemOne marked as deprecated shim" '"deprecated":true' "$S"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && green "All tests passed!" || red "Some tests failed."
exit $FAIL
