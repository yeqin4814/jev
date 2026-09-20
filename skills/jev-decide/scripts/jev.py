"""
jev — Lightweight Python client for the Jev decision engine on Blackwell.

Supports:
- Public Cloudflare Tunnel: https://api.clinivisa.com (no port needed)
- LAN Direct Access: http://192.168.0.106 (ports :8765 decide / :8011 systemone)

Usage:
    from jev import decide, systemone

    # Quick single-choice decision
    result = decide(
        state="User asks about billing",
        criterion="Route to department",
        options=[
            {"id": "billing", "description": "Payments and invoices"},
            {"id": "support", "description": "General help"},
        ],
    )
    print(result["choice"])  # "billing"

    # Advanced multi-question decision
    result = systemone(
        state={"ticket": "Server is on fire"},
        questions={
            "urgent": {"type": "noul", "instructions": "Is this urgent?"},
            "team": {
                "type": "choice",
                "instructions": "Which team?",
                "criteria": {"infra": None, "backend": None},
            },
        },
    )
    print(result["answers"]["urgent"]["noul"])  # 0.95
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError

__all__ = ["decide", "systemone", "health", "JevError"]

# Environment configuration
JEV_BASE_URL = os.environ.get("JEV_BASE_URL")
JEV_HOST = os.environ.get("JEV_HOST", "api.clinivisa.com")
TIMEOUT = int(os.environ.get("JEV_TIMEOUT", "15"))

if JEV_BASE_URL:
    _base = JEV_BASE_URL.rstrip("/")
    DECIDE_URL = f"{_base}/v1/decide"
    SYSTEMONE_URL = f"{_base}/v1/systemone"
    HEALTH_URL = f"{_base}/health"
elif "clinivisa.com" in JEV_HOST:
    _scheme = "http" if JEV_HOST.startswith("http://") else "https"
    _clean_host = JEV_HOST.replace("http://", "").replace("https://", "").rstrip("/")
    DECIDE_URL = f"{_scheme}://{_clean_host}/v1/decide"
    SYSTEMONE_URL = f"{_scheme}://{_clean_host}/v1/systemone"
    HEALTH_URL = f"{_scheme}://{_clean_host}/health"
else:
    # Direct LAN or IP host
    _clean_host = JEV_HOST.replace("http://", "").replace("https://", "").rstrip("/")
    DECIDE_URL = f"http://{_clean_host}:8765/v1/decide"
    SYSTEMONE_URL = f"http://{_clean_host}:8011/v1/systemone"
    HEALTH_URL = f"http://{_clean_host}:8765/health"


class JevError(Exception):
    """Raised when the Jev engine returns an error."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"Jev {status}: {message}")


def _post(url: str, payload: dict) -> dict:
    """Send a JSON POST and return parsed JSON response."""
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "jev-client/1.0"})
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
    """Pick one option from a list.

    Args:
        state: The context to decide on (string, dict, or list).
        criterion: What you are deciding.
        options: List of {"id": str, "description": str | None}.

    Returns:
        Dict with keys: choice, confidence, probabilities, abstain,
        forward_seconds, total_seconds, model.
    """
    return _post(DECIDE_URL, {
        "state": state,
        "criterion": criterion,
        "options": options,
    })


def systemone(
    state: str | dict | list,
    questions: dict[str, dict],
    *,
    seed: int | None = None,
    instructions: str | None = None,
    **extensions,
) -> dict[str, Any]:
    """Send a structured multi-question decision request.

    Args:
        state: The content all questions are asked about.
        questions: Map of question_id -> question definition.
            Each question has: type ("noul"|"choice"|"score"),
            instructions (str), and criteria (type-dependent).
        seed: Optional seed for reproducibility (default 42).
        instructions: Optional shared context before all questions.
        **extensions: Additional Jev extensions (samples, think,
            sequential, auto_max, auto_threshold, steps, etc.)

    Returns:
        Dict with keys: answers, usage, model, diagnostics.
    """
    payload: dict[str, Any] = {"state": state, "questions": questions}
    if seed is not None:
        payload["seed"] = seed
    if instructions is not None:
        payload["instructions"] = instructions
    payload.update(extensions)
    return _post(SYSTEMONE_URL, payload)


def health() -> dict[str, Any]:
    """Check engine health. Returns status dict or raises."""
    req = Request(HEALTH_URL, headers={"User-Agent": "jev-client/1.0"})
    with urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())
