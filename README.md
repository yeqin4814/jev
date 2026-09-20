# Jev: Decision Engine Skills for Coding Agents

Agent skills, workflows, and client libraries for the **Jev** high-speed decision engine, backed by **DiffusionGemma 26B-A4B (NVFP4)** running via `djev-spark` on Blackwell.

Unlike autoregressive language models that generate text token-by-token with chain-of-thought overhead, Jev scores options and answers typed questions in parallel across a discrete diffusion canvas. Decisions complete in **150–300 ms** with calibrated probability scores.

---

## Skills Included

## Skills Included

| Skill | Directory | Primary Endpoint (Cloudflare Tunnel) | LAN Direct Endpoint | Best For |
|---|---|---|---|---|
| **`jev-decide`** | [`skills/jev-decide/`](skills/jev-decide/) | `POST https://api.clinivisa.com/v1/decide` | `http://192.168.0.106:8765/v1/decide` | Single-choice selection from a list (tool routing, team assignment, intent classification, triage) |
| **`jev-systemone`** | [`skills/jev-systemone/`](skills/jev-systemone/) | `POST https://api.clinivisa.com/v1/systemone` | `http://192.168.0.106:8011/v1/systemone` | Full multi-question decisions (`noul` yes/no, `choice`, `score` rubric), question dependencies (`depends_on`, `ask_if`), and vision |

> **Public Tunnel Endpoints:**
> - Primary: `https://api.clinivisa.com` (`/v1/decide`, `/v1/systemone`, `/health`, `/v1/models`)
> - Alternate: `https://demo.clinivisa.com` and `https://demo.evidentos.com`

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
# Confidence: 99.13%
```

### 2. Multi-Question Structured Decision (`systemone`)

```python
from jev import systemone

result = systemone(
    state={"ticket": "All production services are down and the executive team demo is in 30 minutes."},
    instructions="Triage this incoming incident.",
    questions={
        "urgent": {
            "type": "noul",
            "instructions": "Does this require immediate escalation within 15 minutes?",
        },
        "team": {
            "type": "choice",
            "instructions": "Which response team should be paged?",
            "criteria": {
                "sre_outage": "Site reliability and critical infrastructure down",
                "application": "App bug or logic error",
                "customer_success": "Customer communication only",
            },
        },
        "severity": {
            "type": "score",
            "instructions": "Incident severity score",
            "criteria": ["sev3_minor", "sev2_major", "sev1_critical", "sev0_catastrophic"],
        },
    },
)

answers = result["answers"]
print("Urgency probability:", answers["urgent"]["noul"])
print("Team:", answers["team"]["choice"], answers["team"]["confidence"])
print("Severity:", answers["severity"]["score"], answers["severity"]["confidence"])
```

---

## Raw HTTP Usage

### Curl Example (`/v1/decide`)

```bash
curl -s http://192.168.0.106:8765/v1/decide \
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

### Curl Example (`/v1/systemone`)

```bash
curl -s http://192.168.0.106:8011/v1/systemone \
  -H 'Content-Type: application/json' \
  -d '{
    "state": {"ticket": "Database connection pool exhausted"},
    "questions": {
      "urgent": {"type": "noul", "instructions": "Is service degraded?"},
      "area": {
        "type": "choice",
        "instructions": "Which domain?",
        "criteria": {"db": "Database ops", "api": "REST APIs", "web": "Frontend"}
      }
    }
  }'
```

---

## Configuration
 
| Environment Variable | Default | Purpose |
|---|---|---|
| `JEV_BASE_URL` | `https://api.clinivisa.com` | Base URL for Cloudflare Tunnel public endpoint (e.g. `https://api.clinivisa.com` or `https://demo.clinivisa.com`) |
| `JEV_HOST` | `api.clinivisa.com` | Hostname or IP. If domain contains `clinivisa.com` or `evidentos.com`, uses HTTPS tunnel. If IP (e.g. `192.168.0.106`), uses direct LAN ports (`:8765` and `:8011`). |
| `JEV_TIMEOUT` | `15` | Request timeout in seconds |

---

## Smoke Test

Run the included smoke test to verify connectivity and all decision paths:

```bash
# Test via Cloudflare Tunnel (default: https://api.clinivisa.com)
JEV_BASE_URL=https://api.clinivisa.com bash skills/jev-decide/scripts/smoke_jev.sh

# Or test via alternate tunnel (demo.clinivisa.com)
JEV_BASE_URL=https://demo.clinivisa.com bash skills/jev-decide/scripts/smoke_jev.sh

# Or test locally on the same LAN as Blackwell
JEV_HOST=192.168.0.106 bash skills/jev-decide/scripts/smoke_jev.sh
```

---

## License

MIT
