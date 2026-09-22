# Jev: Decision Engine Skills & Infrastructure for Coding Agents

Agent skills, workflows, client libraries, and server gateway infrastructure for the **Jev** high-speed decision engine, powered by **AgentJev-0.6B** (`aimeigaoshou/agent-jev`) running on NVIDIA DGX Blackwell (`spark-15486`).

Unlike slow autoregressive language models that generate reasoning tokens sequentially, Jev evaluates option candidates in parallel with permutation equivariance. Decisions execute in **35–80 ms** with calibrated confidence scores and an ultra-lightweight **2.45 GiB VRAM** footprint (reclaiming 14.1 GiB from legacy Kev-9B).

---

## Skills & Capabilities

| Skill | Directory | Primary Endpoint (Cloudflare Tunnel) | LAN Direct Endpoint | Best For |
|---|---|---|---|---|
| **`jev-decide`** | [`skills/jev-decide/`](skills/jev-decide/) | `POST https://api.clinivisa.com/v1/decide` | `http://192.168.0.106:8765/v1/decide` | Single-choice selection from a list (tool routing, team assignment, intent classification, triage) |
| **`jev-systemone`** | [`skills/jev-systemone/`](skills/jev-systemone/) | `POST https://api.clinivisa.com/api/evaluate` | `http://192.168.0.106:8149/api/evaluate` | Typed evaluations (`choice`, `boolean`, `score`), multi-question decision trees, scoring rubrics |

> **Public Cloudflare Tunnel Endpoint:**
> `https://api.clinivisa.com` (`/v1/decide`, `/api/evaluate`, `/api/info`, `/v1/systemone`, `/health`, `/v1/models`)

---

## Installation for Coding Agents

### Antigravity / Gemini Agents
Copy the skill folders to your personal or workspace configuration:
```bash
# User-global installation
cp -r skills/jev-decide ~/.gemini/config/skills/
cp -r skills/jev-systemone ~/.gemini/config/skills/
```

### Claude Code Agents
```bash
# Personal skills directory
mkdir -p ~/.claude/skills
cp -r skills/jev-decide ~/.claude/skills/
cp -r skills/jev-systemone ~/.claude/skills/
```

### Any Workspace / Project
```bash
# Project-level skills
mkdir -p .agents/skills
cp -r skills/jev-decide .agents/skills/
cp -r skills/jev-systemone .agents/skills/
```

---

## Python Client (`jev.py`)

A zero-dependency Python client (using Python standard library `urllib`) is provided in `jev.py`.

### 1. Single Decision (`decide`)

```python
from jev import decide

result = decide(
    state="User reports their credit card was charged twice for the renewal.",
    criterion="Route to the appropriate support department",
    options=[
        {"id": "billing", "description": "Invoices, subscriptions, and card charges"},
        {"id": "tech_support", "description": "Application crashes and software bugs"},
        {"id": "security", "description": "Compromised credentials or breach reports"},
    ],
)

print(f"Top Choice: {result['choice']}")
print(f"Confidence: {result['confidence']:.2%}")
print(f"Probabilities: {result['probabilities']}")
# Output:
# Top Choice: billing
# Confidence: 98.45%
```

### 2. Native Typed Evaluation (`evaluate`)

```python
from jev import evaluate

result = evaluate(
    state="Production database latency jumped to 5000ms with CPU at 99%",
    questions=[
        {
            "id": "triage",
            "type": "choice",
            "question": "Which triage priority?",
            "options": ["P0 Outage", "P1 Urgent", "P2 Routine"]
        },
        {
            "id": "escalation",
            "type": "boolean",
            "question": "Does this require on-call paging?",
            "criteria": {
                "true": "Immediate paging required",
                "false": "Can wait for business hours"
            }
        }
    ]
)

for ans in result["results"][0]["answers"]:
    print(ans["id"], ans.get("description") or ans.get("value"))
# Output:
# triage P0 Outage
# escalation True
```

---

## Server Architecture (`server/`)

The repository includes production server configurations deployed on NVIDIA DGX Blackwell:

- **`server/decider_adapter.py`**: FastAPI adapter running on port `8765`, adapting standard OpenJev `/v1/decide` requests into AgentJev evaluations.
- **`server/jev_gateway.py`**: Unified gateway running on port `9010`, handling CORS, reverse proxying, health diagnostics, and the legacy Kev-9B backward compatibility bridge.
- **`server/comparison_report.json`**: Head-to-head benchmark results validating AgentJev's 67% latency improvement and 5.1x throughput over Kev-9B.

---

## Raw HTTP Usage

### OpenJev Standard (`/v1/decide`)

```bash
curl -s -X POST https://api.clinivisa.com/v1/decide \
  -H 'Content-Type: application/json' \
  -d '{
    "state": "Build failed with segfault in libcuda.so",
    "criterion": "Which team should investigate?",
    "options": [
      {"id": "infra", "description": "Drivers, GPUs, and hardware"},
      {"id": "backend", "description": "Server code and APIs"},
      {"id": "frontend", "description": "Web client"}
    ]
  }'
```

### Native AgentJev Typed Evaluation (`/api/evaluate`)

```bash
curl -s -X POST https://api.clinivisa.com/api/evaluate \
  -H 'Content-Type: application/json' \
  -d '{
    "state": "Patient vital signs stable, afebrile.",
    "questions": [
      {
        "id": "q1",
        "type": "choice",
        "question": "Which disposition priority?",
        "options": ["Discharge home", "Admit to ICU", "Keep under observation"]
      }
    ]
  }'
```

---

## Configuration

| Environment Variable | Default | Purpose |
|---|---|---|
| `JEV_BASE_URL` | `https://api.clinivisa.com` | Base URL for Cloudflare Tunnel public endpoint |
| `JEV_HOST` | `api.clinivisa.com` | Hostname or IP. If `api.clinivisa.com`, uses HTTPS tunnel. If LAN IP, uses ports `:8765` and `:8149`. |
| `JEV_TIMEOUT` | `15` | Request timeout in seconds |

---

## Smoke Test

Run the included smoke test to verify connectivity and all decision paths:

```bash
# Test via Cloudflare Tunnel (default: https://api.clinivisa.com)
JEV_BASE_URL=https://api.clinivisa.com bash skills/jev-decide/scripts/smoke_jev.sh

# Or test locally on the same LAN as Blackwell
JEV_HOST=192.168.0.106 bash skills/jev-decide/scripts/smoke_jev.sh
```

---

## License

MIT
