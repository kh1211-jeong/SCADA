# -*- coding: utf-8 -*-
"""SCADA 진단 MCP 서버 (stdio): goclaw 에이전트가 호출하는 조회 도구. 읽기 전용, 설비 제어 기능 없음.

데이터: results/agent/store.json(경보·기여 피처, src.agent.build_store로 생성) + FMCS 트렌드 + 계통 토폴로지.
실행: FMCS_DATA=fmcs_synth_v2 .venv/bin/python -m src.agent.scada_mcp   (goclaw config.json의 tools.mcp_servers에서 기동)
"""
import json
import os
os.environ.setdefault('FMCS_DATA', 'fmcs_synth_v2')
from functools import lru_cache
from pathlib import Path
import numpy as np
import pandas as pd
from mcp.server import MCPServer
from src.data import fmcs

STORE = Path(__file__).resolve().parents[2] / 'results' / 'agent' / 'store.json'
mcp = MCPServer('scada-diag', instructions='154kV~220V 수배전 SCADA(FMCS) 이상 경보를 조회·진단하는 읽기 전용 도구. 시각은 "YYYY-MM-DD HH:MM".')


@lru_cache(None)
def store(): return json.load(open(STORE))
@lru_cache(None)
def tags(): return fmcs.tag_table()
@lru_cache(None)
def wide(): return fmcs.load_wide().ffill()
@lru_cache(None)
def nodes(): return pd.read_csv(fmcs.ROOT / 'topology_nodes.csv').set_index('node')
@lru_cache(None)
def edges():
    e = pd.read_csv(fmcs.ROOT / 'topology_edges.csv')
    return e[e.etype == 'power']


def _t(s): return pd.Timestamp(s)
def _r(x, n=3): return None if pd.isna(x) else round(float(x), n)
def _node_tags(node):
    g = tags()[tags().NODE == node]
    return dict(zip(g.QUANTITY, g.EQP_NAME)), dict(zip(g.QUANTITY, g.UNIT))


@mcp.tool(description='탐지된 이상 경보 목록(시간순). 각 경보의 id, 시작·종료, 지속(분), 최대 점수, 기여 상위 설비 3개를 준다.')
def list_alarms(limit: int = 50) -> dict:
    s = store()
    return {'model': s['model'], 'period': s['period'], 'threshold': s['threshold'], 'n_alarms': s['n_alarms'],
            'alarms': [{k: a[k] for k in ('id', 'start', 'end', 'minutes', 'peak_score', 'top_nodes')} for a in s['alarms'][:limit]]}


@mcp.tool(description='경보 하나의 상세: 기여 상위 피처 10개(피처명, 설비, 종류=태그/물리 잔차/KCL 잔차, 정규화 오차 점수).')
def get_alarm(alarm_id: str) -> dict:
    for a in store()['alarms']:
        if a['id'] == alarm_id.upper(): return a
    return {'error': f'{alarm_id} 없음. list_alarms로 id 확인'}


@mcp.tool(description='설비의 계통 위치: 상위 경로(154kV 모선까지), 바로 아래 설비, 형제 설비(같은 상위). 설비 종류·정격·평상 개폐 상태 포함.')
def get_topology(node: str) -> dict:
    N, E = nodes(), edges()
    if node not in N.index: return {'error': f'{node} 없음. find_equipment로 검색'}
    info = lambda n: {'node': n, 'type': N.at[n, 'etype'], 'normal_closed': _r(N.at[n, 'normal_closed'], 0),
                      'rating_kva': _r(N.at[n, 'rating_kva'], 0)} if n in N.index else {'node': n}
    up, cur = [], node
    while True:
        p = E[E.dst == cur].src.tolist()
        if not p or p[0] in up: break
        up.append(p[0]); cur = p[0]
    parent = up[0] if up else None
    sib = [d for d in E[E.src == parent].dst if d != node] if parent else []
    return {'equipment': info(node), 'upstream_path': [info(n) for n in up],
            'children': [info(n) for n in E[E.src == node].dst], 'siblings': [info(n) for n in sib]}


@mcp.tool(description='설비 이름 검색(부분 일치, 대소문자 무시). 예: "3F12A", "LTR", "BTR_3U11".')
def find_equipment(keyword: str, limit: int = 30) -> dict:
    N = nodes(); hit = [n for n in N.index if keyword.upper() in n.upper()]
    return {'n': len(hit), 'nodes': [{'node': n, 'type': N.at[n, 'etype']} for n in hit[:limit]]}


