# -*- coding: utf-8 -*-
"""#4 보고서·그래프 편차 신경망 상세 보고서용 그림(한글, 약어 없이).

  fig_gdn_arch.png     그래프 편차 신경망 구조도
  fig_graph.png        이웃 그래프: 데이터로 학습한 이웃 vs 계통 연결(토폴로지)로 고정한 이웃
  fig_variants.png     변형별 성능 (#3 결과)
  fig_lite.png         경량화 결과 (크기·추론 시간·탐지 정확도)  ← results/fmcs_v2/lite/eval.json
  fig_deploy.png       현장 적용 구성도
사용: FMCS_DATA=fmcs_synth_v2 python -m scripts.report_figs4 [이름...]
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from scripts.report_figs import NAVY, ORANGE, RED, GREY

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'report4'; OUT.mkdir(parents=True, exist_ok=True)
LITE = ROOT / 'results' / 'fmcs_v2' / 'lite'
PINK, LIGHT = '#B5487A', '#E8EDF6'


def save(fig, name):
    fig.savefig(OUT / name, dpi=220, bbox_inches='tight'); plt.close(fig); print('saved', OUT / name)


def box(ax, x, y, w, h, text, fc=LIGHT, ec=NAVY, fs=7.5, bold=False, tc='#1d2433'):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.012,rounding_size=0.02', fc=fc, ec=ec, lw=1))
    ax.text(x + w / 2, y + h / 2, text, ha='center', va='center', fontsize=fs, fontweight='bold' if bold else 'normal', color=tc, linespacing=1.35)


def arrow(ax, a, b, color=NAVY, text=None, fs=6.5, style='-|>', ls='-'):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=9, color=color, lw=1, linestyle=ls))
    if text: ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 0.018, text, ha='center', fontsize=fs, color=color)


def fig_gdn_arch():
    fig, ax = plt.subplots(figsize=(7.2, 3.1)); ax.set_xlim(-0.02, 1.02); ax.set_ylim(0, 1); ax.axis('off')
    # 입력
    box(ax, 0.0, 0.60, 0.17, 0.30, '입력 창\n최근 15분 × 1,077개\n센서·잔차 값', fs=7)
    box(ax, 0.0, 0.12, 0.17, 0.30, '센서 임베딩\n센서마다 학습되는\n특성 벡터', fc='#F6E7EF', ec=PINK, fs=7)
    # 그래프
    box(ax, 0.23, 0.12, 0.19, 0.30, '이웃 그래프 구성\n① 임베딩 유사도 상위 k\n② 계통 연결로 고정\n③ 개방 차단기 이웃 제외', fc='#F6E7EF', ec=PINK, fs=6.6)
    box(ax, 0.23, 0.60, 0.19, 0.30, '시점 압축\n센서별 과거 14분을\n은닉 벡터로 변환', fs=7)
    box(ax, 0.48, 0.36, 0.19, 0.34, '그래프 주의 집중\n이웃 센서 정보를\n관련도 가중치로 모음\n(가중치 = 이웃 중요도)', fc='#FFF3E0', ec=ORANGE, fs=6.8)
    box(ax, 0.73, 0.40, 0.12, 0.26, '현재 값\n예측', fs=7)
    box(ax, 0.88, 0.40, 0.12, 0.26, '예측 오차\n= 이상 점수\n(센서별)', fc='#FDECEA', ec=RED, fs=7)
    arrow(ax, (0.17, 0.75), (0.23, 0.75)); arrow(ax, (0.17, 0.27), (0.23, 0.27), PINK)
    arrow(ax, (0.42, 0.75), (0.48, 0.62)); arrow(ax, (0.42, 0.27), (0.48, 0.44), PINK)
    arrow(ax, (0.67, 0.53), (0.73, 0.53)); arrow(ax, (0.85, 0.53), (0.88, 0.53), RED)
    ax.annotate('', xy=(0.79, 0.40), xytext=(0.085, 0.12), arrowprops=dict(arrowstyle='-|>', color=PINK, lw=0.8, ls='--',
                connectionstyle='arc3,rad=0.25', mutation_scale=8))
    ax.text(0.47, 0.05, '임베딩을 곱해 센서별 출력', fontsize=6.3, color=PINK)
    ax.text(0.94, 0.30, '정규화 → 상위 5개 평균\n→ 임계 초과 시 경보\n→ 상위 센서 = 원인 설비', ha='center', va='top', fontsize=6.2, color=RED)
    save(fig, 'fig_gdn_arch.png')


def fig_graph():
    """한 배전선 주변 설비: 계통 연결 이웃(실선) vs 학습 그래프가 고른 이웃(점선, 대부분 무관한 계통)."""
    fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.6))
    pos = {'주 변압기': (0.5, 0.92), '6.6kV 주 차단기': (0.5, 0.74), '배전선 차단기 A1': (0.2, 0.52), '배전선 차단기 A2\n(대상)': (0.5, 0.52),
           '배전선 차단기 A3': (0.8, 0.52), '저압 변압기 A2': (0.5, 0.30), '220V 차단기 A2': (0.5, 0.10)}
    tree = [('주 변압기', '6.6kV 주 차단기'), ('6.6kV 주 차단기', '배전선 차단기 A1'), ('6.6kV 주 차단기', '배전선 차단기 A2\n(대상)'),
            ('6.6kV 주 차단기', '배전선 차단기 A3'), ('배전선 차단기 A2\n(대상)', '저압 변압기 A2'), ('저압 변압기 A2', '220V 차단기 A2')]
    far = {'다른 계통 220V\n차단기 (3F14)': (0.12, 0.18), '다른 계통 변압기\n온도 (3U11)': (0.88, 0.22), '다른 계통 역률\n(3F15)': (0.85, 0.80)}
    for k, (ax, title) in enumerate(zip(axs, ['(a) 데이터로 학습한 이웃 (원 논문 방식)', '(b) 계통 연결로 고정한 이웃 (본 과제)'])):
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off'); ax.set_title(title, fontsize=7.5)
        for a, b in tree:
            ax.plot(*zip(pos[a], pos[b]), color='#c6ccd8', lw=1, zorder=0)
        tgt = pos['배전선 차단기 A2\n(대상)']
        if k == 0:
            for n, p in far.items():
                ax.annotate('', xy=p, xytext=tgt, arrowprops=dict(arrowstyle='-', color=PINK, lw=1.1, ls='--'))
                ax.text(*p, n, ha='center', va='center', fontsize=6, bbox=dict(fc='#F6E7EF', ec=PINK, lw=0.6, boxstyle='round,pad=0.25'))
            nb = ['배전선 차단기 A1']
        else:
            nb = ['6.6kV 주 차단기', '저압 변압기 A2', '배전선 차단기 A1', '배전선 차단기 A3']
        for n in nb:
            ax.annotate('', xy=pos[n], xytext=tgt, arrowprops=dict(arrowstyle='-', color=NAVY if k else PINK, lw=1.6, ls='-' if k else '--'))
        for n, p in pos.items():
            hl = n.endswith('(대상)')
            ax.text(*p, n, ha='center', va='center', fontsize=6.2, fontweight='bold' if hl else 'normal',
                    bbox=dict(fc='#FFF3E0' if hl else 'white', ec=ORANGE if hl else '#9aa0a6', lw=0.8, boxstyle='round,pad=0.25'))
    axs[0].text(0.5, -0.04, '계통 2단계 이내 이웃 비율 3.5% (무작위 3.5%)', ha='center', fontsize=6.5, color=PINK, transform=axs[0].transAxes)
    axs[1].text(0.5, -0.04, '같은 설비의 측정값 + 바로 위·아래 설비만 이웃', ha='center', fontsize=6.5, color=NAVY, transform=axs[1].transAxes)
    save(fig, 'fig_graph.png')


def fig_variants():
    A = json.load(open(ROOT / 'results' / 'report3' / 'analysis.json'))['fmcs']
    g = A['gdn_all']
    names = {'GDN': '학습 그래프', 'GDN-prior': '계통 연결 고정', 'GDN-hybrid': '고정+학습 혼합', 'GDN-dyn': '개폐 상태 반영'}
    ms = [m for m in names if m in g]
    fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.2))
    for ax, (k, t) in zip(axs, [('ROC-AUC', '판별력(곡선 아래 면적)'), ('F1op', '운영 임계 탐지 정확도'), ('FAR_op', '운전 변동 구간 오경보율')]):
        v = [g[m][k] for m in ms]
        c = [NAVY if m == 'GDN-prior' else '#9fb0cf' for m in ms]
        ax.bar(range(len(ms)), v, color=c, width=0.65)
        ax.set_xticks(range(len(ms))); ax.set_xticklabels([names[m] for m in ms], fontsize=6.2, rotation=20)
        ax.set_title(t, fontsize=7.5)
        for i, x in enumerate(v): ax.text(i, x, f'{x:.3f}' if k != 'FAR_op' else f'{x * 100:.0f}%', ha='center', va='bottom', fontsize=6.3)
        ax.set_ylim(0, max(v) * 1.2); ax.spines[['top', 'right']].set_visible(False)
    b = A['base']
    axs[1].axhline(b['F1op'], color=GREY, ls='--', lw=0.8); axs[1].text(3.4, b['F1op'], '1차 기초 모델', fontsize=5.8, color=GREY, ha='right', va='bottom')
    save(fig, 'fig_variants.png')


LITE_NAME = {'GDN-prior': '기준 모델\n(은닉 64)', 'GDN-lite': '축소 모델\n(은닉 16)', 'GDN-lite-KD': '축소+증류', 'GDN-lite-KD-int8': '축소+증류\n+8비트'}


def fig_lite():
    E = json.load(open(LITE / 'eval.json'))
    ms = [m for m in LITE_NAME if m in E]
    fig, axs = plt.subplots(1, 4, figsize=(7.4, 2.2))
    specs = [('size_kb', '저장 크기 (KB)', '{:.0f}'), ('latency_ms', '1회 추론 시간 (ms, 일반 프로세서)', '{:.1f}'),
             ('F1op', '운영 임계 탐지 정확도', '{:.3f}'), ('node_top3', '원인 설비 상위 3 적중률', '{:.0%}')]
    for ax, (k, t, f) in zip(axs, specs):
        v = [E[m][k] for m in ms]
        ax.bar(range(len(ms)), v, color=[GREY if m == 'GDN-prior' else (ORANGE if m.endswith('int8') else NAVY) for m in ms], width=0.65)
        ax.set_xticks(range(len(ms))); ax.set_xticklabels([LITE_NAME[m] for m in ms], fontsize=5.6)
        ax.set_title(t, fontsize=7)
        for i, x in enumerate(v): ax.text(i, x, f.format(x), ha='center', va='bottom', fontsize=6)
        ax.set_ylim(0, max(v) * 1.22); ax.spines[['top', 'right']].set_visible(False); ax.tick_params(axis='y', labelsize=6)
    save(fig, 'fig_lite.png')


def fig_deploy():
    fig, ax = plt.subplots(figsize=(7.4, 2.9)); ax.set_xlim(-0.01, 1.01); ax.set_ylim(0, 1); ax.axis('off')
    ax.add_patch(FancyBboxPatch((0.0, 0.02), 0.828, 0.94, boxstyle='round,pad=0.005', fc='#F7F8FB', ec='#c6ccd8', ls='--'))
    ax.text(0.01, 0.92, '현장 내부망 (제어망과 분리된 감시 서버) — 언어 모델만 외부 호출', fontsize=6.8, color=GREY)
    box(ax, 0.02, 0.55, 0.16, 0.30, '설비 감시 시스템\n(WinCC OA)\n3초 측정값·개폐 상태', fs=6.6)
    box(ax, 0.22, 0.55, 0.16, 0.30, '1분 집계 + 피처\n물리식 잔차\n키르히호프 잔차', fs=6.6)
    box(ax, 0.42, 0.55, 0.16, 0.30, '경량 그래프 모델\n(수백 KB, 일반 서버)\n매 분 이상 점수', fc='#FFF3E0', ec=ORANGE, fs=6.6)
    box(ax, 0.22, 0.10, 0.16, 0.30, '경보 저장소\n기여 센서·설비\n개폐 기록', fs=6.6)
    box(ax, 0.42, 0.10, 0.16, 0.30, '조회 도구 서버\n(모델 컨텍스트 프로토콜)\n읽기 전용 9종', fs=6.4)
    box(ax, 0.66, 0.55, 0.15, 0.30, '진단 에이전트\n(goclaw)\n도구 호출·근거 정리', fc='#F6E7EF', ec=PINK, fs=6.6)
    box(ax, 0.85, 0.55, 0.15, 0.30, '언어 모델\n(Gemini, 중계: LiteLLM)\n현장: 내부 설치형\n모델로 교체 가능', fs=6.1)
    box(ax, 0.66, 0.10, 0.34, 0.30, '운영자 웹 화면\n계통도 · 실시간 값 · 경보 · 진단 채팅\n(조치는 운영자가 판단, 에이전트는 제어 안 함)', fs=6.6)
    arrow(ax, (0.18, 0.70), (0.22, 0.70)); arrow(ax, (0.38, 0.70), (0.42, 0.70))
    arrow(ax, (0.46, 0.55), (0.34, 0.40)); arrow(ax, (0.38, 0.25), (0.42, 0.25))
    arrow(ax, (0.58, 0.78), (0.66, 0.78), ORANGE, ls='--'); ax.text(0.62, 0.81, '경보 시\n자동 진단', fontsize=5.6, color=ORANGE, ha='center', va='bottom')
    arrow(ax, (0.58, 0.25), (0.69, 0.55), PINK, style='<|-|>'); ax.text(0.615, 0.43, '도구\n호출', fontsize=5.6, color=PINK, ha='center')
    arrow(ax, (0.81, 0.70), (0.85, 0.70), PINK, style='<|-|>')
    arrow(ax, (0.775, 0.55), (0.775, 0.40), PINK, style='<|-|>')
    save(fig, 'fig_deploy.png')


def fig_cases():
    """#3 사례 그림(fig3_cases)을 약어 없이 다시 그림."""
    import matplotlib.dates as mdates
    from src.data import fmcs
    from src.eval import normalize_errors
    from scripts.analyze3 import DS
    from scripts.report_figs import logy
    A = json.load(open(ROOT / 'results' / 'report3' / 'analysis.json'))
    kcl, raw = DS('fmcs_v2/kcl_rs', 'fmcs'), DS('fmcs_v2/raw', 'fmcs')
    ev = fmcs.events(); ts = kcl.ts; Wd = fmcs.load_wide()
    am, gm = A['fmcs']['ae_model'], A['fmcs']['gdn_model']
    KIND = {'VCB_FEEDER': '배전선 차단기', 'ACB': '220V 차단기'}
    nodes = pd.read_csv(fmcs.ROOT / 'topology_nodes.csv').set_index('node').etype
    TT = {'hidden_load': '계량되지 않는 부하(상·하위 전력 합 불일치)', 'ct_drift': '계기용 변류기 비율 오차'}
    fig, axes = plt.subplots(2, 2, figsize=(7.4, 3.3), sharex='col')
    for c, typ in enumerate(['hidden_load', 'ct_drift']):
        e = ev[(ev.type == typ) & (ev.start >= ts[0]) & (ev.end <= ts[-1])]
        e = e.iloc[int(np.argmax((e.end - e.start).values))]
        a = int(ts.searchsorted(e.start - pd.Timedelta('3h'))); b = int(ts.searchsorted(e.end + pd.Timedelta('2h')))
        t = ts[a:b]; n = e.target.rsplit('_', 1)[0] if typ == 'ct_drift' else e.target
        ax = axes[0, c]
        ax.plot(t, Wd.loc[t, f'{n}_POWER'], color=GREY, lw=0.8, label=f'{KIND.get(nodes[n], "설비")} 유효전력 (kW)')
        if typ == 'ct_drift':
            ax2 = ax.twinx(); ax2.plot(t, Wd.loc[t, f'{n}_CURRENT'], color=NAVY, lw=0.8, label='전류 (A)')
            ax2.tick_params(labelsize=6); ax2.legend(fontsize=5.8, loc='upper right')
        ax.axvspan(e.start, e.end, color=ORANGE, alpha=0.25, lw=0)
        ax.set_title(f"({'ab'[c]}) {TT[typ]} — 원신호", fontsize=7.6); ax.tick_params(labelsize=6); ax.legend(fontsize=5.8, loc='upper left')
        ax = axes[1, c]
        for ds, m, lab, col in [(raw, 'MLP-AE', '1차 기초 오토인코더(측정값만)', GREY), (kcl, am, '개선 오토인코더', NAVY), (kcl, gm, '그래프 편차 신경망(계통 고정)', PINK)]:
            Z = normalize_errors(*ds.runs[m][0])
            j = [i for i, cc in enumerate(ds.cols) if cc.startswith(n + '_')]
            ax.plot(t, np.clip(Z[a:b][:, j].max(1), 1e-2, None), lw=0.8, color=col, label=lab)
        ax.axvspan(e.start, e.end, color=ORANGE, alpha=0.25, lw=0); logy(ax)
        ax.set_title(f"({'cd'[c]}) 해당 설비 피처의 정규화 오차(최대, 로그 눈금)", fontsize=7.6); ax.tick_params(labelsize=6)
        ax.legend(fontsize=5.6, loc='upper left'); ax.xaxis.set_major_locator(mdates.HourLocator(interval=2)); ax.xaxis.set_major_formatter(mdates.DateFormatter('%H시'))
    fig.tight_layout(h_pad=0.5, w_pad=1.0); save(fig, 'fig_cases.png')


if __name__ == '__main__':
    names = sys.argv[1:] or ['gdn_arch', 'graph', 'variants', 'lite', 'deploy']
    for n in names:
        globals()['fig_' + n]()
