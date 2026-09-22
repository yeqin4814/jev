"""Unified Gateway v2.3.0 for api.clinivisa.com
Serves:
- AgentJev Reflex Decision API (Primary):
    POST /api/evaluate
    GET  /api/info
    POST /v1/decide (via Decider Adapter :8765)
- Backward-Compatible Shim (Kev-9B Deprecated):
    POST /v1/systemone (dynamically translated & served by AgentJev)
- System 2 Generative Chat Reasoning (vLLM :11434):
    POST /v1/chat/completions
    POST /v1/completions
- Discovery & Health:
    GET  /
    GET  /v1/models
    GET  /health
"""
import os, json, time, httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

AGENT_JEV_BASE = os.environ.get('AGENT_JEV_BASE', 'http://127.0.0.1:8149')
DECIDER_BASE = os.environ.get('DECIDER_BASE', 'http://127.0.0.1:8765')
SYSTEM2_BASE = os.environ.get('SYSTEM2_BASE', 'http://127.0.0.1:11434')

app = FastAPI(
    title='Clinivisa Decision & Generation Gateway',
    version='2.3.0',
    description='Unified edge reverse proxy for api.clinivisa.com on DGX Blackwell'
)

limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
http_client = httpx.AsyncClient(limits=limits, timeout=60.0)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.get('/')
async def index():
    return {
        'service': 'Clinivisa Decision & Generation Gateway',
        'gateway_version': '2.3.0',
        'host': 'spark-15486 (NVIDIA DGX Blackwell GB10)',
        'endpoints': {
            'agentjev_evaluate': 'POST /api/evaluate (Native AgentJev typed evaluation: boolean, choice, score)',
            'agentjev_info': 'GET /api/info (Native AgentJev model metadata & capabilities)',
            'decide': 'POST /v1/decide (OpenJev-compatible decision API, powered by AgentJev)',
            'systemone': 'POST /v1/systemone (Backward-compatibility shim translated to AgentJev; kev-9b deprecated)',
            'chat_completions': 'POST /v1/chat/completions (System 2 Qwen 3.8 Flash Next on vLLM)',
            'models': 'GET /v1/models (List active and deprecated models)',
            'health': 'GET /health (Diagnostic health check)'
        },
        'active_backends': {
            'system1_reflex': {
                'model': 'AgentJev-0.6B (aimeigaoshou/agent-jev)',
                'port': 8149,
                'vram': '~2.45 GiB',
                'latency': '~45-130ms',
                'status': 'primary_active'
            },
            'system2_reasoning': {
                'model': 'Qwen 3.8 Flash Next NVFP4',
                'port': 11434,
                'max_model_len': 32768,
                'vram': '~79.7 GiB',
                'status': 'primary_active'
            }
        },
        'deprecated_backends': {
            'kev-9b': {
                'former_port': 8011,
                'status': 'deprecated_and_retired',
                'replacement': 'AgentJev-0.6B (:8149)'
            }
        }
    }

@app.get('/health')
@app.get('/v1/decide/health')
async def health():
    status = {
        'gateway': 'ok',
        'decider_adapter': 'unknown',
        'agent_jev': 'unknown',
        'system1_kev': 'deprecated',
        'system2_vllm': 'unknown'
    }

    try:
        r0 = await http_client.get(f'{DECIDER_BASE}/health', timeout=3.0)
        status['decider_adapter'] = 'ok' if r0.status_code == 200 else f'err_{r0.status_code}'
    except Exception as e:
        status['decider_adapter'] = f'down: {e}'

    try:
        r1 = await http_client.get(f'{AGENT_JEV_BASE}/api/info', timeout=3.0)
        status['agent_jev'] = 'ok' if r1.status_code == 200 else f'err_{r1.status_code}'
    except Exception as e:
        status['agent_jev'] = f'down: {e}'

    try:
        r3 = await http_client.get(f'{SYSTEM2_BASE}/v1/models', timeout=3.0)
        status['system2_vllm'] = 'ok' if r3.status_code == 200 else f'err_{r3.status_code}'
    except Exception as e:
        status['system2_vllm'] = f'down: {e}'

    all_ok = status['decider_adapter'] == 'ok' and status['agent_jev'] == 'ok'
    return JSONResponse(content=status, status_code=200 if all_ok else 503)

