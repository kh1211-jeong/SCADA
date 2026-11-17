# -*- coding: utf-8 -*-
"""run_wadi 결과(센서별 오차 캐시) → 지표 표 / 스코어링 ablation / 국소화 / 그림.

사용: python -m scripts.analyze_wadi [drift_filtered|all_sensors]
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, precision_recall_curve
from src.eval import to_ts, normalize_errors, aggregate, smooth, metrics
from src.data.wadi import attack_table

import sys
OUT = Path(__file__).resolve().parents[1] / 'results' / 'wadi' / (sys.argv[1] if len(sys.argv) > 1 else 'drift_filtered')
MODELS = ['IF', 'PCA', 'MLP-AE', 'Window-AE', 'Conv-AE', 'LSTM-AE']
COLORS = {'IF': '#1D9E75', 'PCA': '#7F77DD', 'MLP-AE': '#9aa0a6', 'Window-AE': '#EF9F27',
          'Conv-AE': '#D85A30', 'LSTM-AE': '#185FA5'}
# 스코어링 방식 (고정 grid — 테스트로 튜닝하지 않고 전부 보고)
SCORINGS = {
    'raw-mean':          dict(norm=False, how='mean', k=None, sm=1),   # 1차 발표 방식
    'norm-mean':         dict(norm=True,  how='mean', k=None, sm=1),
    'norm-top5':         dict(norm=True,  how='topk', k=5,    sm=1),
    'norm-top5+smooth':  dict(norm=True,  how='topk', k=5,    sm=6),   # 60초 인과 이동평균
}
FINAL = 'norm-top5+smooth'


def score(E_te, E_val, norm, how, k, sm):
    if E_te.shape[1] == 1:                       # IF: 센서별 오차 없음
        return smooth(E_te[:, 0], sm), smooth(E_val[:, 0], sm)
    if norm:
        E_te, E_val = normalize_errors(E_te, E_val), normalize_errors(E_val, E_val)
    return smooth(aggregate(E_te, how, k), sm), smooth(aggregate(E_val, how, k), sm)


def load_errors(name):
    out = []
    for f in sorted(OUT.glob(f'errors_{name}_s*.npz')):
        z = np.load(f); out.append((z['E_te'], z['E_val']))
    return out


def evaluate(y, runs, sc):
    rows = [metrics(y, *score(Et, Ev, **sc)) for Et, Ev in runs]
    df = pd.DataFrame(rows)
    num = df.select_dtypes('number')
    return num.mean(), num.std().fillna(0), rows


def localization(E_te, E_val, table, cols):
    """공격 구간 내 정규화 오차 평균으로 센서 순위 → 실제 공격 지점의 최고 순위."""
    Z = normalize_errors(E_te, E_val)
    res = []
    for a, b, pts in table:
        if not pts: continue
        order = np.argsort(-Z[a:b].mean(0))
        rank = {cols[j]: r + 1 for r, j in enumerate(order)}
        best = min(rank[p] for p in pts if p in rank)
        res.append({'start': a, 'points': pts, 'best_rank': best,
                    'top3': [cols[j] for j in order[:3]]})
    return res


def main():
    meta = np.load(OUT / 'meta.npz', allow_pickle=True)
    y, cols = meta['y'], list(meta['cols'])
    ts = to_ts(meta['ts'])
    table = attack_table(y, ts)
    runs = {m: load_errors(m) for m in MODELS}
    report = {}

    # (1) 모델 × 스코어링 표
    lines = []
    for sname, sc in SCORINGS.items():
        for m in MODELS:
            if not runs[m]: continue
            if m == 'IF' and sc['norm']:
                sc_ = dict(sc, norm=False)
            else:
                sc_ = sc
            mu, sd, rows = evaluate(y, runs[m], sc_)
            report.setdefault(sname, {})[m] = {k: [round(mu[k], 4), round(sd[k], 4)] for k in mu.index}
            report[sname][m]['events'] = [r['events'] for r in rows]
            lines.append([sname, m, len(runs[m])] + [f'{mu[k]:.3f}±{sd[k]:.3f}' for k in
                         ['ROC-AUC', 'PR-AUC', 'F1@q', 'P*', 'R*', 'F1*', 'F1-PA*']] + [rows[0]['events']])
    tab = pd.DataFrame(lines, columns=['scoring', 'model', 'n_seed', 'ROC-AUC', 'PR-AUC', 'F1@q99',
                                       'P*', 'R*', 'F1*', 'F1-PA*', 'events'])
    print(tab.to_string(index=False))
    tab.to_csv(OUT / 'table_all.csv', index=False)

    # (2) 국소화 (seed0, AE 계열 + PCA)
    loc = {}
    for m in ['PCA', 'MLP-AE', 'Window-AE', 'Conv-AE', 'LSTM-AE']:
        if not runs[m]: continue
        allr = [localization(Et, Ev, table, cols) for Et, Ev in runs[m]]
        ranks = np.array([[r['best_rank'] for r in rr] for rr in allr])
        loc[m] = {'top1': float((ranks <= 1).mean()), 'top3': float((ranks <= 3).mean()),
                  'top5': float((ranks <= 5).mean()), 'median_rank': float(np.median(ranks)),
                  'detail_seed0': allr[0]}
        print(f'[loc] {m}: top1={loc[m]["top1"]:.2f} top3={loc[m]["top3"]:.2f} '
              f'top5={loc[m]["top5"]:.2f} median_rank={loc[m]["median_rank"]:.1f}  (D={len(cols)})')
    report['localization'] = loc
    json.dump(report, open(OUT / 'metrics.json', 'w'), indent=1, ensure_ascii=False, default=str)

    figures(y, ts, runs, table, cols, report, loc)


def figures(y, ts, runs, table, cols, report, loc):
    plt.rcParams.update({'axes.spines.top': False, 'axes.spines.right': False, 'font.size': 9})
    best = 'LSTM-AE'
    segs = [(a, b) for a, b, _ in table]

    # Fig A: 스코어 타임라인 (1차 방식 MLP-AE vs 개선 LSTM-AE)
    fig, axes = plt.subplots(2, 1, figsize=(13, 5.2), sharex=True)
    for ax, (m, sname, title) in zip(axes, [('MLP-AE', 'raw-mean', 'Baseline: point-wise AE, raw MSE (1st presentation)'),
                                            (best, FINAL, f'Improved: {best}, normalized top-5 error + smoothing')]):
        Et, Ev = runs[m][0]
        s, sv = score(Et, Ev, **SCORINGS[sname])
        thr = report[sname][m]['thr*'][0]
        ax.plot(ts, s, lw=0.6, color=COLORS[m])
        ax.axhline(thr, color='#D85A30', ls='--', lw=1, label='best-F1 threshold')
        for i, (a, b) in enumerate(segs):
            ax.axvspan(ts[a], ts[min(b, len(ts) - 1)], color='#EF9F27', alpha=0.3, lw=0,
                       label='attack (label)' if i == 0 else None)
        ax.set_yscale('log'); ax.set_title(title, fontweight='bold', loc='left'); ax.legend(loc='upper right', fontsize=8)
        ax.set_ylabel('anomaly score (log)')
    plt.tight_layout(); plt.savefig(OUT / 'fig_timeline.png', dpi=180); plt.close()

    # Fig B: ROC / PR (최종 스코어링)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))
    for m in MODELS:
        if not runs[m]: continue
        sc = SCORINGS[FINAL] if m != 'IF' else dict(SCORINGS[FINAL], norm=False)
        s, _ = score(*runs[m][0], **sc)
        fpr, tpr, _ = roc_curve(y, s); pr, rc, _ = precision_recall_curve(y, s)
        r = report[FINAL][m]
        a1.plot(fpr, tpr, color=COLORS[m], lw=1.6, label=f'{m} (AUC={r["ROC-AUC"][0]:.3f})')
        a2.plot(rc, pr, color=COLORS[m], lw=1.6, label=f'{m} (AP={r["PR-AUC"][0]:.3f})')
    a1.plot([0, 1], [0, 1], ':', color='#9aa0a6'); a1.set(xlabel='FPR', ylabel='TPR', title='ROC — WADI')
    a2.axhline(y.mean(), ls=':', color='#9aa0a6'); a2.set(xlabel='Recall', ylabel='Precision', title='Precision-Recall — WADI')
    a1.legend(fontsize=8); a2.legend(fontsize=8)
    plt.tight_layout(); plt.savefig(OUT / 'fig_roc_pr.png', dpi=180); plt.close()

    # Fig C: ablation bar (F1*, 모델 × 스코어링)
    fig, ax = plt.subplots(figsize=(11, 4))
    ms = [m for m in MODELS if runs[m] and m != 'IF']
    W = 0.8 / len(SCORINGS)
    for i, sname in enumerate(SCORINGS):
        v = [report[sname][m]['F1*'][0] for m in ms]; e = [report[sname][m]['F1*'][1] for m in ms]
        ax.bar(np.arange(len(ms)) + i * W, v, W, yerr=e, capsize=2, label=sname,
               color=plt.cm.Blues(0.35 + 0.18 * i))
    ax.axhline(report['raw-mean']['IF']['F1*'][0], color=COLORS['IF'], ls='--', lw=1, label='Isolation Forest')
    ax.set_xticks(np.arange(len(ms)) + W * (len(SCORINGS) - 1) / 2, ms)
    ax.set_ylabel('best F1 (mean ± std, 3 seeds)'); ax.set_title('Architecture × scoring ablation — WADI', fontweight='bold')
    ax.legend(fontsize=8, ncol=3)
    plt.tight_layout(); plt.savefig(OUT / 'fig_ablation.png', dpi=180); plt.close()

    # Fig D: 국소화 예시 히트맵 (LSTM-AE, 공격 구간별 상위 센서)
    if best in loc:
        Z = normalize_errors(*runs[best][0])
        det = loc[best]['detail_seed0']
        top = sorted({c for r in det for c in r['top3']} | {p for r in det for p in r['points'] if p in cols})
        idx = [cols.index(c) for c in top]
        M = np.array([Z[r['start']:r['start'] + 30, idx].mean(0) for r in det])
        fig, ax = plt.subplots(figsize=(13, 4.8))
        im = ax.imshow(np.log1p(np.clip(M, 0, None)), aspect='auto', cmap='Blues')
        for i, r in enumerate(det):
            for p in r['points']:
                if p in top: ax.add_patch(plt.Rectangle((top.index(p) - .5, i - .5), 1, 1, fill=False, ec='#D85A30', lw=2))
        ax.set_xticks(range(len(top)), top, rotation=70, fontsize=7)
        ax.set_yticks(range(len(det)), [f'{str(ts[r["start"]])[5:16]}  (rank {r["best_rank"]})' for r in det], fontsize=7)
        ax.set_title(f'Root-cause localization — {best} normalized error per sensor (red box = true attack point)',
                     fontweight='bold', loc='left')
        plt.colorbar(im, label='log(1+normalized error)')
        plt.tight_layout(); plt.savefig(OUT / 'fig_localization.png', dpi=180); plt.close()
    print('figures saved to', OUT)


if __name__ == '__main__':
    main()
