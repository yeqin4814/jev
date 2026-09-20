---
name: jev-systemone
description: "Advanced Jev API for structured multi-question decisions. Supports yes/no (noul), choice, and score question types in a single call with dependencies, conditional questions, and vision input. Use for complex decision trees, multi-criteria triage, scoring rubrics, or when you need more than a simple pick-one. Triggers: systemone, multi-question, noul, score, decision tree, triage rubric."
---

# Jev SystemOne — Structured Multi-Question Decisions

## Overview

The full Jev `/v1/systemone` API runs structured decision requests against
DiffusionGemma 26B-A4B (NVFP4) on Blackwell. Unlike `jev-decide` (which picks one
option), SystemOne answers **multiple typed questions in a single call** — yes/no
probability, categorical choice, and ordered scoring — with optional dependencies
between them.

All questions are read in a single diffusion canvas pass (parallel, not
autoregressive), giving sub-200ms latency for 3+ questions simultaneously.

**Use SystemOne when you need:**
- Multiple decisions from the same context in one shot
- Yes/no probability estimates (noul)
- Ordered scoring rubrics (score)
- Conditional question chains (ask question B only if question A answers "yes")
- Vision-based decisions on images

For simple single-choice routing, use the simpler `jev-decide` skill.

## Endpoints

- **Public (Cloudflare Tunnel)**:
  ```
  POST https://api.clinivisa.com/v1/systemone
  Content-Type: application/json
  ```
- **LAN Direct (Internal Network)**:
  ```
  POST http://192.168.0.106:8011/v1/systemone
  Content-Type: application/json
  ```

No API key required. Accessible globally via Cloudflare Tunnel (`api.clinivisa.com`) or locally over LAN.

## Question Types

### `noul` — Yes/No Probability

Returns a probability of "yes" between 0 and 1. Not a binary flag — it's a
calibrated confidence score.

```json
{
  "type": "noul",
  "instructions": "Does the customer need a reply within the hour?",
  "criteria": {
    "true": "The situation is time-sensitive or urgent",
    "false": "The request can wait"
  }
}
```

- `criteria` is optional. If provided, `true`/`false` descriptions help the engine
  understand what yes/no mean in this context.
- **Response**: `{"noul": 0.9098}` — 91% probability of yes.

### `choice` — Pick One Option

Returns the most probable option with per-option probabilities.

```json
{
  "type": "choice",
  "instructions": "Which team owns this?",
  "criteria": {
    "billing": null,
    "outage": "service is down",
    "feature": "feature request or enhancement"
  }
}
```

- `criteria` is required. Object mapping option names to descriptions (`null` = the
  name is self-explanatory).
- Option order in the response matches declaration order.
- **Response**: `{"choice": "outage", "probabilities": {"billing": 0.01, "outage": 0.98, "feature": 0.01}, "confidence": 0.98}`

### `score` — Ordered Scale Rating

Returns a probability-weighted position on an ordered scale.

```json
{
  "type": "score",
  "instructions": "How angry is the customer?",
  "criteria": ["calm", "annoyed", "furious"]
}
```

- `criteria` is required. Array of level names from lowest to highest (minimum 2).
- **Response**: `{"score": 1.999, "legend": {"0": "calm", "1": "annoyed", "2": "furious"}, "probabilities": {"0": 0.0002, "1": 0.0002, "2": 0.9996}, "confidence": 0.9996}`
- `score` is the probability-weighted index (0-based). A score of 1.999 with 3 levels
  means nearly max anger.

## Full Request Shape

```json
{
  "model": "jev-latest",
  "state": "<context string, object, or array>",
  "questions": {
    "q_id_1": {"type": "noul", "instructions": "...", "criteria": {...}},
    "q_id_2": {"type": "choice", "instructions": "...", "criteria": {...}},
    "q_id_3": {"type": "score", "instructions": "...", "criteria": [...]}
  },
  "seed": 42,
  "instructions": "Optional shared context rendered before all questions"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `state` | string, object, or array | Yes | The content all questions are asked about. |
| `questions` | object | Yes | Map of question ID → question object. Answer IDs mirror question IDs. |
| `model` | string | No | Accepted for Jev client compatibility, ignored by the engine. |
| `seed` | integer | No | Seeds noise draws for reproducibility. Default 42. |
| `instructions` | string | No | Shared context rendered before questions; requests sharing it share a KV prefix cache. |

## Full Response Shape

```json
{
  "answers": {
    "q_id_1": {"noul": 0.91},
    "q_id_2": {"choice": "outage", "probabilities": {...}, "confidence": 0.98},
    "q_id_3": {"score": 1.99, "legend": {...}, "probabilities": {...}, "confidence": 0.99}
  },
  "usage": {"input_tokens": 245, "output_tokens": 12},
  "model": "diffusiongemma-26B-A4B-it-NVFP4"
}
```

## Dependencies Between Questions

Questions can depend on each other. The engine resolves them in stages.

### `depends_on` — Sequencing

Question B sees Question A's answer in its prompt:

```json
{
  "urgent": {
    "type": "noul",
    "instructions": "Is this urgent?"
  },
  "escalation_level": {
    "type": "score",
    "instructions": "How far should we escalate?",
    "criteria": ["none", "team_lead", "vp", "ceo"],
    "depends_on": ["urgent"]
  }
}
```

### `ask_if` — Conditional Questions

Only ask if a prior question's answer matches:

```json
{
  "is_bug": {
    "type": "noul",
    "instructions": "Is this a bug report?"
  },
  "severity": {
    "type": "score",
    "instructions": "How severe is this bug?",
    "criteria": ["cosmetic", "degraded", "broken", "data_loss"],
    "ask_if": {"is_bug": ["yes"]}
  }
}
```

If `is_bug` answers "no", `severity` is `null` in the response — no wasted compute.

### `alone` — Isolation

Read a question in its own diffusion canvas to prevent bias from adjacent questions:

```json
{
  "direction": {
    "type": "choice",
    "instructions": "Which direction should the agent go?",
    "criteria": {"north": null, "south": null, "east": null, "west": null},
    "alone": true
  }
}
```

## Advanced Extensions

These optional top-level keys fine-tune inference behavior:

| Key | Default | Description |
|---|---|---|
| `samples` | `"auto"` | Number of noise draws to average. `"auto"` does one read, then more if entropy exceeds `auto_threshold`. |
| `auto_max` | 4 | Maximum reads under `"auto"`. |
| `auto_threshold` | 0.1 | Entropy threshold for additional reads. |
| `think` | 0 | Max thought tokens before the read. Adds one generation per decision but improves quality on ambiguous inputs. |
| `sequential` | false | Run chunks in order, prefilling each chunk's answers before the next. Later answers condition on earlier ones. |
| `steps` | 1 | Denoise steps per read. More steps = more canvas drift from template. |

## Complete Example: Ticket Triage Pipeline

```python
import httpx

