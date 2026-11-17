# -*- coding: utf-8 -*-
"""진단 에이전트용 경보 저장소: #3 최종 모델 점수 → 경보 구간 + 구간별 기여 피처 → results/agent/store.json.

에이전트는 이 저장소(탐지 결과)와 원신호·토폴로지만 본다. 정답 라벨(events.csv)은 넣지 않는다.
채점용으로 경보-정답 매칭은 results/agent/store_eval.json에 따로 저장한다.

사용: FMCS_DATA=fmcs_synth_v2 python -m src.agent.build_store [--model GDN-prior]
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.data import fmcs
from src.eval import normalize_errors, aggregate, smooth
from scripts.analyze3 import DS, RES

OUT = RES / 'agent'
GAP_MIN, MIN_LEN, TOPN = 10, 3, 10          # 10분 이내 끊김은 한 경보로, 3분 미만 경보는 버림, 기여 피처 상위 10개


def kind_of(col):
    if col.endswith('_RESID'): return '물리 잔차(P−√3·V·I·PF)'
    if col.endswith('_KCL'): return 'KCL 잔차(상위 P − 하위 P 합)'
    return '태그'


def node_of(col, tags):
    m = dict(zip(tags.EQP_NAME, tags.NODE))
    return m.get(col, col.rsplit('_', 1)[0])


def segments(pred, gap, min_len):
    idx = np.flatnonzero(pred)
    if not len(idx): return []
    segs, a, b = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - b <= gap: b = i
        else: segs.append((a, b)); a = b = i
    segs.append((a, b))
    return [(a, b + 1) for a, b in segs if b + 1 - a >= min_len]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='GDN-prior')
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ds = DS('fmcs_v2/kcl_rs', 'fmcs')
    tags = fmcs.tag_table()
    Et, Ev = ds.runs[a.model][0]
    Zt, Zv = normalize_errors(Et, Ev), normalize_errors(Ev, Ev)
    Zt = np.where(ds.ctx_te, 0.0, Zt); Zv = np.where(ds.ctx_val[ds.w(a.model)], 0.0, Zv)   # 운전 컨텍스트 제외
    s, sv = smooth(aggregate(Zt, 'topk', 5), 6), smooth(aggregate(Zv, 'topk', 5), 6)
    thr = float(ds.thr(sv, a.model))
    ts = ds.ts
    alarms, ev_rows = [], []
    for i, (p, q) in enumerate(segments(s > thr, GAP_MIN, MIN_LEN), 1):
        contrib = Zt[p:q].mean(0)
        top = np.argsort(contrib)[::-1][:TOPN]
        feats = [{'feature': ds.cols[j], 'node': node_of(ds.cols[j], tags), 'kind': kind_of(ds.cols[j]),
                  'score': round(float(contrib[j]), 1)} for j in top]
        nodes = list(dict.fromkeys(f['node'] for f in feats))[:3]
        alarms.append({'id': f'AL{i:03d}', 'start': str(ts[p]), 'end': str(ts[q - 1]), 'minutes': int(q - p),
                       'peak_score': round(float(s[p:q].max()), 1), 'threshold': round(thr, 2),
                       'top_nodes': nodes, 'top_features': feats})
        ev_rows.append((i, p, q))
    json.dump({'model': a.model, 'data': fmcs.ROOT.name, 'period': [str(ts[0]), str(ts[-1])], 'threshold': round(thr, 2),
               'n_alarms': len(alarms), 'alarms': alarms}, open(OUT / 'store.json', 'w'), ensure_ascii=False, indent=1)
    # 채점용(에이전트 비공개): 경보 ↔ 정답 이벤트 매칭
    ev = fmcs.events(); ev = ev[(ev.kind == 'anomaly') & (ev.end >= ts[0]) & (ev.start <= ts[-1])]
    match = []
    for al in alarms:
        a0, a1 = pd.Timestamp(al['start']), pd.Timestamp(al['end'])
        hit = ev[(ev.start <= a1) & (ev.end >= a0)]
        match.append({'id': al['id'], 'truth': [{'type': r.type, 'target': r.target} for r in hit.itertuples()],
                      'top_node_hit': any(str(r.target).startswith(n) for r in hit.itertuples() for n in al['top_nodes'])})
    tp = sum(bool(m['truth']) for m in match)
    json.dump({'alarms': match, 'n_true_alarms': tp, 'n_false_alarms': len(match) - tp,
               'localized': sum(m['top_node_hit'] for m in match)}, open(OUT / 'store_eval.json', 'w'), ensure_ascii=False, indent=1)
    print(f'경보 {len(alarms)}건 (정답 겹침 {tp}, 오경보 {len(match) - tp}, 상위 3 설비에 원인 포함 '
          f'{sum(m["top_node_hit"] for m in match)}) → {OUT / "store.json"}')


if __name__ == '__main__':
    main()
