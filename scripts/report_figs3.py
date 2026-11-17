# -*- coding: utf-8 -*-
"""#3 보고서용 그림(한글) — results/report3/analysis.json + 오차 캐시에서 생성.

사용: FMCS_DATA=fmcs_synth_v2 python -m scripts.report_figs3  → results/report3/fig{1,2,3}.png
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scripts.report_figs import NAVY, ORANGE, RED, GREY, logy, save as _save
from scripts.analyze3 import DS, RES

OUT = RES / 'report3'
A = json.load(open(OUT / 'analysis.json'))
COL = {'base': '#C9CED6', 'ae': NAVY, 'gdn': '#B5487A', 'ens': '#6E8CC4'}
LAB = {'base': '1차 기초 AE', 'ae': '개선 AE', 'gdn': 'GDN(최적 변형)', 'ens': 'AE+GDN 앙상블'}
DSN = {'wadi': 'WADI', 'epic': 'EPIC', 'fmcs': 'FMCS 트렌드'}
TYPE_KO = {'ct_drift': 'CT 드리프트', 'meter_offset': '전력계 오프셋', 'pf_sign_flip': 'PF 부호 반전',
           'sensor_stuck': '값 고착', 'spike_burst': '전류 스파이크', 'ltr_overheat': '변압기 과열',
           'oltc_hunting': 'OLTC 헌팅', 'voltage_sag': '순간전압강하', 'hidden_load': '미계량 부하(KCL)',
           'pt_drift': 'PT 드리프트'}


def save(fig, name):
    fig.savefig(OUT / name, dpi=220, bbox_inches='tight'); plt.close(fig); print('saved', OUT / name)


# ---------------------------------------------------------------- 그림 1: 데이터셋별 성능 + 향상률
def fig1():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 2.5), gridspec_kw=dict(width_ratios=[1.25, 1]))
    keys = ['wadi', 'epic', 'fmcs']; x = np.arange(3); w = 0.2
    for i, c in enumerate(['base', 'ae', 'gdn', 'ens']):
        hs = [A[k][c]['F1op'] for k in keys]
        a1.bar(x + (i - 1.5) * w, hs, w, color=COL[c], label=LAB[c], edgecolor='white', lw=0.3)
    a1.set_xticks(x, [DSN[k] for k in keys]); a1.set_ylim(0, 1); a1.set_ylabel('F1 (운영 임계)')
    a1.set_title('(a) 운영 임계 F1: 모델 계열별'); a1.legend(fontsize=6, ncol=2, loc='upper left', columnspacing=0.6, handlelength=1.2)
    mets = [('ROC-AUC', 'ROC-AUC'), ('F1*', 'F1(최적)'), ('F1op', 'F1(운영)'), ('event_recall', '이벤트 탐지율')]
    ww = 0.26
    for j, k in enumerate(keys):
        best = max(['ae', 'gdn', 'ens'], key=lambda c: A[k][c]['F1op'])
        g = [(A[k][best][m] / max(A[k]['base'][m], 1e-9) - 1) * 100 for m, _ in mets]
        bars = a2.bar(np.arange(4) + (j - 1) * ww, g, ww, color=['#9aa0a6', '#6E8CC4', NAVY][j], label=DSN[k])
        for b, v in zip(bars, g):
            a2.text(b.get_x() + b.get_width() / 2, v + (2 if v >= 0 else -8), f'{v:+.0f}', ha='center', fontsize=5.6)
    a2.axhline(0, color='k', lw=0.6); a2.set_xticks(range(4), [l for _, l in mets], fontsize=6.8)
    a2.set_ylabel('기초 대비 향상률(%)'); a2.set_title('(b) 최종 구성의 지표별 향상률'); a2.legend(fontsize=6, loc='upper left')
    fig.tight_layout(w_pad=1.2); save(fig, 'fig1_overall.png')


# ---------------------------------------------------------------- 그림 2: 단계별 ablation + 유형별 탐지율
def fig2():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 2.75), gridspec_kw=dict(width_ratios=[1.1, 1]))
    ab = A['ablation']; x = np.arange(len(ab))
    a1.plot(x, [s['F1*'] for s in ab], marker='o', ms=3.5, color=NAVY, lw=1.4, label='F1(최적)')
    a1.plot(x, [s['F1op'] for s in ab], marker='s', ms=3.5, color=ORANGE, lw=1.4, label='F1(운영 임계)')
    ax2 = a1.twinx(); ax2.bar(x, [s.get('FAR_op', 0) * 100 for s in ab], 0.5, color=GREY, alpha=0.35, label='운전 이벤트 오경보율')
    ax2.set_ylabel('운전 이벤트 오경보율(%)', fontsize=6.5); ax2.tick_params(labelsize=6.5); ax2.spines['right'].set_visible(True)
    a1.set_zorder(ax2.get_zorder() + 1); a1.patch.set_visible(False)
    for i, s in enumerate(ab): a1.text(i, s['F1op'] - 0.06, f"{s['F1op']:.2f}", ha='center', fontsize=5.6, color=ORANGE)
    SHORT = {'1차 기초 AE': '1차 AE', '+시계열 윈도우': '+윈도우', '+정규화·상위k·평활': '+정규화·top-k', '+물리 잔차': '+물리 잔차',
             '+KCL 잔차': '+KCL 잔차', '+강건 스케일링': '+강건 스케일', '+운전 컨텍스트': '+운전 컨텍스트', '+GDN 앙상블': '+GDN 앙상블'}
    a1.set_xticks(x, [SHORT.get(s['step'], s['step']) for s in ab], fontsize=6, rotation=35, ha='right', rotation_mode='anchor')
    a1.set_ylim(0, 1); a1.set_ylabel('F1'); a1.set_title('(a) FMCS 단계별 누적 효과(한 요소씩 추가)')
    h1, l1 = a1.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    a1.legend(h1 + h2, l1 + l2, fontsize=5.8, loc='upper left')
    T = A['fmcs_types']; ts = sorted(T, key=lambda t: T[t]['ens'] - T[t]['base'])
    M = np.array([[T[t][c] for c in ('base', 'ae', 'gdn', 'ens')] for t in ts])
    im = a2.imshow(M, cmap='Blues', vmin=0, vmax=1, aspect='auto')
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            a2.text(j, i, f'{M[i, j] * 100:.0f}', ha='center', va='center', fontsize=6, color='white' if M[i, j] > 0.6 else 'k')
    a2.set_xticks(range(4), ['1차 AE', '개선 AE', 'GDN', '앙상블'], fontsize=6.5)
    a2.set_yticks(range(len(ts)), [f"{TYPE_KO.get(t, t)} ({T[t]['n']})" for t in ts], fontsize=6.3)
    a2.set_title('(b) FMCS 이상 유형별 이벤트 탐지율(%)'); a2.spines[:].set_visible(False)
    fig.tight_layout(w_pad=1.0); save(fig, 'fig2_ablation_types.png')


# ---------------------------------------------------------------- 그림 3: 관계형 이상 사례 (hidden_load, pt_drift)
def fig3():
    from src.data import fmcs
    from src.eval import normalize_errors
    kcl, raw = DS('fmcs_v2/kcl_rs', 'fmcs'), DS('fmcs_v2/raw', 'fmcs')
    ev = fmcs.events(); ts = kcl.ts
    Wd = fmcs.load_wide()
    am, gm = A['fmcs']['ae_model'], A['fmcs']['gdn_model']
    fig, axes = plt.subplots(2, 2, figsize=(7.4, 3.3), sharex='col')
    for c, typ in enumerate(['hidden_load', 'ct_drift']):
        e = ev[(ev.type == typ) & (ev.start >= ts[0]) & (ev.end <= ts[-1])]
        if e.empty: continue
        e = e.iloc[int(np.argmax((e.end - e.start).values))]
        a = int(ts.searchsorted(e.start - pd.Timedelta('3h'))); b = int(ts.searchsorted(e.end + pd.Timedelta('2h')))
        t = ts[a:b]; n = e.target.rsplit('_', 1)[0] if typ == 'ct_drift' else e.target
        ax = axes[0, c]
        ax.plot(t, Wd.loc[t, f'{n}_POWER'], color=GREY, lw=0.8, label=f'{n} 전력 P (kW)')
        if typ == 'ct_drift':
            ax2 = ax.twinx(); ax2.plot(t, Wd.loc[t, f'{n}_CURRENT'], color=NAVY, lw=0.8, label='전류 I (A)'); ax2.spines['right'].set_visible(True)
            ax2.tick_params(labelsize=6); ax2.legend(fontsize=5.8, loc='upper right')
        ax.axvspan(e.start, e.end, color=ORANGE, alpha=0.25, lw=0)
        ax.set_title(f"({'ab'[c]}) {TYPE_KO[typ]} — 원신호 ({e.start:%m/%d})", fontsize=7.8); ax.tick_params(labelsize=6)
        ax.legend(fontsize=5.8, loc='upper left')
        ax = axes[1, c]
        for ds, m, lab, col in [(raw, 'MLP-AE', '1차 AE(태그만)', GREY), (kcl, am, f'개선 {am}', NAVY), (kcl, gm, gm, '#B5487A')]:
            Z = normalize_errors(*ds.runs[m][0])
            j = [i for i, cc in enumerate(ds.cols) if cc.startswith(n + '_')]
            ax.plot(t, np.clip(Z[a:b][:, j].max(1), 1e-2, None), lw=0.8, color=col, label=lab)
        ax.axvspan(e.start, e.end, color=ORANGE, alpha=0.25, lw=0); logy(ax)
        ax.set_title(f"({'cd'[c]}) 해당 설비 피처의 정규화 오차(최대)", fontsize=7.8); ax.tick_params(labelsize=6)
        ax.legend(fontsize=5.8, loc='upper left'); ax.xaxis.set_major_locator(matplotlib.dates.HourLocator(interval=2)); ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H시'))
    fig.tight_layout(h_pad=0.5, w_pad=1.0); save(fig, 'fig3_cases.png')


if __name__ == '__main__':
    for f in (fig1, fig2, fig3): f()