@app.post('/api/evaluate')
async def proxy_agentjev_eval(request: Request):
    body = await request.body()
    try:
        resp = await http_client.post(
            f'{AGENT_JEV_BASE}/api/evaluate',
            content=body,
            headers={'content-type': 'application/json'}
        )
        return Response(content=resp.content, status_code=resp.status_code, media_type='application/json')
    except Exception as e:
        return JSONResponse(status_code=502, content={'error': f'AgentJev proxy error: {str(e)}'})

@app.get('/api/info')
async def proxy_agentjev_info():
    try:
        resp = await http_client.get(f'{AGENT_JEV_BASE}/api/info')
        return Response(content=resp.content, status_code=resp.status_code, media_type='application/json')
    except Exception as e:
        return JSONResponse(status_code=502, content={'error': f'AgentJev info error: {str(e)}'})

@app.post('/v1/decide')
async def proxy_decide(request: Request):
    body = await request.body()
    try:
        resp = await http_client.post(
            f'{DECIDER_BASE}/v1/decide',
            content=body,
            headers={'content-type': 'application/json'}
        )
        return Response(content=resp.content, status_code=resp.status_code, media_type='application/json')
    except httpx.ConnectError:
        return JSONResponse(status_code=502, content={'error': 'Decider adapter unreachable on port 8765'})
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={'error': 'Decider adapter timed out'})
    except Exception as e:
        return JSONResponse(status_code=502, content={'error': f'Decider proxy error: {str(e)}'})

@app.post('/v1/systemone')
@app.post('/v1/systemone/{subpath:path}')
async def proxy_systemone(request: Request, subpath: str = ''):
    """Backward-compatibility bridge: converts legacy Kev-9B payloads to AgentJev format"""
    body = await request.body()
    try:
        data = json.loads(body)
    except Exception:
        return JSONResponse(status_code=400, content={'error': 'Invalid JSON body'})

    state = data.get('state', '')
    questions_in = data.get('questions', {})

    # If already native AgentJev questions list, forward directly
    if isinstance(questions_in, list):
        payload = data
    elif isinstance(questions_in, dict):
        # Convert Kev-9B questions dict to AgentJev list
        agent_questions = []
        for q_id, q_body in questions_in.items():
            q_type = q_body.get('type', 'choice')
            instructions = q_body.get('instructions', '')
            criteria = q_body.get('criteria', {})
            
            if q_type == 'boolean':
                agent_questions.append({
                    'id': q_id,
                    'type': 'boolean',
                    'question': instructions,
                    'criteria': criteria if isinstance(criteria, dict) else {'true': 'Yes', 'false': 'No'}
                })
            else:
                opts = list(criteria.values()) if isinstance(criteria, dict) else criteria
                agent_questions.append({
                    'id': q_id,
                    'type': 'choice',
                    'question': instructions,
                    'options': opts
                })
        payload = {'state': state, 'questions': agent_questions}
    else:
        payload = data

    t0 = time.time()
    try:
        resp = await http_client.post(
            f'{AGENT_JEV_BASE}/api/evaluate',
            json=payload,
            headers={'content-type': 'application/json'}
        )
        if resp.status_code != 200:
            return Response(content=resp.content, status_code=resp.status_code, media_type='application/json')
        
        jev_res = resp.json()
        total_ms = (time.time() - t0) * 1000.0

        # Translate back to Kev-9B format
        kev_answers = {}
        for r in jev_res.get('results', []):
            q_id = r.get('id', 'q1')
            answers = r.get('answers', [])
            if not answers:
                continue
            top_ans = answers[0]
            if r.get('type') == 'boolean':
                val = bool(top_ans.get('value', True))
                prob = top_ans.get('probability', 0.5)
                kev_answers[q_id] = {
                    'choice': 'true' if val else 'false',
                    'confidence': prob,
                    'probabilities': {'true': prob, 'false': round(1.0 - prob, 4)}
                }
            else:
                winner_idx = int(top_ans.get('value', 0))
                # Map back to original criteria keys if available
                orig_criteria = questions_in.get(q_id, {}).get('criteria', {})
                keys = list(orig_criteria.keys()) if isinstance(orig_criteria, dict) else []
                choice_key = keys[winner_idx] if winner_idx < len(keys) else str(winner_idx)
                
                dist = top_ans.get('distribution', {})
                prob_map = {}
                for k_idx_str, p_val in dist.items():
                    k_idx = int(k_idx_str)
                    k_name = keys[k_idx] if k_idx < len(keys) else str(k_idx)
                    prob_map[k_name] = round(float(p_val), 4)

                kev_answers[q_id] = {
                    'choice': choice_key,
                    'confidence': round(float(top_ans.get('top_probability', 0.0)), 4),
                    'probabilities': prob_map
                }

        out = {
            'answers': kev_answers,
            'latency_ms': round(total_ms, 2),
            'model': 'agent-jev-0.6b (serving legacy kev-9b endpoint)',
            'deprecated': True
        }
        return JSONResponse(
            content=out,
            status_code=200,
            headers={
                'X-Model-Deprecation': 'kev-9b is deprecated and retired on Blackwell; request was served by agent-jev-0.6b'
            }
        )
    except Exception as e:
        return JSONResponse(status_code=502, content={'error': f'Legacy System 1 shim error: {str(e)}'})

