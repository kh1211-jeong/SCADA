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

from demo import auth
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
    if kind == 'warn':
        say('system', obj['text']); return
    if not auto_diag['on'] or not agent.enabled: return
    if kind == 'alarm':
        say('system', f"경보 {obj['id']} · {', '.join(obj['top_nodes'])}")
        jobs.put((f"[자동 진단 요청] 모의 시각 {eng.tstr()}에 이상 경보 {obj['id']}가 발생했다(기여 상위 설비: {', '.join(obj['top_nodes'])}). "
                  f"원인과 위치를 진단해 줘.", 0))
    elif kind == 'switch':
        say('system', f"{obj['node']} {obj['action']}" + (f" · {obj['cause']}" if obj.get('cause') else ''))
        jobs.put((f"[자동 진단 요청] 모의 시각 {obj['time']}에 {obj['node']}({TYPE_KO.get(obj['etype'], obj['etype'])})가 "
                  f"{obj['action']}되었다(조작 주체: {obj['by']}{', 원인: ' + obj['cause'] if obj.get('cause') else ''}). 정전·영향 범위와 이상 여부를 진단해 줘.", 3))


eng.listeners.append(on_event)


def worker():
    while True:
        text, delay_min = jobs.get()
        if delay_min:
            target = eng.minute + delay_min
            while eng.minute < target: time.sleep(0.2)
        if not agent.enabled: continue          # 대기 중 연결이 해제되면 버림
        pend = {'id': len(chat), 'role': 'agent', 'text': '진단 중…', 'time': eng.tstr(), 'pending': True}
        chat.append(pend)
        t0 = time.time()
        try:
            ans, via = agent.ask(text)
            pend.update(text=ans, pending=False, via=via, sec=round(time.time() - t0, 1))
            agent.stats.update(n=agent.stats['n'] + 1, last_sec=pend['sec'], last_via=via)
        except Exception as e:
            pend.update(text=f'에이전트 호출 실패: {e}', pending=False, error=True)
            agent.stats['fail'] += 1


# ---------------------------------------------------------------- 이상 점수 실시간 해설
narr = {'on': False, 'items': [], 'busy': False, 'last': 0.0, 'last_state': None}
NARR_SYS = ('너는 수배전 계통 이상 탐지 화면의 해설자다. 주어진 이상 점수 데이터만 근거로 한국어 존댓말로 2~3문장, 짧게 설명한다. '
            '이상 점수 = 가장 이상한 센서 5개가 평소보다 몇 배 예측을 빗나가는지(6분 평균). 기준선은 정상 운전의 상위 1% 값이며 3분 넘게 넘으면 경보. '
            '평상시 점수는 대략 10 이하. 지금 수준(정상/상승 중/경보), 추세, 점수를 끌어올리는 설비와 그 이유(개폐 조작 직후인지, 주입된 이상인지 모름)를 말한다. '
            '데이터에 없는 원인을 지어내지 말고, 차단기 조작 지시는 하지 않는다. 이모지 금지.')


def _score_summary(minutes=30):
    with eng.lock:
        sc = list(eng.scores)[-minutes:]; th = list(eng.top_hist)[-minutes:]
        ops = [o for o in eng.ops[-5:]]
        act = [eng.alarm_view(a) for a in eng.alarms if a['end'] is None and a['minutes'] >= 1]
    if not sc: return None
    v = [s for _, s, _ in sc]
    cnt = {}
    for _, tops in th:
        for n, z in tops: cnt[n] = max(cnt.get(n, 0), z)
    top = sorted(cnt.items(), key=lambda kv: -kv[1])[:5]
    return {'모의_시각': eng.tstr(), '현재_점수': round(v[-1], 1), '기준선': round(eng.thr, 1),
            f'최근_{len(v)}분': {'최소': round(min(v), 1), '최대': round(max(v), 1), '10분_전': round(v[-11], 1) if len(v) > 10 else None},
            '현재_상위_기여_설비': [(f['node'], f['kind'], f['score']) for f in eng.top_now[:5]],
            '구간_최대_기여_설비': [(n, round(z, 1)) for n, z in top],
            '진행_중_경보': [{k: a[k] for k in ('id', 'start', 'minutes', 'peak_score', 'top_nodes')} for a in act],
            '최근_개폐': [(o['time'][11:], o['node'], o['action'], o.get('cause', '')) for o in ops]}


