# -*- coding: utf-8 -*-
"""#2 보고서용 그림(한글 라벨) — 결과 캐시(errors_*.npz, metrics.json)에서 생성.

사용: python -m scripts.report_figs  → results/report/fig{1..4}.png
"""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve
from src.eval import to_ts, metrics
from scripts.analyze_wadi import SCORINGS, score
from scripts.analyze import runs_of

RES = Path(__file__).resolve().parents[1] / 'results'
OUT = RES / 'report'
B, I = 'raw-mean', 'norm-top5+smooth'
C = {'IF': '#1D9E75', 'PCA': '#7F77DD', 'MLP-AE': '#9aa0a6', 'Window-AE': '#EF9F27',
     'Conv-AE': '#D85A30', 'LSTM-AE': '#185FA5', 'GDN': '#B5487A', 'GDN-prior': '#6B3FA0'}
NAVY, ORANGE, RED, GREY = '#1F3A6B', '#EF9F27', '#D85A30', '#9aa0a6'
plt.rcParams.update({'font.family': ['Apple SD Gothic Neo', 'DejaVu Sans'], 'mathtext.fontset': 'dejavusans', 'axes.unicode_minus': False, 'font.size': 8,
                     'axes.spines.top': False, 'axes.spines.right': False, 'axes.titlesize': 8.5,
                     'axes.titleweight': 'bold', 'axes.titlelocation': 'left', 'legend.frameon': False})


def M(name): return json.load(open(RES / name / 'metrics.json'))
def v(rep, s, m, k='F1*'): return rep[s][m][k][0]
def meta(name): return np.load(RES / name / 'meta.npz', allow_pickle=True)


def sc(m, s): return SCORINGS[s] if m != 'IF' else dict(SCORINGS[s], norm=False)


def spans(mask):
    d = np.diff(np.r_[0, mask.astype(int), 0]); return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def shade(ax, ts, mask, color, label, alpha=0.3):
    for i, (a, b) in enumerate(spans(mask)):
        ax.axvspan(ts[a], ts[min(b, len(ts) - 1)], color=color, alpha=alpha, lw=0, label=label if i == 0 else None)


def logy(ax):
    ax.set_yscale('log')
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f'{x:g}'))
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())


def days(ax, hours=None):
    ax.xaxis.set_major_locator(matplotlib.dates.HourLocator(byhour=hours) if hours else matplotlib.dates.DayLocator())
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%m/%d %H시' if hours else '%m/%d'))


def save(fig, name):
    fig.savefig(OUT / name, dpi=220, bbox_inches='tight'); plt.close(fig); print('saved', OUT / name)


# ---------------------------------------------------------------- 그림 1: WADI 스코어 시계열 (진단)
def fig1():
    name = 'wadi/drift_filtered'; mt = meta(name); y, ts = mt['y'], to_ts(mt['ts'])
    runs = runs_of(RES / name); rep = M(name)
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 2.45), sharex=True)
    for ax, (m, s, t) in zip(axes, [('MLP-AE', B, '(a) 1차 기초 AE: 시점 단위 재구성, 단순 평균 오차'),
                                    ('LSTM-AE', I, '(b) 개선: LSTM-AE + 정규화 상위 5 센서 오차 + 인과 평활')]):
        st, sv = score(*runs[m][0], **sc(m, s))
        ax.plot(ts, st, lw=0.45, color=NAVY)
        ax.axhline(np.quantile(sv, 0.99), color=RED, ls='--', lw=0.9, label='운영 임계(정상 99%)')
        shade(ax, ts, y == 1, ORANGE, '공격 구간(라벨)', 0.35)
        logy(ax); days(ax, [0, 6, 12, 18]); ax.set_title(t + f'   ROC-AUC {v(rep, s, m, "ROC-AUC"):.3f} · F1 {v(rep, s, m):.3f}')
        ax.set_ylabel('이상 점수(log)')
    axes[0].legend(loc='upper left', ncol=2, fontsize=7)
    fig.tight_layout(h_pad=0.4); save(fig, 'fig1_wadi_timeline.png')


