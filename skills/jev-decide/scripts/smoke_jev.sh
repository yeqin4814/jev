#!/usr/bin/env bash
# Smoke test for Jev decision engine skills.
# Supports both:
#   1. Cloudflare Tunnel: JEV_BASE_URL=https://api.clinivisa.com bash smoke_jev.sh
#   2. LAN Direct:        JEV_HOST=192.168.0.106 bash smoke_jev.sh
set -euo pipefail

BASE_URL="${JEV_BASE_URL:-}"
HOST="${JEV_HOST:-192.168.0.106}"

if [[ -n "$BASE_URL" ]]; then
  HEALTH_URL="${BASE_URL}/health"
  DECIDE_URL="${BASE_URL}/v1/decide"
  SYSTEMONE_URL="${BASE_URL}/v1/systemone"
  TARGET="$BASE_URL (Cloudflare Tunnel)"
elif [[ "$HOST" == *"clinivisa.com"* ]]; then
  HEALTH_URL="https://${HOST}/health"
  DECIDE_URL="https://${HOST}/v1/decide"
  SYSTEMONE_URL="https://${HOST}/v1/systemone"
  TARGET="https://$HOST (Cloudflare Tunnel)"
else
  HEALTH_URL="http://${HOST}:8765/health"
  DECIDE_URL="http://${HOST}:8765/v1/decide"
  SYSTEMONE_URL="http://${HOST}:8011/v1/systemone"
  TARGET="$HOST (LAN ports :8765 and :8011)"
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

echo "━━━ Jev Skill Smoke Tests ━━━"
echo "Target: $TARGET"
echo

# 1. Health check
echo "── Health Check ──"
H=$(curl -sf "$HEALTH_URL" 2>&1 || echo '{"error":"unreachable"}')
check "Health check" '"' "$H"

# 2. Simple decide
echo
echo "── jev-decide: simple choice ──"
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

# 3. SystemOne: multi-question
echo
echo "── jev-systemone: multi-question ──"
S=$(curl -sf "$SYSTEMONE_URL" \
  -H 'content-type: application/json' \
  -d '{
    "state": {"ticket": "Our production database is returning errors and the CEO demo is in 30 minutes"},
    "questions": {
      "urgent": {
        "type": "noul",
        "instructions": "Does this need immediate attention?"
      },
      "team": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {"database": "DB ops and queries", "frontend": "UI issues", "network": "Connectivity"}
      },
      "severity": {
        "type": "score",
        "instructions": "How severe is the impact?",
        "criteria": ["low", "medium", "high", "critical"]
      }
    }
  }' 2>&1 || echo '{"error":"failed"}')
check "SystemOne returns answers" '"answers"' "$S"
check "SystemOne has noul" '"noul"' "$S"
check "SystemOne has choice" '"choice"' "$S"
check "SystemOne has score" '"score"' "$S"

# 4. SystemOne with dependencies
echo
echo "── jev-systemone: dependencies ──"
DEP=$(curl -sf "$SYSTEMONE_URL" \
  -H 'content-type: application/json' \
  -d '{
    "state": "User reports a minor typo on the settings page",
    "questions": {
      "is_bug": {
        "type": "noul",
        "instructions": "Is this a bug report?"
      },
      "priority": {
        "type": "score",
        "instructions": "What priority should this bug get?",
        "criteria": ["p3_low", "p2_medium", "p1_high", "p0_critical"],
        "ask_if": {"is_bug": ["yes"]}
      }
    }
  }' 2>&1 || echo '{"error":"failed"}')
check "Dependencies return answers" '"answers"' "$DEP"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && green "All tests passed!" || red "Some tests failed."
exit $FAIL
