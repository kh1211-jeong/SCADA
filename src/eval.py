# -*- coding: utf-8 -*-
"""평가 지표 + 스코어 후처리."""
import numpy as np
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_fscore_support, precision_recall_curve


def normalize_errors(E, Eval, eps=1e-2):
    """센서별 robust 정규화: (e - median_val) / (IQR_val + eps). 센서 간 스케일 차이 제거 (GDN 방식)."""
    med = np.median(Eval, 0)
    iqr = np.quantile(Eval, 0.75, 0) - np.quantile(Eval, 0.25, 0)
    return (E - med) / (iqr + eps)


def aggregate(E, how='mean', k=None):
    if how == 'mean': return E.mean(1)
    if how == 'max': return E.max(1)
    if how == 'topk': return np.sort(E, 1)[:, -k:].mean(1)
    raise ValueError(how)


def smooth(s, k):
    if k <= 1: return s
    c = np.cumsum(np.r_[np.zeros(k), s])            # 인과적 이동평균 (과거 k 시점)
    out = (c[k:] - c[:-k]) / k
    out[:k - 1] = s[:k - 1]
    return out


def point_adjust(pred, y):
    """PA: 공격 구간 중 한 시점이라도 탐지하면 구간 전체 탐지로 간주 (문헌 관례, 낙관적)."""
    pred = pred.copy()
    d = np.diff(np.r_[0, y, 0]); s = np.where(d == 1)[0]; e = np.where(d == -1)[0]
    for a, b in zip(s, e):
        if pred[a:b].any(): pred[a:b] = 1
    return pred


def prf(y, pred):
    p, r, f, _ = precision_recall_fscore_support(y, pred, average='binary', zero_division=0)
    return p, r, f


def metrics(y, s, s_val, q=0.99):
    """s: 테스트 스코어, s_val: 정상 검증 스코어(임계 산정용)."""
    out = {'ROC-AUC': roc_auc_score(y, s), 'PR-AUC': average_precision_score(y, s)}
    thr = np.quantile(s_val, q)
    out['P@q'], out['R@q'], out['F1@q'] = prf(y, (s > thr).astype(int))
    pr, rc, th = precision_recall_curve(y, s)
    f = 2 * pr * rc / np.maximum(pr + rc, 1e-12)
    i = np.nanargmax(f[:-1]); out['P*'], out['R*'], out['F1*'] = pr[i], rc[i], f[i]
    out['thr*'] = th[i]
    out['F1-PA*'] = prf(y, point_adjust((s >= th[i]).astype(int), y))[2]
    # 탐지된 공격 구간 수 (best 임계 기준)
    d = np.diff(np.r_[0, y, 0]); a_, b_ = np.where(d == 1)[0], np.where(d == -1)[0]
    pred = s >= th[i]
    out['events'] = f'{sum(pred[a:b].any() for a, b in zip(a_, b_))}/{len(a_)}'
    return out


def to_ts(arr):
    """meta.npz 정수 타임스탬프 → DatetimeIndex (구버전 캐시는 µs 단위로 저장됨)."""
    import pandas as pd
    arr = np.asarray(arr)
    return pd.to_datetime(arr, unit='ns' if arr.max() > 1e17 else 'us')
