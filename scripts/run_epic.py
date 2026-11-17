# -*- coding: utf-8 -*-
"""EPIC 2021 (2초): 정상 학습 → 전력 이상 주입 테스트. IF / PCA / AE 계열 오차 캐시.

사용: python -m scripts.run_epic
"""
import argparse, json
from pathlib import Path
import numpy as np
from src.data import epic
from src.models import ae
from scripts.run_wadi import train_and_cache

OUT = Path(__file__).resolve().parents[1] / 'results' / 'epic'


def boundary_ok(lens):
    """파일 경계를 걸치는 윈도우 제외용: 각 파일 첫 시점을 False."""
    ok = np.ones(sum(lens), bool); ok[np.cumsum([0] + lens[:-1])] = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2])
    ap.add_argument('--w', type=int, default=30)                       # 60초 윈도우
    ap.add_argument('--models', nargs='+', default=['IF', 'PCA'] + list(ae.MODELS))
    ap.add_argument('--epochs', type=int, default=60)
    a = ap.parse_args()
    (Xtr, Xva, Xte), (lens_tr, lens_va, lens_te) = epic.split()
    Xte, y, ev = epic.inject(Xte, Xtr, np.random.default_rng(0))
    lo, hi = Xtr.min(), Xtr.max(); rng = (hi - lo).where(hi - lo > 0, 1.0)
    sc = lambda X: ((X - lo) / rng).clip(-5, 5).values.astype('float32')
    OUT.mkdir(parents=True, exist_ok=True)
    cols = list(Xtr.columns)
    np.savez(OUT / 'meta.npz', y=y, cols=np.array(cols), lens_te=np.array(lens_te))
    json.dump([[int(s), int(e), t, c] for s, e, t, c in ev], open(OUT / 'events.json', 'w'), indent=0)
    print('train', Xtr.shape, 'val', Xva.shape, 'test', Xte.shape, 'anomaly %.3f' % y.mean(), flush=True)
    train_and_cache(OUT, sc(Xtr), sc(Xva), sc(Xte), a.models, a.seeds, a.w, a.epochs,
                    boundary_ok(lens_tr), boundary_ok(lens_va))


if __name__ == '__main__':
    main()