@app.post('/v1/chat/completions')
@app.post('/v1/completions')
async def proxy_system2_generation(request: Request):
    path = request.url.path
    body = await request.body()
    target_url = f'{SYSTEM2_BASE}{path}'

    try:
        data = json.loads(body) if body else {}
    except Exception:
        data = {}

    is_stream = bool(data.get('stream', False))

    if is_stream:
        async def stream_generator():
            req = http_client.build_request('POST', target_url, content=body, headers={'content-type': 'application/json'})
            r = await http_client.send(req, stream=True)
            async for chunk in r.aiter_raw():
                yield chunk

        return StreamingResponse(stream_generator(), media_type='text/event-stream')
    else:
        try:
            resp = await http_client.post(
                target_url,
                content=body,
                headers={'content-type': 'application/json'}
            )
            return Response(content=resp.content, status_code=resp.status_code, media_type='application/json')
        except Exception as e:
            return JSONResponse(status_code=502, content={'error': f'System 2 proxy error: {str(e)}'})

@app.get('/v1/models')
async def proxy_models():
    models_list = [
        {
            'id': 'agent-jev-latest',
            'object': 'model',
            'type': 'reflex_engine',
            'lane': 'system1',
            'base': 'Qwen/Qwen3-0.6B',
            'precision': 'bfloat16',
            'status': 'primary'
        },
        {
            'id': 'agent-jev-0.6b',
            'object': 'model',
            'type': 'reflex_engine',
            'lane': 'system1',
            'base': 'Qwen/Qwen3-0.6B',
            'precision': 'bfloat16',
            'status': 'primary'
        },
        {
            'id': 'kev-9b',
            'object': 'model',
            'type': 'decision_engine',
            'lane': 'system1',
            'base': 'Qwen/Qwen3.5-9B-Base',
            'status': 'deprecated',
            'deprecation_reason': 'Replaced by AgentJev-0.6B for 67% lower latency and 14 GiB memory savings'
        }
    ]

    try:
        r2 = await http_client.get(f'{SYSTEM2_BASE}/v1/models', timeout=2.0)
        if r2.status_code == 200:
            s2_data = r2.json()
            for m in s2_data.get('data', []):
                models_list.append({
                    'id': m.get('id'),
                    'object': 'model',
                    'type': 'generative_engine',
                    'lane': 'system2',
                    'owned_by': m.get('owned_by', 'vllm')
                })
    except Exception:
        pass

    return {
        'object': 'list',
        'data': models_list,
        'models': models_list
    }
