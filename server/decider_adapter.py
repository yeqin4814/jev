"""Clinivisa Decider Adapter v2.2.0
Exposes openjev-style POST /v1/decide on :8765 with simplified, ultra-flexible input schemas.
Supports options as list of strings, list of dicts, or comma-separated string.
Primary backend: AgentJev-0.6B (:8149) for ~35-80ms reflex decisions.
"""
import json, os, time, uuid
import urllib.request
import urllib.error
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Union, Dict, List, Any, Optional

AGENT_JEV_UPSTREAM = os.environ.get("AGENT_JEV_UPSTREAM", "http://127.0.0.1:8149/api/evaluate")
AGENT_JEV_HEALTH = os.environ.get("AGENT_JEV_HEALTH", "http://127.0.0.1:8149/api/info")

app = FastAPI(title="Clinivisa Decider Adapter", version="2.2.0")

class Option(BaseModel):
    id: str
    description: str = ""

class DecideReq(BaseModel):
    state: Union[str, Dict[str, Any], List[Any]] = ""
    criterion: Optional[str] = "Select the most appropriate option"
    options: Union[List[str], List[Option], str]

@app.get("/health")
@app.get("/v1/decide/health")
def health():
    try:
        with urllib.request.urlopen(AGENT_JEV_HEALTH, timeout=3) as r:
            up = json.loads(r.read())
        return {
            "status": "ready",
            "backend": "agent-jev-0.6b",
            "model": up.get("model", "AgentJev-0.6B"),
            "deprecated_models": {"kev-9b": "retired"}
        }
    except Exception as e:
        raise HTTPException(503, f"AgentJev engine unavailable on port 8149: {e}")

@app.post("/v1/decide")
def decide(req: DecideReq):
    t0 = time.time()
    abstain_below = float(os.environ.get("DECIDER_ABSTAIN_BELOW", "0.3"))
    state_str = json.dumps(req.state, ensure_ascii=False) if isinstance(req.state, (dict, list)) else str(req.state)
    criterion_str = req.criterion.strip() if req.criterion else "Select the most appropriate option"
    
    # Normalize options: string, list of strings, or list of Option
    raw_options = req.options
    if isinstance(raw_options, str):
        parts = [p.strip() for p in raw_options.replace("\n", ",").split(",") if p.strip()]
        options_list = [Option(id=p, description=p) for p in parts]
    elif isinstance(raw_options, list):
        options_list = []
        for o in raw_options:
            if isinstance(o, str):
                options_list.append(Option(id=o.strip(), description=o.strip()))
            elif isinstance(o, Option):
                options_list.append(o)
            elif isinstance(o, dict):
                options_list.append(Option(id=str(o.get("id", o.get("text", ""))), description=str(o.get("description", o.get("text", "")))))
            else:
                options_list.append(Option(id=str(o), description=str(o)))
    else:
        raise HTTPException(400, "options must be a list of strings, list of dicts, or comma-separated string")

    if not options_list:
        raise HTTPException(400, "options list must not be empty")

    # Single-option requests mapped to boolean primitive
    if len(options_list) == 1:
        opt = options_list[0]
        payload = {
            "state": state_str or criterion_str,
            "questions": [
                {
                    "id": "q1",
                    "type": "boolean",
                    "question": criterion_str,
                    "criteria": {
                        "true": opt.description or opt.id,
                        "false": f"Negative condition / reject {opt.id}"
                    }
                }
            ]
        }
    else:
        opts_descriptions = [o.description or o.id for o in options_list]
        payload = {
            "state": state_str,
            "questions": [
                {
                    "id": "q1",
                    "type": "choice",
                    "question": criterion_str,
                    "options": opts_descriptions
                }
            ]
        }

    r = urllib.request.Request(
        AGENT_JEV_UPSTREAM,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        raise HTTPException(e.code, f"AgentJev backend error: {err_msg}")
    except Exception as e:
        raise HTTPException(502, f"AgentJev upstream unreachable: {e}")

    ans = data["results"][0]["answers"][0]
    total = round(time.time() - t0, 4)
    forward_sec = round(data.get("usage", {}).get("wall_ms", total * 1000) / 1000.0, 4)

    if ans["type"] == "boolean":
        p_true = round(float(ans.get("probability", 0.5)), 4)
        opt = options_list[0]
        is_selected = bool(ans.get("value", True))
        conf = p_true if is_selected else round(1.0 - p_true, 4)
        abstained = conf < abstain_below
        return {
            "id": "dec-" + uuid.uuid4().hex[:8],
            "abstain": abstained,
            "top_choice": opt.id,
            "choice": opt.id if (is_selected and not abstained) else "abstain",
            "confidence": conf,
            "probabilities": {opt.id: p_true},
            "forward_seconds": forward_sec,
            "total_seconds": total,
            "model": "agent-jev-0.6b"
        }
    else:
        winner_idx = int(ans.get("value", 0))
        top_choice = options_list[winner_idx].id if winner_idx < len(options_list) else options_list[0].id
        dist = ans.get("distribution", {})
        probs = {}
        for k, v in dist.items():
            idx = int(k)
            if idx < len(options_list):
                probs[options_list[idx].id] = round(float(v), 4)
        conf = round(float(ans.get("top_probability", 0.0)), 4)
        abstained = conf < abstain_below
        return {
            "id": "dec-" + uuid.uuid4().hex[:8],
            "abstain": abstained,
            "top_choice": top_choice,
            "choice": "abstain" if abstained else top_choice,
            "confidence": conf,
            "probabilities": probs,
            "forward_seconds": forward_sec,
            "total_seconds": total,
            "model": "agent-jev-0.6b"
        }
