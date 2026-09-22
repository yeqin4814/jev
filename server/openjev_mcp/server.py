"""OpenJEV Model Context Protocol (MCP) server for Hermes Agent & Coding Agents.
Powered by AgentJev-0.6B on NVIDIA DGX Blackwell (:8149 / :8765).
Provides ultra-fast (35-45ms) System 1 reflexive decision logic without autoregressive token generation.
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


def _normalize_state(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def _normalize_options(options: Union[List[Any], str]) -> List[str]:
    if isinstance(options, str):
        return [p.strip() for p in options.replace("\n", ",").split(",") if p.strip()]
    out = []
    for o in options:
        if isinstance(o, str):
            out.append(o.strip())
        elif isinstance(o, dict):
            out.append(str(o.get("description", o.get("text", o.get("id", "")))))
        else:
            out.append(str(o))
    return [o for o in out if o]


@server.tool(
    name="openjev_reflex",
    description=(
        "Universal System 1 reflex tool (35-45ms). Simply pass a prompt/question. "
        "If options are provided, picks the best candidate. If no options are provided, "
        "evaluates the statement as True/False with calibrated confidence. "
        "Zero autoregressive token generation."
    )
)
async def openjev_reflex(
    prompt: str,
    context: Optional[str] = None,
    options: Optional[Union[List[str], str]] = None,
) -> str:
    # If options given, route to decide
    if options:
        opts = _normalize_options(options)
        if len(opts) > 1:
            return await openjev_decide(state=context or prompt, criterion=prompt, options=opts)
        elif len(opts) == 1:
            return await openjev_boolean(statement=opts[0], context=context or prompt)

    # Otherwise boolean verification
    return await openjev_boolean(statement=prompt, context=context)


@server.tool(
    name="openjev_boolean",
    description=(
        "Ultra-fast System 1 binary verification gate (35ms). "
        "Evaluates whether a statement, condition, or hypothesis is True or False with calibrated probability. "
        "Takes a simple statement or question (and optional context). "
        "Use for rapid guardrails, safety validation, incident escalation gating, and conditional branching."
    )
)
async def openjev_boolean(
    statement: str,
    context: Optional[Union[str, Dict[str, Any], List[Any]]] = None,
    true_criteria: Optional[str] = "Condition is met / Affirmative",
    false_criteria: Optional[str] = "Condition is not met / Negative",
    # Backwards compatibility aliases
    state: Optional[Union[str, Dict[str, Any], List[Any]]] = None,
    question: Optional[str] = None,
) -> str:
    effective_statement = statement or question or ""
    effective_context = _normalize_state(context or state or effective_statement)
    effective_question = effective_statement or "Is the statement true?"

    payload = {
        "state": effective_context,
        "questions": [
            {
                "id": "q1",
                "type": "boolean",
                "question": effective_question,
                "criteria": {
                    "true": true_criteria or "Condition is met / Affirmative",
                    "false": false_criteria or "Condition is not met / Negative"
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
    name="openjev_decide",
    description=(
        "High-speed System 1 categorical decision layer powered by AgentJev-0.6B on Blackwell (45ms). "
        "Selects the winning choice from 2 to 255 candidate options in a single forward pass without token generation. "
        "options can be a simple list of strings [A, B, C] or a comma-separated string."
    )
)
async def openjev_decide(
    options: Union[List[str], List[Dict[str, str]], str],
    state: Optional[Union[str, Dict[str, Any], List[Any]]] = "",
    criterion: Optional[str] = "Select the most appropriate option",
    # Backwards compatibility alias
    context: Optional[Union[str, Dict[str, Any], List[Any]]] = None,
) -> str:
    effective_state = state if state != "" else (context or "")
    opts = _normalize_options(options)
    formatted_options = [{"id": o, "description": o} for o in opts]

    payload = {
        "state": effective_state,
        "criterion": criterion or "Select the most appropriate option",
        "options": formatted_options,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(DECIDE_URL, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return json.dumps({
                    "choice": data["choice"],
                    "top_choice": data.get("top_choice", data["choice"]),
                    "abstain": data.get("abstain", False),
                    "confidence": round(data["confidence"], 4),
                    "probabilities": {k: round(v, 4) for k, v in data["probabilities"].items()},
                    "forward_seconds": round(data["forward_seconds"], 3),
                    "total_seconds": round(data["total_seconds"], 3),
                    "model": data.get("model", "agent-jev-0.6b")
                }, indent=2)
            else:
                return json.dumps({"error": f"Decider adapter returned HTTP {resp.status_code}: {resp.text}"})
    except Exception as e:
        return json.dumps({"error": f"Failed to connect to OpenJEV decider adapter at {DECIDE_URL}: {e}"})


@server.tool(
    name="openjev_score",
    description=(
        "Fast System 1 ordered rating / severity scoring in 35ms. "
        "Evaluates context against a rubric or question, returning an expected-value score "
        "and discrete level (e.g. low, moderate, high, critical)."
    )
)
async def openjev_score(
    question: str,
    context: Optional[Union[str, Dict[str, Any], List[Any]]] = None,
    levels: Optional[List[str]] = None,
    # Backwards compatibility alias
    state: Optional[Union[str, Dict[str, Any], List[Any]]] = None,
) -> str:
    effective_context = _normalize_state(context or state or question)
    rubric_levels = levels or ["low", "moderate", "high", "critical"]

    payload = {
        "state": effective_context,
        "questions": [
            {
                "id": "q_score",
                "type": "score",
                "question": question,
                "levels": rubric_levels
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(EVALUATE_URL, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                ans = data["results"][0]["answers"][0]
                lvl_idx = int(ans.get("level", 0))
                lvl_name = rubric_levels[lvl_idx] if lvl_idx < len(rubric_levels) else str(lvl_idx)
                return json.dumps({
                    "level": lvl_name,
                    "level_index": lvl_idx,
                    "score": round(float(ans.get("score", 0.0)), 4),
                    "distribution": {rubric_levels[int(k)]: round(float(v), 4) for k, v in ans.get("distribution", {}).items() if int(k) < len(rubric_levels)},
                    "wall_ms": data.get("usage", {}).get("wall_ms", 0.0),
                    "model": "AgentJev-0.6B"
                }, indent=2)
            else:
                return json.dumps({"error": f"AgentJev engine returned HTTP {resp.status_code}: {resp.text}"})
    except Exception as e:
        return json.dumps({"error": f"Failed to connect to AgentJev engine at {EVALUATE_URL}: {e}"})


@server.tool(
    name="openjev_evaluate",
    description=(
        "Multi-question structured triage pass in 40ms. "
        "Evaluates multiple typed questions (choice, boolean, score) in a single parallel canvas pass without sequential generation overhead. "
        "Ideal for multi-criteria incident triage, risk assessment, and scoring rubrics."
    )
)
async def openjev_evaluate(
    state: Union[str, Dict[str, Any], List[Any]],
    questions: List[Dict[str, Any]],
) -> str:
    state_str = _normalize_state(state)
    
    # Auto-fill missing fields if simplified question objects provided
    normalized_questions = []
    for idx, q in enumerate(questions):
        q_copy = dict(q)
        if "id" not in q_copy:
            q_copy["id"] = f"q{idx+1}"
        if "type" not in q_copy:
            q_copy["type"] = "choice" if "options" in q_copy else "boolean"
        if q_copy["type"] == "boolean" and "criteria" not in q_copy:
            q_copy["criteria"] = {"true": "Affirmative / Condition met", "false": "Negative / Condition not met"}
        normalized_questions.append(q_copy)

    payload = {
        "state": state_str,
        "questions": normalized_questions
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
