"""OpenJEV Model Context Protocol (MCP) server for Hermes Agent & Coding Agents.
Powered by AgentJev-0.6B on NVIDIA DGX Blackwell (:8149 / :8765).
Provides ultra-fast (~35-45ms) System 1 reflexive decision logic without autoregressive token generation.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Union, Optional
import httpx
from mcp.server.mcpserver import MCPServer

server = MCPServer("openjev-decision-layer")

DECIDE_URL = "http://127.0.0.1:8765/v1/decide"
EVALUATE_URL = "http://127.0.0.1:8149/api/evaluate"
INFO_URL = "http://127.0.0.1:8149/api/info"


@server.tool(
    name="openjev_decide",
    description="High-speed System 1 categorical decision layer powered by AgentJev-0.6B on Blackwell (~45ms). Reads native logits across declared candidate choices in a single forward pass without autoregressive token generation. Use for deterministic classification, tool selection, ticket triage, workflow routing, and evidence verification without JSON parsing errors."
)
async def openjev_decide(
    state: Union[str, Dict[str, Any], List[Any]],
    criterion: str,
    options: List[Dict[str, str]],
) -> str:
    payload = {
        "state": state,
        "criterion": criterion,
        "options": options,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(DECIDE_URL, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return json.dumps({
                    "choice": data["choice"],
                    "confidence": round(data["confidence"], 4),
                    "probabilities": {k: round(v, 4) for k, v in data["probabilities"].items()},
                    "forward_seconds": round(data["forward_seconds"], 3),
                    "total_seconds": round(data["total_seconds"], 3),
                    "id": data["id"],
                    "model": data.get("model", "agent-jev-0.6b")
                }, indent=2)
            else:
                return json.dumps({"error": f"Decider adapter returned HTTP {resp.status_code}: {resp.text}"})
    except Exception as e:
        return json.dumps({"error": f"Failed to connect to OpenJEV decider adapter at {DECIDE_URL}: {e}"})


@server.tool(
    name="openjev_boolean",
    description="Ultra-fast System 1 binary verification gate (~35ms). Evaluates whether a statement, condition, or hypothesis is True or False with calibrated probability. Use for rapid guardrails, safety validation, incident escalation gating, and conditional branching without LLM deliberation."
)
async def openjev_boolean(
    state: Union[str, Dict[str, Any], List[Any]],
    question: str,
    true_criteria: str = "Condition is met / Affirmative",
    false_criteria: str = "Condition is not met / Negative",
) -> str:
    state_str = json.dumps(state, ensure_ascii=False) if isinstance(state, (dict, list)) else str(state)
    payload = {
        "state": state_str,
        "questions": [
            {
                "id": "q1",
                "type": "boolean",
                "question": question,
                "criteria": {
                    "true": true_criteria,
                    "false": false_criteria
                }
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(EVALUATE_URL, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                ans = data["results"][0]["answers"][0]
                is_true = bool(ans.get("value", True))
                p = round(float(ans.get("probability", 0.5)), 4)
                wall_ms = data.get("usage", {}).get("wall_ms", 0.0)
                return json.dumps({
                    "result": is_true,
                    "value": "true" if is_true else "false",
                    "confidence": p if is_true else round(1.0 - p, 4),
                    "probability_true": p,
                    "wall_ms": wall_ms,
                    "model": "AgentJev-0.6B"
                }, indent=2)
            else:
                return json.dumps({"error": f"AgentJev engine returned HTTP {resp.status_code}: {resp.text}"})
    except Exception as e:
        return json.dumps({"error": f"Failed to connect to AgentJev engine at {EVALUATE_URL}: {e}"})


@server.tool(
    name="openjev_evaluate",
    description="Multi-question structured triage pass in ~40ms. Evaluates multiple typed questions (choice, boolean, score) in a single parallel canvas pass without sequential generation overhead. Ideal for multi-criteria incident triage, risk assessment, and scoring rubrics."
)
async def openjev_evaluate(
    state: Union[str, Dict[str, Any], List[Any]],
    questions: List[Dict[str, Any]],
) -> str:
    state_str = json.dumps(state, ensure_ascii=False) if isinstance(state, (dict, list)) else str(state)
    payload = {
        "state": state_str,
        "questions": questions
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(EVALUATE_URL, json=payload)
            if resp.status_code == 200:
                return resp.text
            else:
                return json.dumps({"error": f"AgentJev engine returned HTTP {resp.status_code}: {resp.text}"})
    except Exception as e:
        return json.dumps({"error": f"Failed to connect to AgentJev engine at {EVALUATE_URL}: {e}"})


if __name__ == "__main__":
    server.run(transport="stdio")
