# -*- coding: utf-8 -*-
"""WADI A2 실데이터: IF / PCA / AE 계열 학습 → 센서별 오차 캐시 저장.

사용: python -m scripts.run_wadi [--seeds 0 1 2] [--w 30] [--models MLP-AE LSTM-AE ...]
결과: results/wadi/errors_{model}_s{seed}.npz  (E_te, E_val : 센서별 오차)
"""
import argparse, time
from pathlib import Path
import numpy as np
import torch
from sklearn.ensemble import IsolationForest
from sklearn.decomposition import PCA
from src.data.wadi import load
from src.models import ae

OUT = Path(__file__).resolve().parents[1] / 'results' / 'wadi'


def prep(drop_drift=False, tol=0.05, frac=0.2):
    Xtr, Xte, y, ts = load()
    if drop_drift:
        # 센서 드리프트 필터(라벨 미사용): 테스트 입력의 frac 이상이 학습 범위를 벗어나는 센서 제외.
        # 운영 관점에선 '센서 교정/고장' 알림 대상이지 공정 이상탐지 입력으로 부적합.
        lo, hi = Xtr.min(), Xtr.max(); r = (hi - lo).where(hi - lo > 0, 1.0)
        out = ((Xte < lo - tol * r) | (Xte > hi + tol * r)).mean()
        drift = list(out[out > frac].index)
        print('drift sensors dropped:', drift)
        Xtr, Xte = Xtr.drop(columns=drift), Xte.drop(columns=drift)
    cols = list(Xtr.columns)
    n_val = len(Xtr) // 10                                   # 정상 마지막 10% = 검증(조기종료·임계)
    lo, hi = Xtr.min(), Xtr.max()
    rng = (hi - lo).where(hi - lo > 0, 1.0)                  # 학습 중 상수 센서: 원 단위 편차 그대로
    sc = lambda X: ((X - lo) / rng).clip(-5, 5).values.astype('float32')
    Xa = sc(Xtr)
    return Xa[:-n_val], Xa[-n_val:], sc(Xte), y, ts, cols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2])
    ap.add_argument('--w', type=int, default=30)
    ap.add_argument('--models', nargs='+', default=['IF', 'PCA'] + list(ae.MODELS))
    ap.add_argument('--epochs', type=int, default=40)
    ap.add_argument('--drop-drift', action='store_true')
    a = ap.parse_args()
    out = OUT / ('drift_filtered' if a.drop_drift else 'all_sensors')
    out.mkdir(parents=True, exist_ok=True)
    Xtr, Xval, Xte, y, ts, cols = prep(a.drop_drift)
    np.savez(out / 'meta.npz', y=y, ts=ts.values.astype('datetime64[ns]').astype('int64'), cols=np.array(cols))
    print('train', Xtr.shape, 'val', Xval.shape, 'test', Xte.shape)
    train_and_cache(out, Xtr, Xval, Xte, a.models, a.seeds, a.w, a.epochs)


def train_and_cache(out, Xtr, Xval, Xte, models, seeds, w_default, epochs, ok_tr=None, ok_val=None, model_kw=None):
    """ok_tr/ok_val: 시점별 정상 마스크(없으면 전체 정상). 이상 구간이 섞인 학습 기간에서 정상 윈도우만 학습."""
    dev = 'mps' if torch.backends.mps.is_available() else 'cpu'
    for name in models:
        for seed in seeds:
            t0 = time.time()
            if name == 'IF':
                m = IsolationForest(n_estimators=300, random_state=seed, n_jobs=-1).fit(Xtr if ok_tr is None else Xtr[ok_tr])
                # IF는 센서별 오차가 없음 → 스코어를 1열로 저장
                E_te, E_val = -m.score_samples(Xte)[:, None], -m.score_samples(Xval if ok_val is None else Xval[ok_val])[:, None]
            elif name == 'PCA':
                if seed != seeds[0]: continue                  # 결정적
                p = PCA(n_components=0.95, svd_solver='full').fit(Xtr if ok_tr is None else Xtr[ok_tr])
                rec = lambda X: (X - p.inverse_transform(p.transform(X))) ** 2
                E_te, E_val = rec(Xte), rec(Xval if ok_val is None else Xval[ok_val])
            else:
                w = 1 if name == 'MLP-AE' else w_default
                m = ae.fit(name, Xtr, Xval, w, epochs=epochs, seed=seed, device=dev, ok_tr=ok_tr, ok_val=ok_val, verbose=name.startswith('GDN'),
                           model_kw=(model_kw or {}).get(name))
                E_te = ae.per_sensor_error(m, Xte, w, dev)
                E_val = ae.per_sensor_error(m, Xval, w, dev, idx=ae.ok_windows(ok_val, w))
                if name == 'GDN' and seed == seeds[0]:             # 학습 그래프 저장 (토폴로지 일치도 분석용)
                    with torch.no_grad(): np.save(out / 'gdn_neighbors.npy', m.learned().cpu().numpy())
            np.savez(out / f'errors_{name}_s{seed}.npz', E_te=E_te, E_val=E_val)
            print(f'{name} seed{seed} done {time.time() - t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