# ---------------------------------------------------------------- 그림 2: 모델 크기 vs 성능, ROC
def fig2():
    import torch
    from src.models.ae import build
    name = 'wadi/drift_filtered'; mt = meta(name); y = mt['y']; d = len(mt['cols'])
    W, E = M(name), M('epic'); runs = runs_of(RES / name)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 2.6), gridspec_kw=dict(width_ratios=[1.1, 1]))
    for m in ['MLP-AE', 'Window-AE', 'Conv-AE', 'LSTM-AE', 'GDN']:
        n = sum(p.numel() for p in build(m, d, 30).parameters())
        a1.scatter(n, v(W, I, m), s=36, color=C[m], zorder=3)
        a1.scatter(n, v(E, I, m), s=36, color=C[m], marker='^', zorder=3, alpha=0.6)
        a1.annotate(m, (n, v(W, I, m)), xytext=(5, 4), textcoords='offset points', fontsize=7)
    a1.axvspan(1e3, 1e5, color='#E8EDF6', zorder=0, label='배포 목표(≤100k)')
    a1.scatter([], [], color='k', s=20, label='WADI'); a1.scatter([], [], color='k', marker='^', s=20, alpha=0.6, label='EPIC')
    a1.set_xscale('log'); a1.set_xlim(8e3, 4e6); a1.set_xlabel('파라미터 수(log)'); a1.set_ylabel('F1(최적)')
    a1.set_title('(a) 모델 크기와 성능'); a1.legend(fontsize=6.5, loc='lower right')
    for m in ['IF', 'PCA', 'MLP-AE', 'Conv-AE', 'LSTM-AE', 'GDN']:
        s, _ = score(*runs[m][0], **sc(m, I)); fpr, tpr, _ = roc_curve(y, s)
        a2.plot(fpr, tpr, color=C[m], lw=1.1, label=f'{m} {v(W, I, m, "ROC-AUC"):.3f}')
    s, _ = score(*runs['MLP-AE'][0], **SCORINGS[B]); fpr, tpr, _ = roc_curve(y, s)
    a2.plot(fpr, tpr, color=GREY, lw=1, ls='--', label=f'1차 AE {v(W, B, "MLP-AE", "ROC-AUC"):.3f}')
    a2.plot([0, 1], [0, 1], ':', color='#cccccc', lw=0.8)
    a2.set(xlabel='오경보율(FPR)', ylabel='탐지율(TPR)'); a2.set_title('(b) WADI ROC (개선 스코어링, AUC)')
    a2.legend(fontsize=6.3, loc='lower right')
    fig.tight_layout(w_pad=1.5); save(fig, 'fig2_size_roc.png')


# ---------------------------------------------------------------- 그림 3: 데이터셋별 개선 효과 + 스코어링 단계별 ablation
def fig3():
    W, E, Fr, Fp = M('wadi/drift_filtered'), M('epic'), M('fmcs/raw'), M('fmcs/physics')
    AE = ['MLP-AE', 'Window-AE', 'Conv-AE', 'LSTM-AE']
    best = lambda r: max(AE, key=lambda m: v(r, I, m))
    rows = [('WADI', W, W, 'F1@q'), ('EPIC', E, E, 'F1@q'), ('FMCS\n(태그)', Fr, Fr, 'F1@qS'), ('FMCS\n(+물리 잔차)', Fp, Fr, 'F1@qS')]
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(7.4, 2.45), gridspec_kw=dict(width_ratios=[1.35, 1, 1]))
    x = np.arange(len(rows)); w = 0.2
    bars = [('1차 AE · 최적', lambda r, b, q: v(b, B, 'MLP-AE'), '#C9CED6'),
            ('1차 AE · 운영 임계', lambda r, b, q: v(b, B, 'MLP-AE', q), '#E6E8EC'),
            ('개선 · 최적', lambda r, b, q: v(r, I, best(r)), NAVY),
            ('개선 · 운영 임계', lambda r, b, q: v(r, I, best(r), q), '#6E8CC4')]
    for i, (lab, f, col) in enumerate(bars):
        hs = [f(r, b, q) for _, r, b, q in rows]
        a1.bar(x + (i - 1.5) * w, hs, w, color=col, label=lab, edgecolor='white', lw=0.3)
        if i == 2:
            for xi, h, (_, r, b, q) in zip(x, hs, rows):
                a1.text(xi + 0.5 * w, h + 0.02, f'{(h / v(b, B, "MLP-AE") - 1) * 100:+.0f}%', ha='center', fontsize=6.5, color=NAVY, fontweight='bold')
    a1.set_xticks(x, [r[0] for r in rows], fontsize=6.8); a1.set_ylim(0, 1.05); a1.set_ylabel('F1')
    a1.set_title('(a) 데이터셋별 F1: 1차 AE → 개선'); a1.legend(fontsize=5.8, ncol=2, loc='upper left', columnspacing=0.6, handlelength=1.2)
    steps = list(SCORINGS); lbl = ['단순\n평균', '+센서\n정규화', '+상위 5\n집계', '+인과\n평활']
    yw = meta('wadi/drift_filtered')['y']; runs = runs_of(RES / 'wadi/drift_filtered')
    f1 = lambda m, s: np.mean([metrics(yw, *score(Et, Ev, **SCORINGS[s]))['F1*'] for Et, Ev in runs[m]])
    for m in AE + ['PCA']:
        a2.plot(range(4), [f1(m, s) for s in steps], marker='o', ms=3, lw=1.2, color=C[m], label=m)
    a2.axhline(v(W, B, 'IF'), color=C['IF'], ls='--', lw=0.9, label='IF')
    a2.set_xticks(range(4), lbl, fontsize=6.5); a2.set_ylabel('F1(최적)')
    a2.set_title('(b) WADI 스코어링 단계별 효과'); a2.legend(fontsize=5.8, ncol=2, loc='lower right', columnspacing=0.6, handlelength=1.2)
    import torch
    from src.models.ae import build
    d = len(meta('wadi/drift_filtered')['cols'])
    for m in AE + ['GDN']:
        n = sum(p.numel() for p in build(m, d, 30).parameters())
        a3.scatter(n, v(W, I, m), s=26, color=C[m], zorder=3)
        a3.scatter(n, v(E, I, m), s=26, color=C[m], marker='^', zorder=3, alpha=0.55)
        a3.annotate(m, (n, v(W, I, m)), xytext=(-4, 5) if m == 'MLP-AE' else (4, 3), ha='right' if m == 'MLP-AE' else 'left',
                    textcoords='offset points', fontsize=6)
    a3.axvspan(1e3, 1e5, color='#E8EDF6', zorder=0, label='배포 목표 ≤100k')
    a3.scatter([], [], color='k', s=14, label='WADI'); a3.scatter([], [], color='k', marker='^', s=14, alpha=0.55, label='EPIC')
    a3.set_xscale('log'); a3.set_xlim(8e3, 6e6); a3.set_xlabel('파라미터 수(log)', fontsize=7); a3.set_ylabel('F1(최적)')
    a3.set_title('(c) 모델 크기와 성능'); a3.legend(fontsize=5.8, loc='lower right', handlelength=1)
    fig.tight_layout(w_pad=0.8); save(fig, 'fig3_gain_ablation.png')


