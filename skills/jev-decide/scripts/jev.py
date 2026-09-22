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

__all__ = ["decide", "evaluate", "info", "systemone", "health", "JevError"]

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


def decide(
    state: str | dict | list,
    criterion: str,
    options: list[dict[str, str | None]],
) -> dict[str, Any]:
    """Pick one option from a list using AgentJev-0.6B on Blackwell.

    Args:
        state: The context to decide on (string, dict, or list).
        criterion: What you are deciding.
        options: List of {"id": str, "description": str | None}.

    Returns:
        Dict with keys: id, choice, top_choice, confidence, probabilities,
        abstain, forward_seconds, total_seconds, model.
    """
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