@mcp.tool(description='설비 태그 추이: 구간 직전(before_minutes) 대비 구간 중 평균·최소·최대·변화율, 구간 중 12점 요약. 수량: POWER, VOLTAGE, CURRENT, PF, STATUS, TEMP 등.')
def get_trend(node: str, start: str, end: str, before_minutes: int = 60) -> dict:
    q, u = _node_tags(node)
    if not q: return {'error': f'{node}의 태그 없음'}
    W = wide(); a, b = _t(start), _t(end)
    pre, cur = W.loc[a - pd.Timedelta(minutes=before_minutes):a - pd.Timedelta(minutes=1)], W.loc[a:b]
    out = {}
    for qty, tag in q.items():
        if tag not in W: continue
        m0, m1 = pre[tag].mean(), cur[tag].mean()
        pts = cur[tag].iloc[np.linspace(0, len(cur) - 1, min(12, len(cur))).astype(int)] if len(cur) else cur[tag]
        out[qty] = {'tag': tag, 'unit': u[qty], 'before_mean': _r(m0), 'during_mean': _r(m1),
                    'change_pct': _r((m1 / m0 - 1) * 100, 2) if m0 and abs(m0) > 1e-9 else None,
                    'during_min': _r(cur[tag].min()), 'during_max': _r(cur[tag].max()),
                    'during_samples': {str(t)[11:16]: _r(v) for t, v in pts.items()}}
    return {'node': node, 'window': [str(a), str(b)], 'quantities': out}


@mcp.tool(description='물리 점검: (1) 설비 내부식 P − √3·V·I·PF/100 잔차, (2) KCL: 이 설비 P − 바로 아래 계량 설비 P 합, (3) 같은 상위의 형제 설비 전압 대비 편차. 구간 직전과 구간 중을 비교.')
def check_physics(node: str, start: str, end: str, before_minutes: int = 120) -> dict:
    W, T = wide(), tags(); a, b = _t(start), _t(end)
    pre = slice(a - pd.Timedelta(minutes=before_minutes), a - pd.Timedelta(minutes=1)); cur = slice(a, b)
    q, u = _node_tags(node); res = {'node': node}
    if {'POWER', 'VOLTAGE', 'CURRENT', 'PF'} <= q.keys():
        V = W[q['VOLTAGE']] / (1000.0 if u['VOLTAGE'] == 'V' else 1.0)
        r = W[q['POWER']] - np.sqrt(3) * V * W[q['CURRENT']] * W[q['PF']] / 100.0
        res['internal_residual_kw'] = {'before_mean': _r(r[pre].mean(), 2), 'during_mean': _r(r[cur].mean(), 2),
                                       'P_during_mean_kw': _r(W[q['POWER']][cur].mean(), 1)}
    E = edges(); metered = set(T.NODE[T.QUANTITY == 'POWER'])
    def below(n):
        out = []
        for c in E[E.src == n].dst:
            out += [c] if c in metered else below(c)
        return out
    d = below(node)
    if d and 'POWER' in q:
        k = W[q['POWER']] - W[[f'{c}_POWER' for c in d]].sum(axis=1)
        res['kcl_residual_kw'] = {'children_metered': d, 'before_mean': _r(k[pre].mean(), 2), 'during_mean': _r(k[cur].mean(), 2),
                                  'change_kw': _r(k[cur].mean() - k[pre].mean(), 2)}
    p = E[E.dst == node].src.tolist()
    if p and 'VOLTAGE' in q:
        sib = [s for s in E[E.src == p[0]].dst if s != node and f'{s}_VOLTAGE' in W]
        if sib:
            dv = W[q['VOLTAGE']] / W[[f'{s}_VOLTAGE' for s in sib]].median(axis=1) - 1
            res['voltage_vs_siblings_pct'] = {'siblings': sib, 'before_mean': _r(dv[pre].mean() * 100, 3), 'during_mean': _r(dv[cur].mean() * 100, 3)}
    return res


@mcp.tool(description='개폐 이력: 구간 앞뒤 margin_minutes 안에서 차단기 STATUS가 바뀐 시각과 설비(정상 운전인 절체·정비·트립 판별용).')
def get_switching(start: str, end: str, margin_minutes: int = 60) -> dict:
    W, T = wide(), tags(); a, b = _t(start) - pd.Timedelta(minutes=margin_minutes), _t(end) + pd.Timedelta(minutes=margin_minutes)
    st = [c for c in T.EQP_NAME[T.QUANTITY == 'STATUS'] if c in W]
    S = W.loc[a:b, st].round()
    ch = S.diff().fillna(0)
    out = [{'time': str(t), 'switch': c.rsplit('_', 1)[0], 'to': '투입(1)' if S.at[t, c] == 1 else '개방(0)'}
           for t, row in ch.iterrows() for c in row.index[row != 0]]
    return {'window': [str(a), str(b)], 'n_changes': len(out), 'changes': out[:100]}


if __name__ == '__main__':
    mcp.run('stdio')