# ---------------------------------------------------------------- 그림 4: FMCS 사례 + 국소화
def qS_threshold(sv, w):
    from src.data import fmcs
    from src.models.ae import ok_windows
    Wd = fmcs.load_wide(); lab = fmcs.labels(index=Wd.index).fillna(0)
    day = (Wd.index.normalize() - Wd.index[0].normalize()).days; nd = day.max() + 1
    off = fmcs.off_normal_config(Wd, fmcs.tag_table(), day < nd - 6)
    va = (day >= nd - 6) & (day < nd - 4)
    keep = ~off[va][ok_windows(~lab['anomaly'].values[va].astype(bool), w)]
    keep = keep[-len(sv):] if len(keep) >= len(sv) else np.ones(len(sv), bool)
    return np.quantile(sv[keep], 0.99)


def fig4():
    mt = meta('fmcs/physics'); y, op, ts = mt['y'], mt['op'], to_ts(mt['ts'])
    Fr, Fp = M('fmcs/raw'), M('fmcs/physics')
    rr, rp = runs_of(RES / 'fmcs/raw'), runs_of(RES / 'fmcs/physics')
    fig = plt.figure(figsize=(7.2, 2.6)); gs = fig.add_gridspec(2, 2, width_ratios=[2.6, 1], hspace=0.5, wspace=0.28)
    for i, (runs, rep, m, s, w, t) in enumerate([(rr, Fr, 'MLP-AE', B, 1, '(a) 1차 기초 AE(태그만)'),
                                                 (rp, Fp, 'Window-AE', I, 15, '(b) 개선: Window-AE + 물리 잔차 + 개선 스코어링')]):
        ax = fig.add_subplot(gs[i, 0])
        st, sv = score(*runs[m][0], **sc(m, s))
        ax.plot(ts, st, lw=0.45, color=NAVY)
        ax.axhline(qS_threshold(sv, w), color=RED, ls='--', lw=0.9, label='운영 임계(평상 구성 99%)')
        shade(ax, ts, y == 1, ORANGE, '이상 이벤트', 0.4); shade(ax, ts, (op == 1) & (y == 0), GREY, '정상 운전 이벤트(개폐·절체)', 0.3)
        logy(ax); days(ax); ax.set_title(t + f'   F1 {v(rep, s, m):.3f}', fontsize=7.8)
        ax.set_ylabel('점수(log)', fontsize=7)
        if i == 0:
            ax.legend(loc='lower left', bbox_to_anchor=(0, 1.13), ncol=3, fontsize=6.2, borderaxespad=0)
            ax.tick_params(labelbottom=False)
    ax = fig.add_subplot(gs[:, 1])
    W, E = M('wadi/drift_filtered'), M('epic')
    ds = [('WADI', W['localization']['LSTM-AE']), ('EPIC', E['localization']['MLP-AE']), ('FMCS', Fp['localization']['Window-AE'])]
    x = np.arange(3); w = 0.26
    for j, (k, col) in enumerate([('top1', '#C9CED6'), ('top3', '#6E8CC4'), ('top5', NAVY)]):
        hs = [d[k] * 100 for _, d in ds]
        ax.bar(x + (j - 1) * w, hs, w, color=col, label=f'상위 {k[-1]}')
        if k == 'top3':
            for xi, h in zip(x, hs): ax.text(xi, h + 2, f'{h:.0f}', ha='center', fontsize=6.5, color=NAVY, fontweight='bold')
    ax.set_xticks(x, [d[0] for d in ds]); ax.set_ylim(0, 105); ax.set_ylabel('원인 센서 적중률(%)')
    ax.set_title('(c) 원인 센서 국소화'); ax.legend(fontsize=6.3, loc='upper left', ncol=3, columnspacing=0.6, handlelength=1)
    save(fig, 'fig4_fmcs_loc.png')


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    for f in (fig1, fig3, fig4): f()