def narrator():
    """해설 켜짐 동안: 상태가 바뀌면 바로, 아니면 실제 30초마다 한 번 짧은 해설을 만든다(도구 없이 데이터만 보내 수 초 응답)."""
    while True:
        time.sleep(1)
        if not narr['on'] or narr['busy'] or not agent.enabled or not eng.scores: continue
        s = eng.scores[-1][1]
        state = 'alarm' if s > eng.thr else 'rise' if s > 30 else 'normal'
        if state == narr['last_state'] and time.time() - narr['last'] < 30: continue
        d = _score_summary()
        if d is None: continue
        narr['busy'] = True
        try:
            t0 = time.time()
            txt = agent.explain('다음은 지금의 이상 점수 데이터다. 해설해 줘.\n' + json.dumps(d, ensure_ascii=False), NARR_SYS)
            narr['items'].append({'time': d['모의_시각'][11:], 'score': d['현재_점수'], 'text': txt.strip(), 'sec': round(time.time() - t0, 1)})
            narr['items'] = narr['items'][-30:]
        except Exception as e:
            narr['items'].append({'time': eng.tstr()[11:], 'score': None, 'text': f'해설 실패: {e}', 'err': True})
        finally:
            narr['busy'] = False; narr['last'] = time.time(); narr['last_state'] = state


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
    return JSONResponse(eng.switch(b['node'], bool(b['closed']), trip=bool(b.get('trip')), force_parallel=bool(b.get('force_parallel'))))


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
    if not agent.enabled:
        say('system', '진단 에이전트 연결이 해제되어 있습니다 — 상단 "에이전트"에서 연결하세요')
        return JSONResponse({'ok': False, 'error': 'agent disabled'})
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
        now = eng.energized(); imp = eng.impact(node, closed)
        lost, gain, kw = imp['lost'], imp['gained'], imp['lost_kw']
        warn = []
        if imp['parallel']:
            warn.append(f"병렬 운전 금지 인터록 — 양쪽이 이미 가압 중({', '.join(imp['parallel'])}). 먼저 한쪽 주 차단기를 개방하세요")
        for b in imp['backup']:
            if b['예상_%'] > 100: warn.append(f"백업 과부하 — {b['변압기']} 예상 부하율 {b['예상_%']:.0f}% (현재 {b['현재_%']:.0f}%), 과부하 보호로 트립될 수 있습니다")
        if not closed and p.etype[node] == 'DIS' and abs(eng.last.get(f'{node}_CURRENT', 0) or 0) > 1:
            warn.append('단로기에 부하 전류가 흐르는 중 — 개방 시 아크 위험')
        if not closed and p.etype[node] in ('GCB', 'MAIN') : warn.append('주 계통 차단기 — 넓은 범위 정전')
        return JSONResponse({'lost': lost, 'gained': gain, 'lost_kw': round(kw, 1),
                             'n_load_lost': imp['n_load_lost'], 'warnings': warn, 'parallel': bool(imp['parallel']), 'backup': imp['backup']})


async def trend(req: Request):
    node = req.query_params['node']; minutes = int(req.query_params.get('minutes', 120))
    F = eng.frame(minutes)
    q = tools.node_tags.get(node, {})
    out = {k: [_num(x, 2) for x in F[t].values] for k, t in q.items() if t in F}
    return JSONResponse({'t': [x.strftime('%H:%M') for x in F.index], 'series': out})


async def agent_status(req: Request):
    """에이전트 연결 정보(GET) / 연결·해제·경로 변경(POST {enabled, mode})."""
    if req.method == 'POST':
        b = await req.json()
        if 'enabled' in b:
            agent.enabled = bool(b['enabled']); say('system', '진단 에이전트 연결' if agent.enabled else '진단 에이전트 연결 해제')
        if b.get('mode') in ('auto', 'goclaw', 'direct'): agent.mode = b['mode']
    from demo.tools import TOOL_NAMES
    m = getattr(eng, 'model_info', None)
    return JSONResponse({**agent.status(), 'tools': TOOL_NAMES, 'auto_diag': auto_diag['on'],
                         'model': {'name': m['name'], 'size_kb': round(m['size_kb']), 'latency_ms': round(m['latency_ms'], 2), 'threshold': round(eng.thr, 2)} if m else None})


