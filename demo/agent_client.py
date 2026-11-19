# -*- coding: utf-8 -*-
"""진단 에이전트 호출: 기본은 goclaw 게이트웨이(:18790, 에이전트 scada-diag → LiteLLM → Gemini, 도구는 MCP :8766).
goclaw가 꺼져 있으면 LiteLLM(:4000)에 직접 붙어 같은 도구로 도구 호출 루프를 돈다(예비 경로).
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

GOCLAW = os.environ.get('GOCLAW_URL', 'http://127.0.0.1:18790')
LITELLM = os.environ.get('LITELLM_URL', 'http://127.0.0.1:4000')
AGENT_DIR = Path(os.environ.get('AGENT_DIR', Path.home() / 'agents'))


def _env(path):
    d = {}
    try:
        for line in open(path):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1); d[k] = v.strip().strip('"')
    except FileNotFoundError:
        pass
    return d


def _post(url, body, headers, timeout=180):
    req = urllib.request.Request(url, json.dumps(body).encode(), {'Content-Type': 'application/json', **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _alive(url):
    try:
        urllib.request.urlopen(url, timeout=2); return True
    except Exception:
        return False


SYSTEM = (Path(__file__).with_name('AGENTS.md')).read_text(encoding='utf-8') if Path(__file__).with_name('AGENTS.md').exists() else ''


class AgentClient:
    def __init__(self, tools):
        self.tools = tools
        self.gc = _env(AGENT_DIR / 'goclaw-scada' / '.env')
        self.ll = _env(AGENT_DIR / 'litellm' / '.env')

    def backend(self):
        if os.environ.get('AGENT_MODE') != 'direct' and _alive(f'{GOCLAW}/health'): return 'goclaw'
        if _alive(f'{LITELLM}/health/liveliness'): return 'litellm'
        return None

    def ask(self, text):
        b = self.backend()
        if b == 'goclaw':
            try:
                d = _post(f'{GOCLAW}/v1/chat/completions', {'model': 'goclaw:scada-diag', 'messages': [{'role': 'user', 'content': text}]},
                          {'Authorization': f"Bearer {self.gc.get('GOCLAW_GATEWAY_TOKEN', '')}", 'X-GoClaw-User-Id': 'operator'})
                ans = d['choices'][0]['message']['content'] if 'choices' in d else ''
                if ans and "couldn't generate" not in ans and 'Agent error' not in ans:
                    return ans, 'goclaw'
            except Exception:
                pass
            if _alive(f'{LITELLM}/health/liveliness'):      # goclaw 실패(언어 모델 과부하 등) → 예비 경로로 1회 재시도
                return self._direct(text), 'goclaw 실패 → 직접 호출'
        if b == 'litellm':
            return self._direct(text), 'litellm(직접)'
        raise RuntimeError('goclaw(:18790)와 LiteLLM(:4000)이 모두 꺼져 있음 — zsh ~/agents/goclaw-scada/start.sh 로 기동')

    # 예비 경로: LiteLLM 직접 + 도구 호출 루프 ------------------------------------------------
    def _schemas(self):
        import inspect
        from demo.tools import TOOL_NAMES
        out = []
        for n in TOOL_NAMES:
            fn = getattr(self.tools, n)
            props, req = {}, []
            for p in inspect.signature(fn).parameters.values():
                props[p.name] = {'type': 'integer' if p.annotation in (int, 'int') else 'string'}
                if p.default is inspect._empty: req.append(p.name)
            out.append({'type': 'function', 'function': {'name': 'scada_' + n, 'description': fn.__doc__,
                                                         'parameters': {'type': 'object', 'properties': props, 'required': req}}})
        return out

    def _direct(self, text, max_iter=10):
        msgs = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': text}]
        hdr = {'Authorization': f"Bearer {self.ll.get('LITELLM_MASTER_KEY', '')}"}
        for _ in range(max_iter):
            d = _post(f'{LITELLM}/v1/chat/completions', {'model': 'scada-gemini', 'messages': msgs, 'tools': self._schemas(),
                                                         'temperature': 0.2}, hdr)
            m = d['choices'][0]['message']
            msgs.append({k: v for k, v in m.items() if v is not None})
            if not m.get('tool_calls'):
                return m.get('content') or ''
            for tc in m['tool_calls']:
                fn = tc['function']['name'].removeprefix('scada_').removeprefix('_')
                try:
                    res = getattr(self.tools, fn)(**json.loads(tc['function']['arguments'] or '{}'))
                except Exception as e:
                    res = {'error': str(e)}
                msgs.append({'role': 'tool', 'tool_call_id': tc['id'], 'content': json.dumps(res, ensure_ascii=False, default=str)})
        return '도구 호출 한도를 넘었습니다. 질문을 좁혀 주세요.'
