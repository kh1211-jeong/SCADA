# -*- coding: utf-8 -*-
"""#4 경량화 실험: 토폴로지 고정 GDN(교사, 은닉 64·이웃 24) → 경량 학생(은닉 16·이웃 12).

변형
  GDN-prior     교사. #3 최종 모델과 같은 구조, 가중치 저장
  GDN-lite      학생 구조를 정답(실측값)만으로 학습
  GDN-lite-KD   학생 구조를 정답 + 교사 예측(지식 증류)으로 학습
  GDN-lite-KD-int8  위 모델의 선형층을 8비트 정수로 동적 양자화 (CPU 추론)
측정: 파라미터 수, 저장 크기, CPU 1분 1회 추론 지연(배치 1), 학습 시간 → lite.json
     센서별 오차 캐시 errors_*.npz → analyze_light에서 #3과 같은 방식(정규화·상위5·운전 컨텍스트·운영 임계)으로 채점

사용: FMCS_DATA=fmcs_synth_v2 python -m scripts.run_light [--epochs 25]
"""
import argparse
import io
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from src.data import fmcs
from src.lite.features import FeatureBuilder
from src.models import ae
from src.models.gdn import GDN, topology_neighbors

OUT = Path(__file__).resolve().parents[1] / 'results' / 'fmcs_v2' / 'lite'
W_WIN = 15
CFG = {'GDN-prior': dict(hid=64, k_max=24), 'GDN-lite': dict(hid=16, k_max=12), 'GDN-lite-KD': dict(hid=16, k_max=12)}


def data():
    W = fmcs.load_wide()
    tags = fmcs.tag_table(); edges = pd.read_csv(fmcs.ROOT / 'topology_edges.csv')
    lab = fmcs.labels(index=W.index).fillna(0)
    tr, va, te = fmcs.split_masks(W.index)
    anom = lab['anomaly'].values.astype(bool)
    fb = FeatureBuilder(tags, edges).fit(W, tr, ~anom)
    A = fb.transform(W)
    return fb, tags, edges, dict(Xtr=A[tr], Xval=A[va], Xte=A[te], ok_tr=~anom[tr], ok_val=~anom[va],
                                 y=anom[te].astype(int), op=lab['operational'].values[te].astype(int),
                                 dq=lab['data_quality'].values[te].astype(int), ts=W.index[te])