async def score(req: Request):
    """이상 점수 추이(최근 N분): 점수, 기준선, 분마다 상위 기여 설비, 경보 구간, 개폐 시각, 실시간 해설."""
    minutes = int(req.query_params.get('minutes', 180))
    with eng.lock:
        sc = list(eng.scores)[-minutes:]; th = {t: tops for t, tops in list(eng.top_hist)[-minutes:]}
        t0 = sc[0][0] if sc else None
        al = [{'id': a['id'], 'start': a['start'][11:], 'end': (a['end'] or '')[11:]} for a in eng.alarms if a['minutes'] >= 3 and t0 is not None and a['start'] >= t0.strftime('%Y-%m-%d %H:%M')]
        ops = [{'t': o['time'][11:], 'node': o['node'], 'action': o['action']} for o in eng.ops if t0 is not None and o['time'] >= t0.strftime('%Y-%m-%d %H:%M')]
    v = [s for _, s, _ in sc]
    base = v[30:] if len(v) > 90 else v                      # 서버 시작 직후 30분은 모델 창이 차오르는 과도 구간이라 정상 범위 계산에서 뺀다
    norm = sorted(x for x in base if x < eng.thr)
    band = [round(norm[int(len(norm) * .05)], 1), round(norm[int(len(norm) * .95) - 1], 1)] if len(norm) > 20 else None
    return JSONResponse({'t': [t.strftime('%H:%M') for t, _, _ in sc], 'v': [round(x, 2) for x in v], 'thr': round(eng.thr, 2),
                         'top': [[n for n, _ in th.get(t, [])] for t, _, _ in sc], 'band': band, 'alarms': al, 'ops': ops,
                         'top_now': eng.top_now[:5], 'narr': {'on': narr['on'], 'busy': narr['busy'], 'items': narr['items'][-12:]}})


async def narrate(req: Request):
    b = await req.json(); narr['on'] = bool(b.get('on')); narr['last_state'] = None
    return JSONResponse({'on': narr['on']})


async def me(req: Request):
    return JSONResponse({'role': getattr(req.state, 'role', 'admin'), 'auth': auth.ENABLED})


app = Starlette(routes=[Route('/login', auth.login, methods=['GET', 'POST']), Route('/logout', auth.logout), Route('/api/me', me), Route('/', index), Route('/api/meta', meta), Route('/api/state', state), Route('/api/switch', do_switch, methods=['POST']), Route('/api/inject', do_inject, methods=['POST']),
                        Route('/api/control', control, methods=['POST']), Route('/api/ask', ask, methods=['POST']),
                        Route('/api/agent', agent_status, methods=['GET', 'POST']), Route('/api/score', score), Route('/api/narrate', narrate, methods=['POST']),
                        Route('/api/preview', preview), Route('/api/trend', trend), Mount('/static', StaticFiles(directory=STATIC))])


app.add_middleware(auth.AuthMiddleware)


def main():
    if os.environ.get('SCADA_HOST', '127.0.0.1') != '127.0.0.1' and not auth.ENABLED:
        print('[auth] 경고: 외부 공개 주소인데 로그인 비밀번호 파일이 없습니다 —', auth.AUTH_FILE)
    eng.warmup(int(os.environ.get('WARMUP', 40)))
    threading.Thread(target=eng.run, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=narrator, daemon=True).start()
    mcp_app = build_mcp(tools).streamable_http_app(host='127.0.0.1')
    threading.Thread(target=lambda: uvicorn.run(mcp_app, host='127.0.0.1', port=8766, log_level='warning'), daemon=True).start()
    uvicorn.run(app, host=os.environ.get('SCADA_HOST', '127.0.0.1'), port=int(os.environ.get('PORT', 8765)), log_level='warning')


if __name__ == '__main__':
    main()
