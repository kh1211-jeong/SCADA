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
        self.enabled = True                                         # 화면의 "에이전트 연결/해제"
        self.mode = 'direct' if os.environ.get('AGENT_MODE') == 'direct' else 'auto'   # auto | goclaw | direct
        self.stats = {'n': 0, 'fail': 0, 'last_sec': None, 'last_via': None}

    def status(self):
        g, l = _alive(f'{GOCLAW}/health'), _alive(f'{LITELLM}/health/liveliness')
        return {'enabled': self.enabled, 'mode': self.mode, 'backend': self.backend() if self.enabled else None,
                'goclaw': {'url': GOCLAW, 'alive': g, 'agent': 'scada-diag'},
                'litellm': {'url': LITELLM, 'alive': l, 'model': 'scada-gemini (gemini-flash-lite → 실패 시 gemini-3.5-flash)'},
                'stats': self.stats}

    def backend(self):
        if not self.enabled: return None
        if self.mode != 'direct' and _alive(f'{GOCLAW}/health'): return 'goclaw'
        if self.mode != 'goclaw' and _alive(f'{LITELLM}/health/liveliness'): return 'litellm'
        return None

    def explain(self, prompt, system):
        """도구 없이 한 번에 답하는 짧은 해설(이상 점수 실시간 해설용, 수 초). 데이터는 prompt에 담아 보낸다."""
        if not self.enabled: raise RuntimeError('에이전트 연결 해제 상태')
        hdr = {'Authorization': f"Bearer {self.ll.get('LITELLM_MASTER_KEY', '')}"}
        d = _post(f'{LITELLM}/v1/chat/completions', {'model': 'scada-gemini', 'temperature': 0.2, 'max_tokens': 400,
                  'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}]}, hdr, timeout=60)
        return d['choices'][0]['message']['content'] or ''

    def ask(self, text):
        if not self.enabled: raise RuntimeError('에이전트 연결이 해제되어 있습니다 — 상단 "에이전트"에서 연결하세요')
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
