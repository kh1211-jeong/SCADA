# -*- coding: utf-8 -*-
"""진단 에이전트용 실시간 조회 도구 (읽기 전용, 설비 제어 없음).

데모 서버가 이 도구들을 MCP(스트리밍 HTTP, :8766/mcp)로 노출하고, goclaw 에이전트가 호출한다.
에이전트가 볼 수 있는 것: 측정값·개폐 기록·경보(모델 출력)·토폴로지. 주입 이벤트(정답)는 보이지 않는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SQ3 = float(np.sqrt(3.0))
QTY_KO = {'POWER': '유효전력(kW)', 'VOLTAGE': '전압', 'CURRENT': '전류(A)', 'PF': '역률(%)', 'STATUS': '개폐 상태(1 투입/0 개방)',
          'TEMP': '온도(℃)', 'TEMP_C': '철심 온도(℃)', 'TEMP_W': '권선 온도(℃)', 'LOAD': '부하율(%)', 'TAP': '탭 위치'}
TYPE_KO = {'BUS': '154kV 모선', 'GCB': '154kV 가스 차단기', 'BTR': '주 변압기(154kV→6.6kV)', 'MAIN': '6.6kV 주 차단기',
           'VCB_K': '6.6kV 모선 분기 차단기', 'VCB_Q': '6.6kV 모선 분기 차단기', 'VCB_FEEDER': '6.6kV 배전선 진공 차단기',
           'LTR': '저압 변압기(6.6kV→220V)', 'ACB': '220V 기중 차단기', 'ACB_MAIN_EMG': '비상 기중 차단기', 'TIE': '연계 차단기(평상 개방)',
           'XCB': '비상 연계 차단기(평상 개방)', 'DIS': '단로기', 'VCB_CAP': '콘덴서 차단기', 'VCS_CAP': '콘덴서 개폐기',
           'VCB_STR': '태양광 연계 차단기', 'STR': '태양광 설비', 'RETURN': '역송 지점'}


def _r(x, n=2):
    try:
        return None if x is None or not np.isfinite(x) else round(float(x), n)
    except TypeError:
        return None


class Tools:
    def __init__(self, eng):
        self.e = eng
        self.N = eng.nodes
        pe = eng.edges[eng.edges.etype == 'power']
        self.parent = dict(zip(pe.dst, pe.src))
        self.children = pe.groupby('src').dst.apply(list).to_dict()
        tg = eng.tags
        self.node_tags = {n: dict(zip(g.QUANTITY, g.EQP_NAME)) for n, g in tg.groupby('NODE')}
        self.units = {n: dict(zip(g.QUANTITY, g.UNIT)) for n, g in tg.groupby('NODE')}

    def _info(self, n):
        if n not in self.N.index: return {'node': n}
        t = self.N.at[n, 'etype']
        return {'node': n, 'type': TYPE_KO.get(t, t), 'system': self.N.at[n, 'system'] if isinstance(self.N.at[n, 'system'], str) else ''}

    # ------------------------------------------------------------------
    def get_overview(self) -> dict:
        """현재 모의 시각, 탐지 모델 상태, 이상 점수/임계, 진행 중 경보, 평상과 다른 개폐 상태, 최근 개폐 기록."""
        e = self.e
        with e.lock:
            sc = e.scores[-1] if e.scores else None
            off = [{'node': n, 'now': '투입' if e.sim.state[e.plant.sw_idx[n]] else '개방',
                    'normal': '투입' if e.plant.normal_state[e.plant.sw_idx[n]] else '개방'} for n in e.off_normal()]
            act = [e.alarm_view(a) for a in e.alarms if a['end'] is None and a['minutes'] >= 3]
            return {'sim_time': e.tstr(), 'model': getattr(e, 'model_name', None),
                    'score': _r(sc[1]) if sc else None, 'threshold': _r(e.thr) if e.model else None,
                    'active_alarms': [{k: a[k] for k in ('id', 'start', 'minutes', 'peak_score', 'top_nodes')} for a in act],
                    'n_alarms_total': len([a for a in e.alarms if a['minutes'] >= 3]),
                    'off_normal_switches': off, 'recent_operations': e.ops[-8:],
                    'current_top_features': e.top_now[:5]}

    def list_alarms(self, limit: int = 20) -> dict:
        """탐지된 이상 경보 목록(최근순): id, 시작·종료, 지속(분), 최대 점수, 기여 상위 설비."""
        e = self.e
        with e.lock:
            al = [e.alarm_view(a) for a in e.alarms if a['minutes'] >= 3][::-1][:limit]
        return {'threshold': _r(e.thr) if e.model else None,
                'alarms': [{k: a[k] for k in ('id', 'start', 'end', 'minutes', 'peak_score', 'top_nodes')} for a in al]}

    def get_alarm(self, alarm_id: str) -> dict:
        """경보 상세: 기여 상위 피처 10개(피처명, 설비, 종류=태그/물리 잔차/KCL 잔차, 정규화 오차 점수)."""
        e = self.e
        with e.lock:
            for a in e.alarms:
                if a['id'] == alarm_id.upper().strip(): return e.alarm_view(a)
        return {'error': f'{alarm_id} 없음. list_alarms로 확인'}

    def get_switching(self, minutes: int = 120) -> dict:
        """최근 개폐 기록(운영자 조작·보호계전기 트립)과 평상 구성과 다른 차단기 목록."""
        e = self.e
        cut = e.ts() - pd.Timedelta(minutes=minutes)
        ops = [o for o in e.ops if pd.Timestamp(o['time']) >= cut]
        ov = self.get_overview()
        return {'sim_time': e.tstr(), 'operations': ops, 'off_normal_switches': ov['off_normal_switches']}

    def get_topology(self, node: str) -> dict:
        """설비의 계통 위치: 상위 경로(154kV 모선까지), 바로 아래 설비, 형제 설비, 연계(TIE) 상대, 현재 가압 여부."""
        if node not in self.N.index: return {'error': f'{node} 없음. find_equipment로 검색'}
        en = self.e.energized()
        info = lambda n: {**self._info(n), 'energized': n in en}
        up, cur = [], node
        while cur in self.parent and len(up) < 10:
            cur = self.parent[cur]; up.append(cur)
        par = self.parent.get(node)
        sib = [d for d in self.children.get(par, []) if d != node] if par else []
        ties = [n for n in self.e.adj.get(node, ()) if n not in self.children.get(node, []) and n != par]
        return {'equipment': info(node), 'upstream_path': [info(n) for n in up], 'children': [info(n) for n in self.children.get(node, [])],
                'siblings': [info(n) for n in sib][:12], 'tie_links': [info(n) for n in ties]}

    def get_grid_rules(self) -> dict:
        """계통 운전 규칙: 설비 종류별 역할·트립 가능 여부, 정전 판단 기준, 병렬 운전 금지 인터록, 과부하 보호 곡선, 백업 용량, 모의 한계."""
        from demo.grid_rules import RULES
        return RULES

    def find_equipment(self, keyword: str, limit: int = 30) -> dict:
        """설비 이름 검색(부분 일치). 예: '3F12A', 'LTR_3F11', 'BTR'."""
        hit = [n for n in self.N.index if keyword.upper() in n.upper()]
        return {'n': len(hit), 'nodes': [self._info(n) for n in hit[:limit]]}

    def get_trend(self, node: str, minutes: int = 30, baseline_minutes: int = 60) -> dict:
        """설비 측정값 추이: 최근 minutes분과 그 앞 baseline_minutes분의 평균·최소·최대, 변화율(%), 최근 값, 최근 구간 6점 요약."""
        if node not in self.node_tags: return {'error': f'{node} 측정 태그 없음'}
        F = self.e.frame(minutes + baseline_minutes)
        if len(F) < 5: return {'error': '데이터 부족'}
        rec, base = F.iloc[-minutes:], F.iloc[:-minutes]
        out = {}
        for q, tag in self.node_tags[node].items():
            r = rec[tag]; b = base[tag] if len(base) else r
            bm = b.mean()
            out[QTY_KO.get(q, q)] = {'baseline_mean': _r(bm), 'recent_mean': _r(r.mean()), 'recent_min': _r(r.min()), 'recent_max': _r(r.max()),
                                     'change_pct': _r((r.mean() - bm) / abs(bm) * 100, 1) if bm and abs(bm) > 1e-6 else None,
                                     'last': _r(r.iloc[-1]), 'flat': bool(r.nunique() <= 1 and len(r) > 3),
                                     'recent_6pt': [_r(x) for x in r.iloc[np.linspace(0, len(r) - 1, 6).astype(int)]]}
        return {'node': node, 'sim_time': self.e.tstr(), 'window': f'최근 {minutes}분 vs 그 앞 {len(base)}분', 'values': out}

    def check_physics(self, node: str, minutes: int = 30) -> dict:
        """물리 관계 점검: (1) 설비 내부식 잔차 P − √3·V·I·PF/100, (2) KCL 잔차 = 이 설비 P − 바로 아래 계량 설비 P 합,
        (3) 같은 상위의 형제 설비 대비 전압 편차, (4) 변압기면 부하율 대비 온도. 각각 최근 minutes분과 그 앞 60분 비교."""
        e = self.e
        F = e.frame(minutes + 60)
        if len(F) < 5: return {'error': '데이터 부족'}
        q = self.node_tags.get(node, {}); u = self.units.get(node, {})
        rec, base = F.iloc[-minutes:], F.iloc[:-minutes] if len(F) > minutes else F
        cmp = lambda s: {'baseline': _r(s.loc[base.index].mean(), 3), 'recent': _r(s.loc[rec.index].mean(), 3), 'last': _r(s.iloc[-1], 3)}
        out = {'node': node, 'sim_time': e.tstr()}
        if {'POWER', 'VOLTAGE', 'CURRENT', 'PF'} <= q.keys():
            V = F[q['VOLTAGE']] / (1000.0 if u.get('VOLTAGE') == 'V' else 1.0)
            calc = SQ3 * V * F[q['CURRENT']] * F[q['PF']] / 100.0
            out['internal_residual_kW'] = cmp(F[q['POWER']] - calc)
            out['internal_residual_note'] = '정상이면 0 근처. 커지면 전류·역률 측정(변류기, 결선) 이상 의심'
        metered = {n for n, t in self.node_tags.items() if 'POWER' in t}

        def below(n):
            r = []
            for c in self.children.get(n, []):
                r += [c] if c in metered else below(c)
            return r
        d = below(node)
        if d and 'POWER' in q:
            k = F[q['POWER']] - F[[f'{c}_POWER' for c in d]].sum(axis=1)
            out['kcl_residual_kW'] = {**cmp(k), 'downstream': d[:12]}
            out['kcl_note'] = '정상이면 변압기 손실 정도의 작은 양수. 갑자기 커지면 미계량 부하·누설 또는 상·하위 전력계 치우침'
        par = self.parent.get(node)
        if 'VOLTAGE' in q and par:
            sib = [s for s in self.children.get(par, []) if s != node and 'VOLTAGE' in self.node_tags.get(s, {})]
            if sib:
                ref = F[[f'{s}_VOLTAGE' for s in sib]].median(axis=1)
                dev = (F[q['VOLTAGE']] - ref) / ref.abs().clip(lower=1e-6) * 100
                out['voltage_dev_vs_siblings_pct'] = {**cmp(dev), 'siblings': sib[:8]}
                out['voltage_note'] = '형제 설비와 같은 모선이면 편차가 0 근처. 서서히 벌어지면 계기용 변압기(PT) 비율 오차 의심'
        if 'LOAD' in q:
            tq = q.get('TEMP_W') or q.get('TEMP')
            if tq:
                out['load_pct'] = cmp(F[q['LOAD']]); out['temperature_C'] = cmp(F[tq])
                out['thermal_note'] = '부하율이 그대로인데 온도만 오르면 냉각 이상(과열) 의심'
        if 'TAP' in q:
            tap = F[q['TAP']]
            out['tap_changes_recent'] = int((tap.loc[rec.index].diff().abs() > 0.5).sum())
            out['tap_changes_baseline'] = int((tap.loc[base.index].diff().abs() > 0.5).sum())
            out['tap_note'] = '정상은 1시간에 몇 번 이하. 짧은 주기로 왕복하면 탭 절환기 헌팅'
        return out

    def get_live_values(self, node: str) -> dict:
        """설비의 현재(최근 1분) 측정값과 가압 여부."""
        q = self.node_tags.get(node)
        if not q: return {'error': f'{node} 측정 태그 없음'}
        return {'node': node, 'sim_time': self.e.tstr(), 'energized': node in self.e.energized(),
                'values': {QTY_KO.get(k, k): _r(self.e.last.get(t)) for k, t in q.items()}}


TOOL_NAMES = ['get_grid_rules', 'get_overview', 'list_alarms', 'get_alarm', 'get_switching', 'get_topology', 'find_equipment', 'get_trend',
              'check_physics', 'get_live_values']


def build_mcp(tools: Tools):
    from mcp.server import MCPServer
    m = MCPServer('scada-live', instructions='154kV~220V 수배전 계통 실시간 감시 데이터 조회 도구(읽기 전용). 시각은 모의 시각.')
    for name in TOOL_NAMES:
        fn = getattr(tools, name)
        m.tool(name=name, description=fn.__doc__)(fn)
    return m
