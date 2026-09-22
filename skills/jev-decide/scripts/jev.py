"""jev — Lightweight Python client for the AgentJev decision engine on Blackwell.

Supports:
- Public Cloudflare Tunnel: https://api.clinivisa.com (no port needed)
- LAN Direct Access: http://192.168.0.106
    - Port 8765: OpenJev-compatible /v1/decide
    - Port 8149: Native AgentJev /api/evaluate and /api/info
    - Port 9010: Gateway (all endpoints + /v1/systemone shim)

Usage:
    from jev import decide, evaluate, info, health

    # 1. Quick single-choice decision (OpenJev standard schema)
    result = decide(
        state="User asks about billing charge discrepancy",
        criterion="Route to correct department",
        options=[
            {"id": "billing", "description": "Payments, refunds, and invoices"},
            {"id": "support", "description": "General product help and bugs"},
        ],
    )
    print(result["choice"])  # "billing"
    print(result["confidence"])  # 0.98

    # 2. Native AgentJev typed evaluation (choice, boolean, score)
    res = evaluate(
        state="Patient vital signs stable, afebrile for 48h.",
        questions=[
            {
                "id": "q1",
                "type": "choice",
                "question": "Which disposition priority?",
                "options": ["Discharge home", "Admit to ICU", "Keep under observation"]
            }
        ]
    )
    print(res["results"][0]["answers"][0]["description"])  # "Discharge home"
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError

__all__ = ["reflex", "decide", "boolean", "score", "evaluate", "info", "systemone", "health", "JevError"]

# Environment configuration
JEV_BASE_URL = os.environ.get("JEV_BASE_URL")
JEV_HOST = os.environ.get("JEV_HOST", "api.clinivisa.com")
TIMEOUT = int(os.environ.get("JEV_TIMEOUT", "15"))

if JEV_BASE_URL:
    _base = JEV_BASE_URL.rstrip("/")
    DECIDE_URL = f"{_base}/v1/decide"
    EVALUATE_URL = f"{_base}/api/evaluate"
    INFO_URL = f"{_base}/api/info"
    SYSTEMONE_URL = f"{_base}/v1/systemone"
    HEALTH_URL = f"{_base}/health"
elif "clinivisa.com" in JEV_HOST:
    _scheme = "http" if JEV_HOST.startswith("http://") else "https"
    _clean_host = JEV_HOST.replace("http://", "").replace("https://", "").rstrip("/")
    DECIDE_URL = f"{_scheme}://{_clean_host}/v1/decide"
    EVALUATE_URL = f"{_scheme}://{_clean_host}/api/evaluate"
    INFO_URL = f"{_scheme}://{_clean_host}/api/info"
    SYSTEMONE_URL = f"{_scheme}://{_clean_host}/v1/systemone"
    HEALTH_URL = f"{_scheme}://{_clean_host}/health"
else:
    # Direct LAN or IP host
    _clean_host = JEV_HOST.replace("http://", "").replace("https://", "").rstrip("/")
    DECIDE_URL = f"http://{_clean_host}:8765/v1/decide"
    EVALUATE_URL = f"http://{_clean_host}:8149/api/evaluate"
    INFO_URL = f"http://{_clean_host}:8149/api/info"
    SYSTEMONE_URL = f"http://{_clean_host}:9010/v1/systemone"
    HEALTH_URL = f"http://{_clean_host}:9010/health"


class JevError(Exception):
    """Raised when the Jev engine returns an error."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"Jev {status}: {message}")


def _post(url: str, payload: dict) -> dict:
    """Send a JSON POST and return parsed JSON response."""
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "jev-client/2.0"})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            msg = json.loads(body).get("error", {}).get("message", body)
        except (json.JSONDecodeError, AttributeError):
            msg = body
        raise JevError(e.code, msg) from e


def reflex(
    prompt: str,
    context: str | dict | list | None = None,
    options: list[str] | list[dict[str, str]] | str | None = None,
) -> dict[str, Any]:
    """Universal single-prompt System 1 reflex (~35ms).
    
    - If options provided: selects the winning choice.
    - If no options provided: evaluates prompt as True/False with calibrated confidence.
    """
    if options:
        return decide(state=context or prompt, criterion=prompt, options=options)
    return boolean(statement=prompt, context=context)