def fit_kd(teacher, d, nb, hid, epochs, dev, alpha=0.5, seed=0, bs=256, lr=1e-3, patience=5):
    """ae.fit과 같은 절차 + 손실 = (1−α)·‖ŷ−x‖² + α·‖ŷ−ŷ_교사‖² (마지막 시점만)."""
    torch.manual_seed(seed); np.random.seed(seed)
    Xtr, Xval = d['Xtr'], d['Xval']
    m = GDN(Xtr.shape[1], W_WIN, hid=hid, neighbors=nb).to(dev)
    opt = torch.optim.Adam(m.parameters(), lr=lr)
    tri, vai = ae.ok_windows(d['ok_tr'], W_WIN), ae.ok_windows(d['ok_val'], W_WIN)
    teacher.eval(); best, bad, state = np.inf, 0, None
    t0 = time.time()
    for ep in range(epochs):
        m.train(); np.random.shuffle(tri)
        for s in range(0, len(tri), bs):
            xb = torch.from_numpy(ae._windows(Xtr, tri[s:s + bs], W_WIN)).to(dev)
            with torch.no_grad(): yt = teacher(xb)[:, -1]
            yp = m(xb)[:, -1]
            loss = (1 - alpha) * ((yp - xb[:, -1]) ** 2).mean() + alpha * ((yp - yt) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step()
        v = ae.per_sensor_error(m, Xval, W_WIN, dev, idx=vai).mean()
        el = time.time() - t0
        print(f'  GDN-lite-KD ep{ep + 1}/{epochs} val={v:.5f} best={min(best, v):.5f} 경과 {el / 60:.1f}분', flush=True)
        if v < best - 1e-6:
            best, bad, state = v, 0, {k: t.detach().clone() for k, t in m.state_dict().items()}
        else:
            bad += 1
            if bad >= patience: break
    m.load_state_dict(state)
    return m


def size_bytes(m):
    b = io.BytesIO(); torch.save(m.state_dict(), b); return b.getbuffer().nbytes


@torch.no_grad()
def latency_ms(m, D, n=50):
    m = m.cpu().eval(); x = torch.randn(1, W_WIN, D)
    for _ in range(5): m(x)
    t = time.perf_counter()
    for _ in range(n): m(x)
    return (time.perf_counter() - t) / n * 1000


def quantize(m):
    return torch.ao.quantization.quantize_dynamic(m.cpu().eval(), {torch.nn.Linear}, dtype=torch.qint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--epochs', type=int, default=25)
    ap.add_argument('--models', nargs='+', default=['GDN-prior', 'GDN-lite', 'GDN-lite-KD'])
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(int(__import__('os').environ.get('LIGHT_THREADS', 4)))
    fb, tags, edges, d = data()
    fb.save(OUT / 'feat.json')
    np.savez(OUT / 'meta.npz', y=d['y'], op=d['op'], dq=d['dq'], ts=d['ts'].values.astype('datetime64[ns]').astype('int64'),
             cols=np.array(fb.cols), root=fmcs.ROOT.name)
    D = len(fb.cols)
    print('features', D, 'train', d['Xtr'].shape, flush=True)
    import os
    dev = os.environ.get('LIGHT_DEVICE') or ('mps' if torch.backends.mps.is_available() else 'cpu')
    models = {}
    for name in a.models:
        c = CFG[name]
        nb = topology_neighbors(fb.cols, tags, edges, k_max=c['k_max'])
        np.save(OUT / f'neighbors_k{c["k_max"]}.npy', nb)
        t0 = time.time()
        if name == 'GDN-lite-KD':
            if 'GDN-prior' not in models:
                tch = GDN(D, W_WIN, hid=64, neighbors=topology_neighbors(fb.cols, tags, edges, k_max=24))
                tch.load_state_dict(torch.load(OUT / 'GDN-prior.pt', map_location='cpu')); models['GDN-prior'] = tch
            m = fit_kd(models['GDN-prior'].to(dev), d, nb, c['hid'], a.epochs, dev)
        else:
            m = ae.fit('GDN', d['Xtr'], d['Xval'], W_WIN, epochs=a.epochs, seed=0, device=dev, ok_tr=d['ok_tr'],
                       ok_val=d['ok_val'], verbose=True, model_kw=dict(hid=c['hid'], neighbors=nb))
        train_s = time.time() - t0
        models[name] = m
        torch.save(m.state_dict(), OUT / f'{name}.pt')
        variants = [(name, m)] + ([(name + '-int8', quantize(m))] if name == 'GDN-lite-KD' else [])
        for vn, mm in variants:
            dv = 'cpu' if vn.endswith('int8') else dev
            E_te = ae.per_sensor_error(mm.to(dv), d['Xte'], W_WIN, dv)
            E_val = ae.per_sensor_error(mm.to(dv), d['Xval'], W_WIN, dv, idx=ae.ok_windows(d['ok_val'], W_WIN))
            np.savez(OUT / f'errors_{vn}_s0.npz', E_te=E_te, E_val=E_val)
            info = json.load(open(OUT / 'lite.json')) if (OUT / 'lite.json').exists() else {}   # 병행 실행 시 덮어쓰기 방지
            info[vn] = {'params': int(sum(p.numel() for p in m.parameters())), 'hid': c['hid'], 'k_max': c['k_max'],
                        'size_kb': size_bytes(mm) / 1024, 'latency_ms': latency_ms(mm, D), 'train_min': train_s / 60}
            if vn.endswith('int8'): torch.save(mm.state_dict(), OUT / f'{vn}.pt')
            print(vn, info[vn], flush=True)
            json.dump(info, open(OUT / 'lite.json', 'w'), indent=1, ensure_ascii=False)
            mm.to(dev) if not vn.endswith('int8') else None
    print('done', flush=True)


if __name__ == '__main__':
    main()