JEV_URL = "http://192.168.0.106:8011/v1/systemone"

def triage_ticket(ticket_text: str) -> dict:
    """Full triage: urgency + team + severity + tone in one call."""
    resp = httpx.post(JEV_URL, json={
        "state": {"ticket": ticket_text},
        "instructions": "Triage this support ticket.",
        "questions": {
            "urgent": {
                "type": "noul",
                "instructions": "Does the customer need a response within one hour?",
                "criteria": {
                    "true": "Time-sensitive, production down, or explicit deadline",
                    "false": "Can wait for normal queue processing"
                }
            },
            "team": {
                "type": "choice",
                "instructions": "Which team should own this ticket?",
                "criteria": {
                    "billing": "Invoices, payments, subscriptions",
                    "outage": "Service down, infrastructure failure",
                    "security": "Breaches, credential leaks, access issues",
                    "feature": "Feature requests, enhancement ideas",
                    "support": "General help, how-to questions"
                }
            },
            "severity": {
                "type": "score",
                "instructions": "How severe is the impact?",
                "criteria": ["cosmetic", "degraded", "broken", "critical"]
            },
            "tone": {
                "type": "score",
                "instructions": "How frustrated is the customer?",
                "criteria": ["calm", "annoyed", "frustrated", "furious"],
                "alone": true
            }
        }
    }, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    a = data["answers"]
    return {
        "urgent": a["urgent"]["noul"] > 0.5,
        "urgency_prob": a["urgent"]["noul"],
        "team": a["team"]["choice"],
        "team_confidence": a["team"]["confidence"],
        "severity": list(a["severity"]["legend"].values())[
            round(a["severity"]["score"])
        ],
        "tone": list(a["tone"]["legend"].values())[
            round(a["tone"]["score"])
        ],
    }

# Usage
result = triage_ticket("Everything is down and we have a demo at noon. Fix it NOW.")
# → {'urgent': True, 'urgency_prob': 0.91, 'team': 'outage',
#     'team_confidence': 0.98, 'severity': 'critical', 'tone': 'furious'}
```

## Complete Example: Agent Tool Selection with Fallback

```python
import httpx

def select_tool(user_message: str, available_tools: list[dict]) -> str | None:
    """Use Jev to pick the right tool, with abstention if unclear."""
    criteria = {t["name"]: t.get("description") for t in available_tools}
    resp = httpx.post("http://192.168.0.106:8011/v1/systemone", json={
        "state": user_message,
        "questions": {
            "tool": {
                "type": "choice",
                "instructions": "Which tool should be called to handle this request?",
                "criteria": criteria
            },
            "confident": {
                "type": "noul",
                "instructions": "Is the tool selection clearly correct, or is the request ambiguous?",
                "depends_on": ["tool"]
            }
        }
    }, timeout=10)
    resp.raise_for_status()
    a = resp.json()["answers"]
    if a["confident"]["noul"] < 0.6:
        return None  # Too uncertain — ask the user or use LLM reasoning
    return a["tool"]["choice"]
```

## Health Check

```bash
curl -s http://192.168.0.106:8011/health
# Engine-level health check
```

## Error Handling

| HTTP Code | Meaning |
|---|---|
| 200 | Success |
| 422 | Validation error — malformed question, missing criteria, invalid type. Check `error.message`. |
| 502 | Upstream vLLM engine failure. Retry or check container health. |

## Best Practices

1. **Pack related questions together**: All questions in one request share the same
   diffusion canvas and KV cache. 3 questions in 1 call is faster than 3 separate calls.
2. **Use `instructions` for shared context**: If multiple requests share the same system
   prompt or rubric, put it in `instructions` — the engine caches the KV prefix.
3. **Use `depends_on` sparingly**: Each dependency stage adds ~100ms. Only use when
   later questions genuinely need earlier answers.
4. **Use `ask_if` to skip irrelevant questions**: Saves compute and avoids noisy answers
   to questions that don't apply.
5. **Use `alone: true` for bias-prone questions**: Directional or spatial questions can
   bias each other when read in the same canvas.
6. **Interpret `noul` as probability, not boolean**: A `noul` of 0.65 means "lean yes but
   uncertain." Set your own thresholds per use case.
7. **Score values are continuous**: A `score` of 1.7 on a 0–2 scale means "between levels
   1 and 2, closer to 2." Use rounding or thresholds as appropriate.
8. **Keep `state` focused**: Include only the context the questions need. Large irrelevant
   state dilutes attention.
