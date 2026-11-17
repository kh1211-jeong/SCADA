# -*- coding: utf-8 -*-
"""#4 경량화 결과 채점 + 데모용 모델 번들 생성.

채점: #3과 같은 방식(센서별 정규화 → 운전 컨텍스트 마스크 → 상위 5 평균 → 6분 평활 → 운영 임계 = 평상 구성 검증 99%).
추가 지표: 원인 설비 적중률(이벤트 구간 평균 정규화 오차 상위 3개 설비 안에 실제 대상 설비가 있는 비율).
출력: results/fmcs_v2/lite/eval.json, bundle.json(데모 엔진이 읽음)

사용: FMCS_DATA=fmcs_synth_v2 python -m scripts.export_lite [--deploy GDN-lite-KD-int8]
"""
import argparse
import json
from pathlib import Path
import numpy as np
from scripts.analyze3 import DS
from src.eval import normalize_errors

LITE = Path(__file__).resolve().parents[1] / 'results' / 'fmcs_v2' / 'lite'
VARIANTS = ['GDN-prior', 'GDN-lite', 'GDN-lite-KD', 'GDN-lite-KD-int8', 'GDN-lite-KD-fp16']


def node_hit(ds, m):
    Et, Ev = ds.runs[m][0]
    Z = normalize_errors(Et, Ev)
    if ds.ctx_te is not None: Z = np.where(ds.ctx_te, 0.0, Z)
    from src.data import fmcs
    tags = fmcs.tag_table(); node_of = dict(zip(tags.EQP_NAME, tags.NODE))
    cn = [node_of.get(c, c.rsplit('_', 1)[0]) for c in ds.cols]
    hits = []
    for a, b, pts, typ in ds.table:
        tgt = {node_of.get(p, p.rsplit('_', 1)[0]) for p in pts}
        if not tgt or typ == 'voltage_sag': continue
        z = Z[a:b].mean(0)
        by = {}
        for j, n in enumerate(cn): by[n] = max(by.get(n, -1e9), z[j])
        top = sorted(by, key=lambda n: -by[n])[:3]
        hits.append(bool(tgt & set(top)))
    return float(np.mean(hits)), len(hits)


def load_compact(path):
    import torch
    sd = torch.load(path, map_location='cpu')
    return {k: (v.float() if v.is_floating_point() else v.long() if v.dtype == torch.int16 else v) for k, v in sd.items()}


def remeasure(info, D):
    """학습이 모두 끝난 뒤 다른 작업 없이 CPU 4스레드로 저장 크기·1회 추론 시간을 다시 잰다(병행 학습 중 측정치 대체)."""
    import torch
    from src.models.gdn import GDN
    from scripts.run_light import latency_ms, size_bytes, W_WIN
    torch.set_num_threads(4)
    for m in info:
        base = m.replace('-int8', '')
        nb = np.load(LITE / f"neighbors_k{info[m]['k_max']}.npy")
        net = GDN(D, W_WIN, hid=info[m]['hid'], neighbors=nb)
        if m.endswith('int8'):
            net = (setattr(torch.backends.quantized, 'engine', torch.backends.quantized.supported_engines[-1]) or torch.ao.quantization.quantize_dynamic)(net.eval(), {torch.nn.Linear}, dtype=torch.qint8)
            net.load_state_dict(torch.load(LITE / f'{m}.pt', map_location='cpu'))
        elif m.endswith('fp16'):   # 16비트 실수 가중치 + 16비트 이웃 인덱스로 저장, 읽을 때 32비트로 복원
            net.load_state_dict(load_compact(LITE / f'{m}.pt'))
            info[m]['size_kb'] = (LITE / f'{m}.pt').stat().st_size / 1024
            info[m]['latency_ms'] = float(np.median([latency_ms(net, D, 40) for _ in range(3)]))
            print('measure', m, round(info[m]['size_kb']), 'KB', round(info[m]['latency_ms'], 2), 'ms'); continue
        else:
            net.load_state_dict(torch.load(LITE / f'{base}.pt', map_location='cpu'))
        info[m]['size_kb'] = size_bytes(net) / 1024
        info[m]['latency_ms'] = float(np.median([latency_ms(net, D, 40) for _ in range(3)]))
        print('measure', m, round(info[m]['size_kb']), 'KB', round(info[m]['latency_ms'], 2), 'ms')
    json.dump(info, open(LITE / 'lite.json', 'w'), indent=1, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--deploy', default='GDN-lite-KD-fp16')
    a = ap.parse_args()
    ds = DS('fmcs_v2/lite', 'fmcs')
    ds.runs = {m: [(np.load(f)['E_te'], np.load(f)['E_val'])] for m in VARIANTS if (f := LITE / f'errors_{m}_s0.npz').exists()}
    info = json.load(open(LITE / 'lite.json'))
    remeasure(info, len(ds.cols))
    ev = {}
    for m in ds.runs:
        s, sv = ds.score(m, ctx=True)
        r = ds.evaluate(s, sv, m)
        hit, n = node_hit(ds, m)
        ev[m] = {k: r[k] for k in ('ROC-AUC', 'F1*', 'F1op', 'FAR_op', 'event_recall', 'delay_min')} | {'node_top3': hit, 'n_loc': n}
        ev[m] |= {k: info[m][k] for k in ('params', 'size_kb', 'latency_ms', 'train_min', 'hid', 'k_max') if m in info}
        print(m, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in ev[m].items()})
    json.dump(ev, open(LITE / 'eval.json', 'w'), indent=1, ensure_ascii=False)

    m = a.deploy
    Et, Ev = ds.runs[m][0]
    s, sv = ds.score(m, ctx=True)
    med = np.median(Ev, 0); iqr = np.quantile(Ev, 0.75, 0) - np.quantile(Ev, 0.25, 0)
    base = m.replace('-int8', '')
    base = m.replace('-int8', '') if m.endswith('int8') else m
    bundle = {'name': m, 'weights': f'{m}.pt' if m.endswith(('int8', 'fp16')) else f'{base}.pt', 'int8': m.endswith('int8'), 'fp16': m.endswith('fp16'),
              'hid': info[m]['hid'], 'k_max': info[m]['k_max'], 'params': info[m]['params'], 'size_kb': info[m]['size_kb'],
              'latency_ms': info[m]['latency_ms'], 'thr': float(ds.thr(sv, m)), 'med': med.tolist(), 'iqr': iqr.tolist(),
              'teacher': {k: ev['GDN-prior'][k] for k in ('params', 'size_kb', 'latency_ms')} if 'GDN-prior' in ev else None}
    json.dump(bundle, open(LITE / 'bundle.json', 'w'))
    print('bundle', m, 'thr %.2f' % bundle['thr'])


if __name__ == '__main__':
    main()
