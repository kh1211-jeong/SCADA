# -*- coding: utf-8 -*-
"""데모 엔진: 실시간 계통 시뮬레이터 + 경량 이상탐지 모델 + 경보/조작 기록.

- 시뮬레이터: src.data.synth_fmcs (3차 학습 데이터 fmcs_synth_v2와 같은 시나리오: seed 7, 42일, v2 프로파일)를
  1분(3초 × 20샘플) 단위로 진행한다. 설비 정격·부하 패턴이 학습 데이터와 같으므로 학습된 모델을 그대로 쓴다.
  예정된 이벤트는 모두 지우고, 운영자(웹 화면)가 차단기 조작·이벤트 주입으로만 계통을 바꾼다.
- 탐지: results/fmcs_v2/lite 의 경량 GDN(토폴로지 고정, 은닉 16, 8비트 양자화)을 CPU에서 매 분 1회 추론.
  점수 = 센서별 정규화 오차 상위 5개 평균(운전 컨텍스트 마스크 적용) → 6분 인과 평활 → 운영 임계(검증 99%).
- 기록: 경보(시작·종료·기여 상위 피처/설비), 개폐 기록(운영자 조작/보호 트립), 주입 이벤트(정답, 에이전트에는 비공개).
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from src.data import synth_fmcs as sf
from src.lite.features import FeatureBuilder
from src.models.gdn import GDN

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'fmcs_synth_v2'
LITE = ROOT / 'results' / 'fmcs_v2' / 'lite'
W_WIN, TOPK, SMOOTH, HOLD, HOPS = 15, 5, 6, 15, 2
BUF = 24 * 60                      # 최근 24시간(1분) 보관

EVENT_TYPES = {   # 화면에서 주입 가능한 이벤트: 대상 설비 종류, 기본 지속(분), 설명
    'ct_drift':     dict(name='계기용 변류기 비율 오차(전류 측정값 서서히 증가)', targets='analog', minutes=90),
    'pt_drift':     dict(name='계기용 변압기 비율 오차(전압 측정값 서서히 변화)', targets='analog', minutes=120),
    'sensor_stuck': dict(name='측정값 고착(값이 변하지 않음)', targets='analog', minutes=60),
    'spike_burst':  dict(name='전류 순간 급등 반복', targets='analog', minutes=8),
    'pf_sign_flip': dict(name='역률 부호 반전(결선·설정 오류)', targets='analog', minutes=60),
    'meter_offset': dict(name='전력량계 치우침(하위 합계와 불일치)', targets='acb', minutes=90),
    'hidden_load':  dict(name='계량되지 않는 부하·누설', targets='feeder', minutes=120),
    'ltr_overheat': dict(name='저압 변압기 냉각 이상(과열)', targets='ltr', minutes=150),
    'oltc_hunting': dict(name='변압기 탭 절환기 반복 동작(헌팅)', targets='btr', minutes=90),
    'voltage_sag':  dict(name='154kV 수전 순간 전압 강하', targets='bus', minutes=1),
    'comm_loss':    dict(name='통신 두절(측정값 수신 안 됨)', targets='analog', minutes=30),
}


class Engine:
    def __init__(self, start_day=30, start_hour=8, seed=7):
        rng = np.random.default_rng(seed)
        g, _ = sf.load_egms_grid()
        self.plant = p = sf.Plant.from_grid(g)
        self.sc = sf.design_scenario(p, 42, pd.Timestamp('2026-09-07'), rng, 1.0, 'v2', 12, 3)
        self.sc.events, self.sc.sw_changes = [], []          # 예정 이벤트 제거 → 운영자 조작만
        self.tags = sf.build_tag_table(p)
        self.sim = sf.Simulator(p, self.sc, self.tags, rng)
        self.sensor_rng = np.random.default_rng(seed + 1)
        self.t = start_day * sf.SPD + start_hour * 3600 // sf.SEC_STEP     # 3초 샘플 인덱스
        self.t_end = 42 * sf.SPD - sf.SPM
        self.start = self.sc.start
        self.lock = threading.RLock()
        self.rows: deque = deque(maxlen=BUF)           # (timestamp, dict tag->value)
        self.scores: deque = deque(maxlen=BUF)         # (timestamp, score, thr)
        self.raw_scores: deque = deque(maxlen=SMOOTH)
        self.alarms: list[dict] = []
        self.ops: list[dict] = []                      # 개폐 기록
        self.injected: list[dict] = []                 # 주입 이벤트(정답)
        self.listeners: list = []                      # 경보/조작 발생 콜백 (자동 진단)
        self.last = {}
        self.top_now: list[dict] = []
        self.speed = 1.0                               # 실시간 1초당 모의 분
        self.paused = False
        self.n_ev = 0
        self.nodes = pd.read_csv(DATA / 'topology_nodes.csv').set_index('node')
        self.edges = pd.read_csv(DATA / 'topology_edges.csv')
        self.adj = {}
        for a, b in zip(self.edges.src, self.edges.dst):
            self.adj.setdefault(a, set()).add(b); self.adj.setdefault(b, set()).add(a)
        self.status_tags = [r.EQP_NAME for r in self.tags.itertuples() if r.QUANTITY == 'STATUS']
        self.normal_status = None
        self.last_change = {}                          # 스위치 노드 -> 마지막 개폐 시각(분 인덱스)
        self.minute = 0
        self._load_model()

    # ------------------------------------------------------------------ 모델
    def _load_model(self):
        self.model = None
        b = LITE / 'bundle.json'
        if not b.exists():
            print('[engine] 경량 모델 번들 없음 — 탐지 없이 시뮬레이터만 실행 (scripts/export_lite.py 실행 필요)')
            return
        info = json.load(open(b))
        self.fb = FeatureBuilder(pd.read_csv(DATA / 'TN_CM_EQP.csv'), self.edges).load(LITE / 'feat.json')
        D = len(self.fb.cols)
        nb = np.load(LITE / f"neighbors_k{info['k_max']}.npy")
        m = GDN(D, W_WIN, hid=info['hid'], neighbors=nb)
        if info['int8']:
            m = torch.ao.quantization.quantize_dynamic(m.eval(), {torch.nn.Linear}, dtype=torch.qint8)
        m.load_state_dict(torch.load(LITE / info['weights'], map_location='cpu'))
        self.model = m.eval()
        self.med, self.iqr = np.array(info['med']), np.array(info['iqr'])
        self.thr = info['thr']; self.model_name = info['name']; self.model_info = info
        self.col_node = self.fb.col_node(); self.col_kind = self.fb.col_kind()
        node_cols = {}
        for j, n in enumerate(self.col_node): node_cols.setdefault(n, []).append(j)
        self.node_cols = node_cols
        torch.set_num_threads(2)
        print(f"[engine] 모델 {info['name']} 로드: 피처 {D}, 임계 {self.thr:.2f}")

    # ------------------------------------------------------------------ 시간
    def ts(self, t=None):
        t = self.t if t is None else t
        return self.start + pd.Timedelta(seconds=int(t) * sf.SEC_STEP)

    def tstr(self, t=None): return self.ts(t).strftime('%Y-%m-%d %H:%M')

    # ------------------------------------------------------------------ 운영자 조작
    def switch(self, node, closed, trip=False, who='운영자'):
        with self.lock:
            if node not in self.plant.sw_idx: return {'error': f'{node}는 개폐 설비가 아님'}
            cur = int(self.sim.state[self.plant.sw_idx[node]])
            if cur == int(closed): return {'ok': True, 'note': '이미 같은 상태'}
            self.sc.sw_changes.insert(self.sim.sw_ptr, (self.t, node, int(closed)))
            op = {'time': self.tstr(), 'node': node, 'action': '투입' if closed else ('트립(보호계전기 동작)' if trip else '개방'),
                  'by': '보호계전기' if trip else who, 'etype': self.plant.etype[node]}
            self.ops.append(op)
            if trip:   # 트립은 보호계전기 동작 = 설비 고장으로 기록 (정답 목록에도 남김)
                self._add_injected('breaker_trip', node, 0, {}, '차단기 트립(보호계전기 동작)')
            self._notify('switch', op)
            return {'ok': True, 'op': op}

    def inject(self, typ, target, minutes=None, params=None):
        with self.lock:
            if typ not in EVENT_TYPES: return {'error': f'알 수 없는 이벤트 {typ}'}
            spec = EVENT_TYPES[typ]
            minutes = float(minutes or spec['minutes'])
            node = target.rsplit('_', 1)[0] if target.endswith(('_CURRENT', '_POWER', '_VOLTAGE', '_PF')) else target
            pr = dict(params or {})
            n = int(minutes * sf.SPM)
            if typ == 'ct_drift':
                tgt = f'{node}_CURRENT'; pr.setdefault('gain', 1.10); pr.setdefault('ramp', int(min(n * 0.4, 40 * sf.SPM)))
            elif typ == 'pt_drift':
                tgt = node; pr.setdefault('gain', 1.015); pr.setdefault('ramp', int(min(n * 0.4, 40 * sf.SPM)))
            elif typ == 'sensor_stuck':
                tgt = f"{node}_{pr.pop('quantity', 'POWER')}"
            elif typ == 'spike_burst':
                tgt = f'{node}_CURRENT'; pr.setdefault('mult', 3.0)
            elif typ == 'pf_sign_flip':
                tgt = f'{node}_PF'
            elif typ == 'meter_offset':
                tgt = f'{node}_POWER'; pr.setdefault('offset_frac', 0.15)
            elif typ == 'hidden_load':
                tgt = node
                P = abs(self.last.get(f'{node}_POWER', 500.0))
                pr.setdefault('frac', 0.10); pr.setdefault('pf', 0.85); pr.setdefault('ramp', 5 * sf.SPM)
                pr['extra_kw'] = float(pr['frac'] * max(P, 100.0))
            elif typ == 'ltr_overheat':
                tgt = node; pr.setdefault('delta_c', 18.0)
            elif typ == 'oltc_hunting':
                tgt = node; pr.setdefault('period_min', 3.0)
            elif typ == 'voltage_sag':
                tgt = 'BUS_154kV'; pr.setdefault('depth', 0.2); n = max(n, 10)
            else:
                tgt = node
            ev = self._add_injected(typ, tgt, n, pr, spec['name'])
            self.sc.events.append({'event_id': ev['id'], 'kind': 'data_quality' if typ == 'comm_loss' else 'anomaly',
                                   'type': typ, 'target': tgt, 'start': self.t, 'end': self.t + n, 'params': pr})
            self._notify('inject', ev)
            return {'ok': True, 'event': ev}

    def _add_injected(self, typ, tgt, n, pr, name):
        self.n_ev += 1
        ev = {'id': f'EV{self.n_ev:03d}', 'type': typ, 'name': name, 'target': tgt, 'start': self.tstr(),
              'end': self.tstr(self.t + n), 'params': {k: (round(v, 4) if isinstance(v, float) else v) for k, v in pr.items()}}
        self.injected.append(ev)
        return ev

    def reset_events(self):
        with self.lock:
            self.sc.events = [e for e in self.sc.events if e['end'] < self.t]
            for sw, i in self.plant.sw_idx.items():
                if self.sim.state[i] != self.plant.normal_state[i]:
                    self.switch(sw, bool(self.plant.normal_state[i]), who='운영자(평상 복귀)')

    def _notify(self, kind, obj):
        for f in self.listeners:
            try: f(kind, obj)
            except Exception as e: print('[engine] listener error', e)

    # ------------------------------------------------------------------ 진행
    def step(self):
        """모의 1분 진행 → 1분 평균 측정값 → 탐지."""
        with self.lock:
            if self.t >= self.t_end:
                return
            truth = self.sim.run_block(self.t, sf.SPM)
            meas, missing = sf.apply_sensor(truth, self.tags, self.sc.events, self.t, self.sensor_rng)
            row = {}
            for k, x in meas.items():
                v = float(np.mean(x))
                if k in missing and missing[k].any(): v = float('nan')
                row[k] = v
            ts = self.ts()
            self.t += sf.SPM
            self.minute += 1
            self.rows.append((ts, row))
            self.last = row
            if self.normal_status is None:
                self.normal_status = {s: int(self.plant.normal_state[self.plant.sw_idx[s.rsplit('_', 1)[0]]])
                                      for s in self.status_tags if s.rsplit('_', 1)[0] in self.plant.sw_idx}
            for s in self.status_tags:
                n = s.rsplit('_', 1)[0]
                if len(self.rows) > 1 and n in self.plant.sw_idx:
                    prev = self.rows[-2][1].get(s)
                    if prev is not None and not np.isnan(prev) and round(prev) != round(row[s]):
                        self.last_change[n] = self.minute
            self._detect(ts)

    def off_normal(self):
        """평상 구성과 다른 차단기(콘덴서 자동 개폐 VCS_CAP 제외)."""
        return [n for n, i in self.plant.sw_idx.items()
                if self.sim.state[i] != self.plant.normal_state[i] and self.plant.etype[n] != 'VCS_CAP']

    def _context_cols(self):
        """운전 컨텍스트: 평상 구성과 다르거나 최근 15분 내 개폐된 스위치로부터 2단계 이내 설비 피처."""
        act = set()
        for n in self.off_normal(): act.add(n)
        for n, m in self.last_change.items():
            if self.minute - m < HOLD: act.add(n)          # 콘덴서 자동 개폐도 직후 15분은 제외(학습 때와 동일)
        near = set()
        for sn in act:
            fr, seen = {sn}, {sn}
            for _ in range(HOPS):
                fr = {m for u in fr for m in self.adj.get(u, ())} - seen; seen |= fr
            near |= seen
        return near

    def _detect(self, ts):
        if self.model is None or len(self.rows) < W_WIN + 1:
            return
        W = pd.DataFrame([r for _, r in list(self.rows)[-(W_WIN + 30):]])
        X = self.fb.transform(W)[-W_WIN:]
        with torch.no_grad():
            xb = torch.from_numpy(X[None])
            pred = self.model(xb)[0, -1].numpy()
        e = (pred - X[-1]) ** 2
        z = (e - self.med) / (self.iqr + 1e-2)
        near = self._context_cols()
        mask = np.array([n in near for n in self.col_node])
        z = np.where(mask, 0.0, z)
        top = np.argsort(z)[-TOPK:][::-1]
        raw = float(z[top].mean())
        self.raw_scores.append(raw)
        s = float(np.mean(self.raw_scores))
        self.scores.append((ts, s, self.thr))
        top10 = np.argsort(z)[-10:][::-1]
        self.top_now = [{'feature': self.fb.cols[j], 'node': self.col_node[j], 'kind': self.col_kind[j], 'score': round(float(z[j]), 1)}
                        for j in top10 if z[j] > 3]
        self._alarm_fsm(ts, s)

    def _alarm_fsm(self, ts, s):
        cur = self.alarms[-1] if self.alarms and self.alarms[-1]['end'] is None else None
        if s > self.thr:
            if cur is None:
                cur = {'id': f'AL{len(self.alarms) + 1:03d}', 'start': ts.strftime('%Y-%m-%d %H:%M'), 'end': None,
                       'peak_score': 0.0, 'threshold': round(self.thr, 2), 'feat_acc': {}, 'minutes': 0, 'notified': False}
                self.alarms.append(cur)
            cur['minutes'] += 1
            cur['peak_score'] = round(max(cur['peak_score'], s), 1)
            for f in self.top_now:
                a = cur['feat_acc'].setdefault(f['feature'], [f['node'], f['kind'], 0.0])
                a[2] = max(a[2], f['score'])
            if cur['minutes'] >= 3 and not cur['notified']:     # 3분 지속 시 자동 진단 요청
                cur['notified'] = True
                self._notify('alarm', self.alarm_view(cur))
        elif cur is not None:
            cur['end'] = ts.strftime('%Y-%m-%d %H:%M')
            if cur['minutes'] < 3:                              # 3분 미만 일시 초과는 경보로 남기지 않음
                self.alarms.pop()

    def alarm_view(self, a):
        feats = sorted(a['feat_acc'].items(), key=lambda kv: -kv[1][2])[:10]
        nodes = list(dict.fromkeys(v[0] for _, v in feats))[:3]
        return {'id': a['id'], 'start': a['start'], 'end': a['end'] or '진행 중', 'minutes': a['minutes'],
                'peak_score': a['peak_score'], 'threshold': a['threshold'], 'top_nodes': nodes,
                'top_features': [{'feature': k, 'node': v[0], 'kind': v[1], 'score': round(v[2], 1)} for k, v in feats]}

    # ------------------------------------------------------------------ 조회
    def frame(self, minutes=60):
        with self.lock:
            rows = list(self.rows)[-minutes:]
            return pd.DataFrame([r for _, r in rows], index=[t for t, _ in rows])

    def energized(self):
        order, _, _ = self.sim._topology(self.sim.state.copy())
        return set(order)

    def run(self):
        """백그라운드 루프: speed(모의 분/초)에 맞춰 step 호출."""
        while True:
            t0 = time.time()
            if not self.paused:
                try: self.step()
                except Exception as e:
                    import traceback; traceback.print_exc()
            time.sleep(max(0.02, 1.0 / max(self.speed, 0.1) - (time.time() - t0)))

    def warmup(self, minutes=40):
        for _ in range(minutes): self.step()
