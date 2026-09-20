---
name: jev-decide
description: "Route decisions through the Jev decision engine on Blackwell. Use when you need to pick one option from a list based on context — tool selection, ticket routing, intent classification, triage. Returns calibrated probabilities in <300ms. Triggers: decide, route, classify, pick, triage, which option, which tool."
---

# Jev Decide — Fast Decision Routing

## Overview

Jev Decide sends a context + options payload to the DiffusionGemma 26B decision engine
running on Blackwell (`192.168.0.106`). It returns a single choice with calibrated
probabilities and confidence scores — no autoregressive generation, no chain-of-thought.
Typical latency is **150–300 ms** for up to 8 options.

Use this skill whenever you need to **pick one thing from a list**:
- Which tool to call
- Which team owns a ticket
- Which workflow branch to take
- Intent classification
- Triage / severity routing

For advanced multi-question decisions (yes/no + choice + scoring in one call), use the
`jev-systemone` skill instead.

## Endpoints

- **Public (Cloudflare Tunnel)**:
  ```
  POST https://api.clinivisa.com/v1/decide
  Content-Type: application/json
  ```
- **Alternate Public Tunnel**: `https://demo.clinivisa.com/v1/decide`
- **LAN Direct (Internal Network)**:
  ```
  POST http://192.168.0.106:8765/v1/decide
  Content-Type: application/json
  ```

No API key required. Accessible globally via Cloudflare Tunnel or locally over LAN.

## Request Shape

```json
{
  "state": "<string or object — the context to decide on>",
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
| `state` | string or object | Yes | The situation, ticket, user message, or structured data to decide on. |
| `criterion` | string | Yes | A short sentence describing what you are deciding. |
| `options` | array of `{id, description}` | Yes | 2–8 options. `id` is the machine-readable label, `description` explains what it means (can be `null`). |

## Response Shape

```json
{
  "id": "dec-5006294d",
  "abstain": false,
  "top_choice": "option_a",
  "choice": "option_a",
  "confidence": 0.9913,
  "probabilities": {
    "option_a": 0.9913,
    "option_b": 0.0081,
    "option_c": 0.0006
  },
  "forward_seconds": 0.295,
  "total_seconds": 0.295,
  "model": "dgemma"
}
```

| Field | Description |
|---|---|
| `choice` | The winning option id. |
| `confidence` | Probability of the winning choice (0–1). |
| `probabilities` | Calibrated probability for every option. |
| `abstain` | `true` if the engine could not decide (all options equally unlikely). |
| `forward_seconds` | Engine inference time. |

## Usage Pattern (curl)

```bash
curl -s http://192.168.0.106:8765/v1/decide \
  -H 'content-type: application/json' \
  -d '{
    "state": "User says: my build is failing with a segfault in libcuda.so",
    "criterion": "Which team should handle this ticket?",
    "options": [
      {"id": "infra", "description": "Infrastructure, hardware, drivers, CUDA"},
      {"id": "backend", "description": "Application backend, APIs, databases"},
      {"id": "frontend", "description": "UI, web, mobile client"}
    ]
  }'
```

## Usage Pattern (Python)

```python
import httpx, json

def jev_decide(state: str, criterion: str, options: list[dict]) -> dict:
    """Pick one option from a list using the Jev decision engine."""
    resp = httpx.post(
        "http://192.168.0.106:8765/v1/decide",
        json={"state": state, "criterion": criterion, "options": options},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()

# Example: tool selection
result = jev_decide(
    state="User wants to know the weather in Tokyo tomorrow",
    criterion="Which tool should be called?",
    options=[
        {"id": "web_search", "description": "Search the internet for information"},
        {"id": "calculator", "description": "Perform mathematical calculations"},
        {"id": "weather_api", "description": "Get weather forecasts by location"},
        {"id": "calendar", "description": "Check or create calendar events"},
    ],
)
print(f"Use tool: {result['choice']} (confidence: {result['confidence']:.1%})")
# → Use tool: weather_api (confidence: 99.2%)
```

## Best Practices

1. **Be specific in `state`**: Include the raw user message, ticket body, or structured
   context. More detail → better decisions.
2. **Write clear `description`s**: The engine reads them. A `null` description means the
   `id` alone must be self-explanatory.
3. **2–8 options**: The engine handles up to ~16 but is calibrated best with 2–8.
4. **Trust the confidence**: Scores are calibrated probabilities from diffusion noise
   sampling, not softmax logits. A 0.95 means 95% of the time it would pick that option.
5. **Use `abstain`**: If `abstain: true`, the engine is uncertain — fall back to a
   language model or ask the user.
6. **Latency budget**: Expect 150–300 ms on the local network. Safe for real-time
   agentic loops.

## Health Check

```bash
curl -s http://192.168.0.106:8765/health
# → {"status": "ok", "engine": "dgemma", "port": 8011}
```

## When NOT to Use This

- **Open-ended generation**: Jev is a decision engine, not a chat model. It picks from
  your options; it does not generate text.
- **Complex multi-question decisions**: Use `jev-systemone` instead to ask yes/no +
  choice + scoring questions in a single call.
- **Knowledge-heavy questions**: Jev decides based on semantic context, not factual recall.
  Don't ask "What is the capital of France?" — ask "Given the user's message, which
  intent does it match?"
