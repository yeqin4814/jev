---
name: jev-decide
description: "Route decisions through the AgentJev reflex decision engine on Blackwell. Use when you need to pick one option from a list or evaluate typed questions (choice, boolean, score) based on context — tool selection, ticket routing, intent classification, triage. Returns calibrated probabilities in 35-80ms. Triggers: decide, route, classify, pick, triage, which option, which tool."
---

# Jev Decide — Fast Decision Routing (AgentJev-0.6B)

## Overview

Jev Decide sends a context + options payload to the **AgentJev-0.6B** decision engine
running on NVIDIA DGX Blackwell (`spark-15486`). It returns a single choice with calibrated
probabilities and confidence scores — without slow autoregressive token generation.

Key specs:
- **Engine Latency**: **35–80 ms** on Blackwell GB10 GPU.
- **Edge Latency**: **120–160 ms** globally via Cloudflare Tunnel (`api.clinivisa.com`).
- **Throughput**: Up to **12.70 QPS** concurrent on a single instance.
- **Candidates**: Supports 2 to 255 candidates per question (shared-prefix cached).
- **Primitives**: `choice`, `boolean`, and `score`.

Use this skill whenever you need to **pick one thing from a list**:
- Which tool to call
- Which team owns a ticket
- Which workflow branch to take
- Intent classification
- Clinical triage / severity routing

## Endpoints

- **Public (Cloudflare Tunnel)**:
  ```http
  POST https://api.clinivisa.com/v1/decide
  Content-Type: application/json
  ```
- **Native Typed Evaluation (Public)**:
  ```http
  POST https://api.clinivisa.com/api/evaluate
  Content-Type: application/json
  ```
- **Native Engine Metadata (Public)**:
  ```http
  GET https://api.clinivisa.com/api/info
  ```
- **LAN Direct (spark-15486)**:
  ```http
  POST http://192.168.0.106:8765/v1/decide      # OpenJev decider adapter
  POST http://192.168.0.106:8149/api/evaluate   # Native AgentJev engine
  GET  http://192.168.0.106:8149/api/info       # Native capabilities
  ```

No API key required.

---

## 1. Standard Decision API (`/v1/decide`)

### Request Shape
```json
{
  "state": "<string, object, or array — the context to decide on>",
  "criterion": "<what you are deciding>",
  "options": [
    {"id": "option_a", "description": "What option A means"},
    {"id": "option_b", "description": "What option B means"},
    {"id": "option_c", "description": "What option C means"}
  ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `state` | string or object | Yes | The situation, ticket, user message, or clinical data. |
| `criterion` | string | Yes | A short sentence describing what you are deciding. |
| `options` | array of `{id, description}` | Yes | 1–255 options. `id` is the machine-readable label, `description` explains what it means. Single options map to boolean verification. |

### Response Shape
```json
{
  "id": "dec-9bb1fbc8",
  "abstain": false,
  "top_choice": "option_a",
  "choice": "option_a",
  "confidence": 0.9241,
  "probabilities": {
    "option_a": 0.9241,
    "option_b": 0.0531,
    "option_c": 0.0228
  },
  "forward_seconds": 0.0452,
  "total_seconds": 0.1658,
  "model": "agent-jev-0.6b"
}
```

---

## 2. Native AgentJev Evaluation API (`/api/evaluate`)

For advanced pipelines or multi-question evaluations:

```json
{
  "state": "Production database latency jumped to 5000ms with CPU at 99%",
  "questions": [
    {
      "id": "q1",
      "type": "choice",
      "question": "Which triage priority?",
      "options": ["P0 Outage", "P1 Urgent", "P2 Routine"]
    }
  ]
}
```

**Response**:
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
          "margin": 0.8842
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

## 3. Python Client Usage

A lightweight client is provided in `scripts/jev.py`:

### Quick Start: Simplified Prompts

```python
import sys
sys.path.append("/Users/nan/.gemini/config/skills/jev-decide/scripts")
from jev import reflex, boolean, decide, score, evaluate

# 1. Universal single-prompt reflex (~35ms)
# Boolean gate:
is_emergency = reflex("Is acute myocardial infarction an emergency?")
print(is_emergency["result"], is_emergency["confidence"])  # True, 0.84

# Categorical selection (simple list of strings!):
action = reflex(
    prompt="Select immediate clinical priority",
    context="Patient presents with acute chest pain, BP 80/50, ST elevation",
    options=["Emergency cath lab", "Observation", "Discharge"]
)
print(action["top_choice"], action["confidence"])  # "Emergency cath lab"

# 2. Ordered rubric & risk scoring (~35ms)
risk = score(
    question="Rate sepsis risk",
    context="Patient has fever 103F, HR 135, BP 75/45, altered mental status",
    levels=["low", "moderate", "high", "critical"]
)
print(risk["level"], risk["score"])  # "critical", 2.85

# 3. Categorical choice via decide() (~45ms)
res = decide(
    state="Customer requesting refund past 30 days without receipt",
    options=["Approve exception", "Deny refund", "Escalate to supervisor"]
)
print(res["top_choice"])
```

### Full / Advanced Examples

```python
import sys
sys.path.append("/Users/nan/.gemini/config/skills/jev-decide/scripts")
from jev import decide, evaluate

# Quick pick-one decision
result = decide(
    state="Customer says: my credit card was charged twice for order #4021",
    criterion="Route to the appropriate support queue",
    options=[
        {"id": "billing", "description": "Payments, credit card charges, refunds, invoices"},
        {"id": "tech_support", "description": "Application errors, crashes, bugs"},
        {"id": "account", "description": "Password resets, profile updates"},
    ],
)
print(result["choice"])         # "billing"
print(result["confidence"])     # 0.9845
print(result["forward_seconds"])# ~0.04s

# Native typed evaluation
res = evaluate(
    state="Patient afebrile, vitals normal, wound healing well.",
    questions=[{
        "id": "q1",
        "type": "choice",
        "question": "Discharge disposition?",
        "options": ["Discharge home", "Keep for observation", "Admit to ICU"]
    }]
)
print(res["results"][0]["answers"][0]["description"])  # "Discharge home"
```

## When NOT to use Jev
- **Open-ended text generation**: Use System 2 Qwen 3.8 Flash Next (`/v1/chat/completions`) for multi-sentence generation.
- **Context exceeding 2,048 tokens**: AgentJev has a hard limit of 2,048 tokens. For documents over 2k tokens, summarize context first or use System 2.
