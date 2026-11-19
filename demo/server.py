# -*- coding: utf-8 -*-
"""수배전 이상탐지·진단 데모 서버.

  웹 화면   http://127.0.0.1:8765      계통도(6개 계통) + 실시간 값 + 차단기 조작/이벤트 주입 + 진단 채팅
  MCP 도구  http://127.0.0.1:8766/mcp  goclaw 에이전트가 붙는 실시간 조회 도구(읽기 전용)

실행: cd ~/SCADA && .venv/bin/python -m demo.server   (먼저 zsh ~/agents/goclaw-scada/start.sh)
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

import numpy as np
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from demo.agent_client import AgentClient
from demo.engine import EVENT_TYPES, Engine
from demo.tools import TYPE_KO, Tools, build_mcp

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).with_name('static')
sys.path.insert(0, str(ROOT / 'scripts' / 'winccoa' / 'web'))
from layout import compute_layout  # noqa: E402  (EGMS sld_renderer 레이아웃 알고리즘의 파이썬 포팅)

LEVEL = {"BUS": 0, "GCB": 1, "BTR": 2, "MAIN": 3, "VCB_K": 4, "VCB_Q": 5, "VCB_FEEDER": 6, "VCB_STR": 6, "VCB_CAP": 6,
         "LTR": 7, "ACB": 8, "ACB_MAIN_EMG": 8, "STR": 8, "VCS_CAP": 8, "XCB": 9, "RETURN": 9}

eng = Engine()
tools = Tools(eng)
agent = AgentClient(tools)
chat: list[dict] = []
jobs: queue.Queue = queue.Queue()
auto_diag = {'on': True}


def say(role, text, **kw):
    chat.append({'id': len(chat), 'role': role, 'text': text, 'time': eng.tstr(), **kw})


# ---------------------------------------------------------------- 계통도 레이아웃
def tie_level(name):
    import re
    tail = re.sub(r"^(TIE|DIS)_3[FU]\d{2}", "", name)
    return 8 if re.search(r"\d$", tail) and len(re.findall(r"[A-Z]", tail)) >= 2 else 3


def diagrams():
    N, E = eng.nodes, eng.edges
    out = {}
    for s in sorted(x for x in N.system.dropna().unique()):
        ids = set(N.index[N.system == s]) | {'BUS_154kV'}
        ids |= {n for n in N.index[N.system.isna()] if n.startswith('TIE_') and any(m in ids for m in eng.adj.get(n, ()))}
        nodes = []
        for n in ids:
            t = N.at[n, 'etype']
            lv = tie_level(n) if t in ('TIE', 'DIS') else LEVEL.get(t, 9)
            nodes.append({'id': n, 'etype': t, 'level': lv})
        edges = [dict(src=a, dst=b, etype=t) for a, b, t in zip(E.src, E.dst, E.etype) if a in ids and b in ids]
        pos = compute_layout(nodes, edges)
        # 계통 간 연계 차단기: 레이아웃이 주 차단기와 같은 자리에 겹쳐 놓으므로 바깥쪽으로 빼고 상대 계통을 붙인다
        mains = [pos[n][0] for n in ids if N.at[n, 'etype'] == 'MAIN']
        ext = {}
        for n in ids:
            if n.startswith('TIE_') and not isinstance(N.at[n, 'system'], str):
                inside = [m for m in eng.adj.get(n, ()) if m in ids]
                other = [N.at[m, 'system'] for m in eng.adj.get(n, ()) if m not in ids and isinstance(N.at[m, 'system'], str)]
                if inside:
                    mx, my = pos[inside[0]]
                    side = 1 if mx >= max(mains) else -1
                    pos[n] = (mx + side * 120, my)
                    ext[n] = (other[0] if other else '', side)
        xs = [p[0] for p in pos.values()]
        x0 = min(xs)
        for nd in nodes:
            x, y = pos[nd['id']]
            y = y * 0.6 + (75 if nd['etype'] in ('TIE', 'DIS') and nd['level'] == 8 else 0)   # 세로 압축, 저압 연계는 한 칸 아래
            nd.update(x=round(x - x0 + 110, 1), y=round(y + 50, 1), type_ko=TYPE_KO.get(nd['etype'], nd['etype']),
                      switch=nd['id'] in eng.plant.sw_idx)
            if nd['id'] in ext: nd['ext'], nd['side'] = ext[nd['id']]
        out[s] = {'nodes': nodes, 'edges': edges}
    return out


DIAG = diagrams()


def targets_for(kind):
    N = eng.nodes
    analog = set(eng.tags.NODE[eng.tags.QUANTITY == 'POWER'])
    return {'analog': sorted(analog), 'acb': sorted(n for n in analog if N.at[n, 'etype'] == 'ACB'),
            'feeder': sorted(n for n in analog if N.at[n, 'etype'] == 'VCB_FEEDER'),
            'ltr': sorted(N.index[N.etype == 'LTR']), 'btr': sorted(N.index[N.etype == 'BTR']), 'bus': ['BUS_154kV']}[kind]


# ---------------------------------------------------------------- 자동 진단
def on_event(kind, obj):
    if not auto_diag['on']: return
    if kind == 'alarm':
        say('system', f"경보 {obj['id']} · {', '.join(obj['top_nodes'])}")
        jobs.put((f"[자동 진단 요청] 모의 시각 {eng.tstr()}에 이상 경보 {obj['id']}가 발생했다(기여 상위 설비: {', '.join(obj['top_nodes'])}). "
                  f"원인과 위치를 진단해 줘.", 0))
    elif kind == 'switch':
        say('system', f"{obj['node']} {obj['action']}")
        jobs.put((f"[자동 진단 요청] 모의 시각 {obj['time']}에 {obj['node']}({TYPE_KO.get(obj['etype'], obj['etype'])})가 "
                  f"{obj['action']}되었다(조작 주체: {obj['by']}). 정전·영향 범위와 이상 여부를 진단해 줘.", 3))


eng.listeners.append(on_event)


def worker():
    while True:
        text, delay_min = jobs.get()
        if delay_min:
            target = eng.minute + delay_min
            while eng.minute < target: time.sleep(0.2)
        pend = {'id': len(chat), 'role': 'agent', 'text': '진단 중…', 'time': eng.tstr(), 'pending': True}
        chat.append(pend)
        t0 = time.time()
        try:
            ans, via = agent.ask(text)
            pend.update(text=ans, pending=False, via=via, sec=round(time.time() - t0, 1))
        except Exception as e:
            pend.update(text=f'에이전트 호출 실패: {e}', pending=False, error=True)


# ---------------------------------------------------------------- API
async def index(_): return FileResponse(STATIC / 'index.html')


async def meta(_):
    info = getattr(eng, 'model_info', None)
    sysmap = {nd['id']: k for k, d in DIAG.items() for nd in d['nodes'] if nd['id'] != 'BUS_154kV'}
    return JSONResponse({'systems': list(DIAG), 'diagrams': DIAG, 'node_system': sysmap,
                         'event_types': {k: {**v, 'targets': targets_for(v['targets'])} for k, v in EVENT_TYPES.items()},
                         'model': None if info is None else {k: info[k] for k in ('name', 'params', 'size_kb', 'latency_ms', 'hid', 'k_max', 'int8', 'thr', 'teacher')
                                                             if k in info}})


def _num(x, n=1):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


async def state(req: Request):
    s = req.query_params.get('system', '3F11')
    with eng.lock:
        last = eng.last
        en = eng.energized()
        tf = eng.tie_fed()
        vals = {}
        for nd in DIAG.get(s, {'nodes': []})['nodes']:
            n = nd['id']; q = tools.node_tags.get(n, {})
            v = {k: _num(last.get(t), 2 if k == 'PF' else 1) for k, t in q.items() if k != 'STATUS'}
            if n in eng.plant.sw_idx: v['closed'] = int(eng.sim.state[eng.plant.sw_idx[n]])
            v['on'] = n in en
            if n in tf and tf[n]: v['via'] = tf[n]       # 연계 공급원(변압기)
            vals[n] = v
        scores = [(t.strftime('%H:%M'), round(sc, 2)) for t, sc, _ in list(eng.scores)[-180:]]
        act = [eng.alarm_view(a) for a in eng.alarms if a['end'] is None and a['minutes'] >= 1]
        hot = {}
        for a in act:
            for f in a['top_features'][:5]: hot[f['node']] = max(hot.get(f['node'], 0), f['score'])
        alarms = [eng.alarm_view(a) for a in eng.alarms if a['minutes'] >= 3][::-1][:20]
        off = eng.off_normal()
        sys_off = {x: sum(1 for n in off if eng.nodes.at[n, 'system'] == x) for x in DIAG}
        sys_hot = {x: sum(1 for n in hot if n in eng.nodes.index and eng.nodes.at[n, 'system'] == x) for x in DIAG}
        return JSONResponse({'time': eng.tstr(), 'speed': eng.speed, 'paused': eng.paused, 'values': vals,
                             'score': scores[-1][1] if scores else None, 'thr': _num(getattr(eng, 'thr', None), 2),
                             'scores': scores, 'hot': hot, 'alarms': alarms, 'ops': eng.ops[-30:][::-1],
                             'injected': eng.injected[-30:][::-1], 'sys_off': sys_off, 'sys_hot': sys_hot,
                             'chat': chat[-60:],
                             'auto': auto_diag['on'], 'top_now': eng.top_now[:5]})


async def do_switch(req: Request):
    b = await req.json()
    return JSONResponse(eng.switch(b['node'], bool(b['closed']), trip=bool(b.get('trip'))))


async def do_inject(req: Request):
    b = await req.json()
    r = eng.inject(b['type'], b['target'], b.get('minutes'))
    if r.get('ok'): say('system', f"이벤트 주입 {r['event']['id']}")
    return JSONResponse(r)


async def control(req: Request):
    b = await req.json()
    if 'speed' in b: eng.speed = float(b['speed'])
    if 'paused' in b: eng.paused = bool(b['paused'])
    if 'auto' in b: auto_diag['on'] = bool(b['auto'])
    if b.get('reset'): eng.reset_events(); say('system', '평상 복귀')
    return JSONResponse({'speed': eng.speed, 'paused': eng.paused, 'auto': auto_diag['on']})


async def ask(req: Request):
    b = await req.json()
    text = b.get('text', '').strip()
    if not text: return JSONResponse({'error': 'empty'})
    say('user', text)
    recent = [m for m in chat[-8:-1] if m['role'] in ('user', 'agent') and not m.get('pending')][-4:]
    ctx = '\n'.join(f"[{'운영자' if m['role'] == 'user' else '에이전트'}] {m['text'][:400]}" for m in recent)
    jobs.put(((f'(이전 대화)\n{ctx}\n\n' if ctx else '') + f'[운영자 질문, 모의 시각 {eng.tstr()}] {text}', 0))
    return JSONResponse({'ok': True})


async def preview(req: Request):
    """조작 전 영향 미리보기: 정전·가압될 설비, 상실 부하(kW), 인터록 경고."""
    node = req.query_params['node']; closed = int(req.query_params['closed'])
    with eng.lock:
        p = eng.plant
        if node not in p.sw_idx: return JSONResponse({'error': '개폐 설비 아님'})
        st = eng.sim.state.copy(); now = set(eng.sim._topology(st)[0])
        st2 = st.copy(); st2[p.sw_idx[node]] = closed
        after = set(eng.sim._topology(st2)[0])
        lost, gain = sorted(now - after), sorted(after - now)
        kw = sum(abs(eng.last.get(f'{n}_POWER', 0) or 0) for n in lost if p.etype[n] in ('ACB', 'ACB_MAIN_EMG'))
        warn = []
        if closed and p.etype[node] in ('TIE', 'XCB', 'DIS'):
            nb = [m for m in eng.adj.get(node, ()) if m in now]
            if len(nb) >= 2: warn.append('양쪽이 모두 가압 상태 — 병렬(루프) 운전이 됩니다')
        if not closed and p.etype[node] in ('GCB', 'MAIN') : warn.append('주 계통 차단기 — 넓은 범위 정전')
        return JSONResponse({'lost': lost, 'gained': gain, 'lost_kw': round(kw, 1),
                             'n_load_lost': sum(1 for n in lost if p.etype[n] in ('ACB', 'ACB_MAIN_EMG')), 'warnings': warn})


async def trend(req: Request):
    node = req.query_params['node']; minutes = int(req.query_params.get('minutes', 120))
    F = eng.frame(minutes)
    q = tools.node_tags.get(node, {})
    out = {k: [_num(x, 2) for x in F[t].values] for k, t in q.items() if t in F}
    return JSONResponse({'t': [x.strftime('%H:%M') for x in F.index], 'series': out})


async def agent_status(_):
    return JSONResponse({'backend': agent.backend()})


app = Starlette(routes=[Route('/', index), Route('/api/meta', meta), Route('/api/state', state), Route('/api/switch', do_switch, methods=['POST']), Route('/api/inject', do_inject, methods=['POST']),
                        Route('/api/control', control, methods=['POST']), Route('/api/ask', ask, methods=['POST']),
                        Route('/api/agent', agent_status), Route('/api/preview', preview), Route('/api/trend', trend), Mount('/static', StaticFiles(directory=STATIC))])


def main():
    eng.warmup(int(os.environ.get('WARMUP', 40)))
    threading.Thread(target=eng.run, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    mcp_app = build_mcp(tools).streamable_http_app(host='127.0.0.1')
    threading.Thread(target=lambda: uvicorn.run(mcp_app, host='127.0.0.1', port=8766, log_level='warning'), daemon=True).start()
    uvicorn.run(app, host=os.environ.get('SCADA_HOST', '127.0.0.1'), port=int(os.environ.get('PORT', 8765)), log_level='warning')


if __name__ == '__main__':
    main()
