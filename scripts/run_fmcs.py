# -*- coding: utf-8 -*-
"""FMCS 트렌드(1분): IF / PCA / AE 계열 / GDN 계열 학습 → 센서별 오차 캐시.

분할(fmcs.split_masks): v1 = 마지막 4일 평가·그 앞 2일 검증, v2 = 마지막 10일 평가·그 앞 4일 검증, 나머지 학습.
학습/검증 기간의 anomaly 라벨 구간은 학습에서 제외(정상만 학습). operational(트립/정비/ATS)·data_quality는
정상 운전 변동으로 학습에 포함.

피처 (--feat):
  raw       태그만
  physics   + 설비 내부 물리 잔차 (P − √3·V·I·PF)
  kcl       + 물리 잔차 + 설비 간 KCL 잔차 (상위 P − 하위 계량 P 합)

GDN 변형: GDN(학습 그래프), GDN-prior(토폴로지 고정), GDN-hybrid(토폴로지 ∪ 학습 top-k),
          GDN-dyn(hybrid + 이웃 STATUS 개방 시 어텐션 제외)

사용: python -m scripts.run_fmcs --feat physics            (v1, 결과 results/fmcs/physics)
      FMCS_DATA=fmcs_synth_v2 python -m scripts.run_fmcs --feat kcl   (v2, 결과 results/fmcs_v2/kcl)
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from src.data import fmcs
from src.models import ae
from scripts.run_wadi import train_and_cache

RES = Path(__file__).resolve().parents[1] / 'results'
OUT = RES / ('fmcs_v2' if fmcs.ROOT.name == 'fmcs_synth_v2' else 'fmcs')
GDNS = ['GDN', 'GDN-prior', 'GDN-hybrid', 'GDN-dyn']


def prep(feat, scale='minmax'):
    W = fmcs.load_wide()
    tags = fmcs.tag_table()
    W = W.ffill().bfill()
    X = W
    if feat in ('physics', 'kcl'):
        X = X.join(fmcs.physics_residuals(W, tags))
    if feat == 'kcl':
        X = X.join(fmcs.kcl_residuals(W, tags))
    lab = fmcs.labels(index=W.index).fillna(0)
    tr, va, te = fmcs.split_masks(W.index)
    keep = X[tr].std() > 0
    X = X.loc[:, keep]
    anom = lab['anomaly'].values.astype(bool)
    if scale == 'robust':      # 분위수 기반: 개폐 과도(분 평균 왜곡) 이상치가 스케일을 부풀리지 않도록
        Xn = X[tr & ~anom]
        lo, rng = Xn.quantile(0.5), Xn.quantile(0.995) - Xn.quantile(0.005)
        rng = rng.where(rng > 1e-9, (Xn.max() - Xn.min()).where(Xn.max() > Xn.min(), 1.0))
        st = X.columns.str.endswith('_STATUS')            # 개폐 상태는 0/1 그대로 (GDN-dyn 게이팅 기준 0.5)
        lo[st], rng[st] = 0.0, 1.0
        A = ((X - lo) / rng).clip(-10, 10).values.astype('float32')
    else:                      # 1차 방식 Min-Max
        lo, hi = X[tr].min(), X[tr].max()
        rng = (hi - lo).where(hi - lo > 0, 1.0)
        A = ((X - lo) / rng).clip(-5, 5).values.astype('float32')
    return dict(Xtr=A[tr], Xval=A[va], Xte=A[te], ok_tr=~anom[tr], ok_val=~anom[va],
                y=anom[te].astype(int), op=lab['operational'].values[te].astype(int),
                dq=lab['data_quality'].values[te].astype(int), ts=W.index[te], cols=list(X.columns))


def gdn_kwargs(cols, models):
    from src.models.gdn import topology_neighbors, status_index
    tags = fmcs.tag_table()
    nb = topology_neighbors(cols, tags, pd.read_csv(fmcs.ROOT / 'topology_edges.csv'))
    print('topology prior: mean degree %.1f' % (nb >= 0).sum(1).mean(), flush=True)
    kw = {'GDN-prior': {'neighbors': nb},
          'GDN-hybrid': {'neighbors': nb, 'hybrid': True, 'k': 8},
          'GDN-dyn': {'neighbors': nb, 'hybrid': True, 'k': 8, 'status_idx': status_index(cols, nb, tags)}}
    return {m: kw[m] for m in models if m in kw}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--feat', choices=['raw', 'physics', 'kcl'], default='raw')
    ap.add_argument('--physics', action='store_true', help='(구버전 호환) --feat physics 와 같음')
    ap.add_argument('--scale', choices=['minmax', 'robust'], default='minmax')
    ap.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2])
    ap.add_argument('--w', type=int, default=15)                       # 15분 윈도우
    ap.add_argument('--models', nargs='+', default=['IF', 'PCA'] + list(ae.MODELS))
    ap.add_argument('--epochs', type=int, default=60)
    a = ap.parse_args()
    feat = 'physics' if a.physics else a.feat
    d = prep(feat, a.scale)
    out = OUT / (feat + ('_rs' if a.scale == 'robust' else ''))
    out.mkdir(parents=True, exist_ok=True)
    np.savez(out / 'meta.npz', y=d['y'], op=d['op'], dq=d['dq'], ts=d['ts'].values.astype('datetime64[ns]').astype('int64'),
             cols=np.array(d['cols']), root=fmcs.ROOT.name)
    print('train', d['Xtr'].shape, 'val', d['Xval'].shape, 'test', d['Xte'].shape, 'anomaly ratio(test) %.3f' % d['y'].mean(), flush=True)
    kw = gdn_kwargs(d['cols'], a.models) if any(m in a.models for m in GDNS[1:]) else {}
    train_and_cache(out, d['Xtr'], d['Xval'], d['Xte'], a.models, a.seeds, a.w, a.epochs, d['ok_tr'], d['ok_val'], kw)


if __name__ == '__main__':
    main()