def boolean(
    statement: str,
    context: str | dict | list | None = None,
    true_criteria: str = "Condition is met / Affirmative",
    false_criteria: str = "Condition is not met / Negative",
) -> dict[str, Any]:
    """Ultra-fast binary verification gate (~35ms) with calibrated probability."""
    state_str = json.dumps(context, ensure_ascii=False) if isinstance(context, (dict, list)) else (str(context) if context else statement)
    payload = {
        "state": state_str,
        "questions": [
            {
                "id": "q1",
                "type": "boolean",
                "question": statement,
                "criteria": {"true": true_criteria, "false": false_criteria}
            }
        ]
    }
    raw = _post(EVALUATE_URL, payload)
    ans = raw["results"][0]["answers"][0]
    is_true = bool(ans.get("value", True))
    p = round(float(ans.get("probability", 0.5)), 4)
    return {
        "result": is_true,
        "confidence": p if is_true else round(1.0 - p, 4),
        "probability_true": p,
        "wall_ms": raw.get("usage", {}).get("wall_ms", 0.0),
        "model": "AgentJev-0.6B"
    }


def score(
    question: str,
    context: str | dict | list | None = None,
    levels: list[str] | None = None,
) -> dict[str, Any]:
    """Fast continuous/ordered rubric rating (~35ms)."""
    rubric_levels = levels or ["low", "moderate", "high", "critical"]
    state_str = json.dumps(context, ensure_ascii=False) if isinstance(context, (dict, list)) else (str(context) if context else question)
    payload = {
        "state": state_str,
        "questions": [
            {
                "id": "q_score",
                "type": "score",
                "question": question,
                "levels": rubric_levels
            }
        ]
    }
    raw = _post(EVALUATE_URL, payload)
    ans = raw["results"][0]["answers"][0]
    lvl_idx = int(ans.get("level", 0))
    lvl_name = rubric_levels[lvl_idx] if lvl_idx < len(rubric_levels) else str(lvl_idx)
    return {
        "level": lvl_name,
        "level_index": lvl_idx,
        "score": round(float(ans.get("score", 0.0)), 4),
        "distribution": {rubric_levels[int(k)]: round(float(v), 4) for k, v in ans.get("distribution", {}).items() if int(k) < len(rubric_levels)},
        "wall_ms": raw.get("usage", {}).get("wall_ms", 0.0),
        "model": "AgentJev-0.6B"
    }


def decide(
    state: str | dict | list,
    options: list[str] | list[dict[str, str | None]] | str,
    criterion: str = "Select the most appropriate option",
) -> dict[str, Any]:
    """Pick one option from a list using AgentJev-0.6B on Blackwell (~45ms).

    Args:
        state: The context to decide on (string, dict, or list).
        options: List of strings (e.g. ["A", "B"]), comma-separated string, or list of dicts.
        criterion: What you are deciding (optional, defaults to "Select the most appropriate option").

    Returns:
        Dict with keys: id, choice, top_choice, confidence, probabilities,
        abstain, forward_seconds, total_seconds, model.
    """
    if isinstance(options, str):
        opt_list = [o.strip() for o in options.split(",") if o.strip()]
        options_arg = [{"id": o, "description": o} for o in opt_list]
    elif options and isinstance(options[0], str):
        options_arg = [{"id": o, "description": o} for o in options]
    else:
        options_arg = options

    return _post(DECIDE_URL, {
        "state": state,
        "criterion": criterion,
        "options": options,
    })


def evaluate(
    state: str | dict | list,
    questions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Native typed evaluation with AgentJev-0.6B.

    Args:
        state: Shared context (text, object, or array).
        questions: List of question definitions. Supported types:
            - choice: {"id": str, "type": "choice", "question": str, "options": list[str]}
            - boolean: {"id": str, "type": "boolean", "question": str, "criteria": {"true": str, "false": str}}
            - score: {"id": str, "type": "score", "question": str}

    Returns:
        AgentJev native response with api_version, model, results, and usage.
    """
    return _post(EVALUATE_URL, {
        "state": state,
        "questions": questions,
    })


def info() -> dict[str, Any]:
    """Retrieve AgentJev runtime capabilities and configuration."""
    req = Request(INFO_URL, headers={"User-Agent": "jev-client/2.0"})
    with urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def systemone(
    state: str | dict | list,
    questions: dict[str, dict],
    *,
    seed: int | None = None,
    instructions: str | None = None,
    **extensions,
) -> dict[str, Any]:
    """Send a structured multi-question decision request via legacy compatibility shim.

    Note: Kev-9B is deprecated; requests are transparently translated to AgentJev-0.6B.
    For new implementations, prefer evaluate() or decide().
    """
    payload: dict[str, Any] = {"state": state, "questions": questions}
    if seed is not None:
        payload["seed"] = seed
    if instructions is not None:
        payload["instructions"] = instructions
    payload.update(extensions)
    return _post(SYSTEMONE_URL, payload)


def health() -> dict[str, Any]:
    """Check decision engine and gateway health. Returns status dict or raises."""
    req = Request(HEALTH_URL, headers={"User-Agent": "jev-client/2.0"})
    with urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())
