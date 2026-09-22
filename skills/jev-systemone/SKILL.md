---
name: jev-systemone
description: "Structured multi-question decisions powered by AgentJev-0.6B on Blackwell. Supports choice, boolean, and score typed evaluations with calibrated probabilities in 35-80ms. Use for multi-criteria triage, decision trees, scoring rubrics, or when you need more than a simple pick-one. Triggers: systemone, multi-question, boolean, score, decision tree, triage rubric, agentjev."
---

# Jev SystemOne — Structured Multi-Question Decisions

## Overview

The Jev Decision Lane on NVIDIA DGX Blackwell (`spark-15486`) is powered by **AgentJev-0.6B** (`aimeigaoshou/agent-jev`).
It replaces legacy autoregressive routing engines with an ultra-fast, permutation-equivariant transformer architecture.

Key advantages:
- **Ultra-low latency**: **35–80 ms** on Blackwell GB10 GPU (**~140 ms** globally via Cloudflare).
- **5.1× throughput**: Up to **12.70 QPS** concurrent.
- **Unified memory**: Only **2.45 GiB VRAM** footprint (freed 14.1 GiB from legacy Kev-9B).
- **Supported primitives**: `choice` (2–255 candidates), `boolean`, and `score` (0.0–1.0 float).

---

## Available Endpoints

1. **Native Typed Evaluation (Recommended)**:
   ```http
   POST https://api.clinivisa.com/api/evaluate
   Content-Type: application/json
   ```
2. **Metadata & Inspection**:
   ```http
   GET https://api.clinivisa.com/api/info
   ```
3. **Legacy SystemOne Shim (Deprecated)**:
   ```http
   POST https://api.clinivisa.com/v1/systemone
   Content-Type: application/json
   ```
   *Note: Transparently translated to AgentJev via gateway shim; returns `X-Model-Deprecation` header.*

---

## 1. Native AgentJev Evaluation API (`/api/evaluate`)

### Request Shape
```json
{
  "state": "<context text, JSON object, or list>",
  "questions": [
    {
      "id": "q1",
      "type": "choice",
      "question": "Which triage priority?",
      "options": ["P0 Outage", "P1 Urgent", "P2 Routine"]
    },
    {
      "id": "q2",
      "type": "boolean",
      "question": "Requires on-call paging?",
      "criteria": {
        "true": "Immediate page required",
        "false": "Can wait for business hours"
      }
    }
  ]
}
```

### Supported Question Types

#### `choice` — Pick 1 from N candidates (2 to 255 candidates)
```json
{
  "id": "priority",
  "type": "choice",
  "question": "What is the severity level?",
  "options": ["Low", "Medium", "High", "Critical"]
}
```
Returns winning candidate index, description, top probability, margin, and full probability distribution.

#### `boolean` — Calibrated True / False Verification
```json
{
  "id": "is_urgent",
  "type": "boolean",
  "question": "Is this situation life-threatening?",
  "criteria": {
    "true": "Immediate emergency intervention needed",
    "false": "Non-emergency"
  }
}
```
Returns calibrated probability for `true` vs `false`.

#### `score` — Continuous Scoring
```json
{
  "id": "satisfaction",
  "type": "score",
  "question": "Rate customer sentiment from negative (0.0) to positive (1.0)"
}
```
Returns continuous calibrated score in `[0.0, 1.0]`.

### Native Response Shape
```json
{
  "api_version": "agentjev.decision.v1",
  "model": "agent-jev",
  "results": [
    {
      "id": "0",
      "answers": [
        {
          "id": "q1",
          "type": "choice",
          "value": "0",
          "description": "P0 Outage",
          "top_probability": 0.9412,
          "margin": 0.8842,
          "distribution": {
            "0": 0.9412,
            "1": 0.0450,
            "2": 0.0138
          }
        }
      ]
    }
  ],
  "usage": {
    "wall_ms": 37.81
  }
}
```

---

## 2. Legacy `/v1/systemone` Compatibility Bridge

Existing code calling `POST /v1/systemone` continues to work transparently:

```json
{
  "state": "User reports payment failed with error code 4002",
  "questions": {
    "team": {
      "type": "choice",
      "instructions": "Which team owns this?",
      "criteria": {
        "billing": "Invoicing & payments",
        "infra": "Network & servers",
        "frontend": "UI bugs"
      }
    }
  }
}
```

**Response**:
```json
{
  "answers": {
    "team": {
      "choice": "billing",
      "confidence": 0.9621,
      "probabilities": {
        "billing": 0.9621,
        "infra": 0.0210,
        "frontend": 0.0169
      }
    }
  },
  "latency_ms": 147.95,
  "model": "agent-jev-0.6b (serving legacy kev-9b endpoint)",
  "deprecated": true
}
```

---

## 3. Python Client Integration

Use `scripts/jev.py`:

```python
import sys
sys.path.append("/Users/nan/.gemini/config/skills/jev-decide/scripts")
from jev import evaluate, decide

# 1. Native typed evaluation
res = evaluate(
    state="Server response times spiked from 20ms to 4500ms following deployment v2.4.1",
    questions=[
        {
            "id": "rollback",
            "type": "boolean",
            "question": "Should we immediately rollback deployment v2.4.1?",
            "criteria": {
                "true": "Rollback immediately to restore availability",
                "false": "Keep deployment and investigate in place"
            }
        },
        {
            "id": "severity",
            "type": "choice",
            "question": "What incident severity?",
            "options": ["SEV-1 (Critical)", "SEV-2 (Major)", "SEV-3 (Minor)"]
        }
    ]
)

for result in res["results"][0]["answers"]:
    print(result["id"], result.get("description") or result.get("value"))
```

## Migration Guidance
1. **For single-option routing**: Use `jev-decide` (`/v1/decide`).
2. **For multi-question evaluation**: Use `/api/evaluate` directly for highest speed and richest typing.
3. **Legacy Kev-9B**: Retired and masked on Blackwell. Legacy `/v1/systemone` requests are handled by the AgentJev shim.
