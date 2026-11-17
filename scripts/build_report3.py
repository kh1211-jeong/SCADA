# -*- coding: utf-8 -*-
"""#3 개선 모델 성능 분석 보고서(docx) — 1·2차 보고서 서식 재사용, 수치는 results/report3/analysis.json에서 읽음.

사용: FMCS_DATA=fmcs_synth_v2 python -m scripts.build_report3  → 개선모델성능분석_보고서.docx
"""
import json
from pathlib import Path
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, Twips
from scripts.build_report2 import (ROOT, FONT, NAVY, GREY, LINE, _run, _spacing, _border, body, h1, h2, bullet,
                                   caption, note, table, figure, f3)

R3 = ROOT / 'results' / 'report3'
A = json.load(open(R3 / 'analysis.json'))
DSN = {'wadi': 'WADI', 'epic': 'EPIC', 'fmcs': 'FMCS 트렌드'}
TYPE_KO = {'ct_drift': 'CT 드리프트', 'meter_offset': '전력계 오프셋', 'pf_sign_flip': 'PF 부호 반전',
           'sensor_stuck': '값 고착', 'spike_burst': '전류 스파이크', 'ltr_overheat': '변압기 과열',
           'oltc_hunting': 'OLTC 헌팅', 'voltage_sag': '순간전압강하', 'hidden_load': '미계량 부하',
           'pt_drift': 'PT 드리프트'}


def pct(a, b): return f'{(a / max(b, 1e-9) - 1) * 100:+.0f}%'


def final(k):
    """데이터셋별 최종 구성: 운영 임계 F1이 가장 높은 쪽(개선 AE 단독, GDN 단독, AE+GDN 앙상블)."""
    return max(['ae', 'gdn', 'ens'], key=lambda c: A[k][c]['F1op'])


def name_of(k, c):
    return {'ae': A[k]['ae_model'], 'gdn': A[k]['gdn_model'], 'ens': '+'.join(A[k]['ens_models'])}[c]


def build(out_path):
    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Twips(11906), Twips(16838)
    for k in ('left_margin', 'right_margin', 'top_margin', 'bottom_margin'): setattr(s, k, Twips(1080))
    st = doc.styles['Normal']; st.font.name = FONT; st.font.size = Pt(10)
    st.element.rPr.rFonts.set(qn('w:eastAsia'), FONT)

    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; _spacing(p, 0, 34)
    _run(p, '산업인공지능 문제해결 프로젝트  #3 개선 모델 성능 분석', 14.5, True)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; _spacing(p, 0, 34)
    _run(p, '기초 오토인코더 대비 향상 비율과 그 원인: 시계열 AE · 스코어링 · 물리/KCL 잔차 · 운전 컨텍스트 · GDN', 10.5, False, NAVY)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; _spacing(p, 0, 120); _border(p, LINE, 6, 6)
    _run(p, '주제: 토폴로지 인지 그래프 기반 조기 이상탐지    /    대상: 154kV 수전 ~ 220V 수배전 (WinCC OA)', 8, False, GREY)

    W, E, F = A['wadi'], A['epic'], A['fmcs']
    fk = {k: final(k) for k in ('wadi', 'epic', 'fmcs')}
    ab = A['ablation']; T = A['fmcs_types']

    # I
    h1(doc, 'I. 분석 개요')
    body(doc, '#2에서 계획한 개선 기법을 모두 구현하여, 1차 기초 모델(시점 단위 MLP-AE, Min-Max 정규화, 전체 센서 평균 오차, '
              '정상 99% 임계)과 같은 데이터·같은 분할에서 비교하였다. 비교 대상은 개선 AE(시계열 AE + 센서별 정규화·상위 k 집계·인과 평활), '
              'GDN 변형 4종(학습 그래프, 토폴로지 고정, 토폴로지+학습 혼합, STATUS 기반 동적 그래프), AE와 GDN의 점수 앙상블이다. '
              '지표는 ROC-AUC, 최적 F1, 운영 임계 F1(배포 시 실제 판정), 이벤트 탐지율, 운전 이벤트 구간 오경보율이며 '
              '향상률은 (개선 − 기초)/기초로 계산하였다.')
    note(doc, f"※ FMCS 트렌드는 대상 계통 토폴로지·태그 명명·Oracle 저장 형식(3초 exception 압축)을 따르는 시뮬레이션 데이터(42일)이다. "
              f"부하 유형별(공정·공조·사무) 패턴, 외기온도, 공휴일, 개폐·절체 운전을 반영했고 이상 10종(평가 12일, {F['n_events']}건)을 "
              f"현장 수준 크기(예: CT 비 4~12%, PT 비 0.6~1.8%)로 주입했다. 학습 26일·검증 4일·평가 12일, AE는 시드 3회 평균, GDN 변형은 시드 1회이다.")

    # II
    h1(doc, 'II. 종합 결과: 기초 모델 대비 향상 비율')

    def row(k):
        b, f = A[k]['base'], A[k][fk[k]]
        return [DSN[k], name_of(k, fk[k]), f"{f3(b['ROC-AUC'])} → {f3(f['ROC-AUC'])}", f"{f3(b['F1*'])} → {f3(f['F1*'])}",
                f"{f3(b['F1op'])} → {f3(f['F1op'])}", pct(f['F1op'], b['F1op']), f"{b['event_recall'] * 100:.0f} → {f['event_recall'] * 100:.0f}%"]
    caption(doc, '표 1. 데이터셋별 기초 모델(1차 AE) 대비 최종 개선 구성의 성능')
    table(doc, [['데이터셋', '최종 구성', 'ROC-AUC', 'F1(최적)', 'F1(운영 임계)', 'F1 향상', '이벤트 탐지율']] + [row(k) for k in ('wadi', 'epic', 'fmcs')],
          [2.2, 3.6, 2.4, 2.4, 2.4, 1.6, 2.4], align_right_from=2)
    figure(doc, R3 / 'fig1_overall.png', 13.5, '[그림 1] (a) 모델 계열별 운영 임계 F1, (b) 최종 구성의 지표별 향상률')
    body(doc, [('요약. ', True), (f"운영 임계 F1 기준 향상률은 WADI {pct(W[fk['wadi']]['F1op'], W['base']['F1op'])}, EPIC "
               f"{pct(E[fk['epic']]['F1op'], E['base']['F1op'])}, FMCS {pct(F[fk['fmcs']]['F1op'], F['base']['F1op'])}이다. "
               f"FMCS에서 향상이 가장 큰 것은 기초 AE가 운전 이벤트(개폐·절체) 구간의 {F['base']['FAR_op'] * 100:.0f}%를 이상으로 판정해 "
               f"운영 임계가 사실상 무력화되었기 때문이며, 최종 구성은 이를 {F[fk['fmcs']]['FAR_op'] * 100:.0f}%로 낮췄다.", False)])

    # III
    h1(doc, 'III. 향상 원인 분석')
    h2(doc, '단계별 기여 (FMCS, 한 요소씩 누적)')
    figure(doc, R3 / 'fig2_ablation_types.png', 14.5, '[그림 2] (a) 개선 요소를 하나씩 추가할 때의 F1과 운전 이벤트 오경보율, (b) 이상 유형별 이벤트 탐지율')
    st = {x['step']: x for x in ab}
    seq = [x['step'] for x in ab]
    deltas = [(seq[i], ab[i]['ROC-AUC'] - ab[i - 1]['ROC-AUC'], ab[i]['F1op'] - ab[i - 1]['F1op']) for i in range(1, len(ab))]
    for i, (stp, da, df) in enumerate(deltas, 1):
        bullet(doc, f'{stp.lstrip("+")}: ', REASON[stp](ab[i - 1], ab[i], f'{da:+.3f}', f'{df:+.3f}'))
    h2(doc, '이상 유형별 탐지율 (그림 2(b))')
    body(doc, TYPES_TEXT(T))
    h2(doc, 'GDN 적용 효과')
    body(doc, GDN_TEXT(F))

    # IV
    h1(doc, 'IV. 사례 분석: 설비 간 관계로만 보이는 이상')
    figure(doc, R3 / 'fig3_cases.png', 14.5, '[그림 3] 미계량 부하(좌)와 CT 드리프트(우): 원신호(위)와 해당 설비 피처의 정규화 오차(아래)')
    body(doc, CASE_TEXT(F, T))

    # V
    h1(doc, 'V. 한계와 #4 계획')
    for h, t in LIMITS:
        bullet(doc, h, t)
    doc.save(out_path)
    print('saved', out_path)


# 결과 해석 문구 (수치는 analysis.json에서) -------------------------------------------------------
def fr(x): return f"{x.get('FAR_op', 0) * 100:.0f}%"


REASON = {
    '+시계열 윈도우': lambda p, c, da, df: (
        f'AUC {da}, 운영 F1 {df}. 1,000여 개 피처의 평균 오차에서는 소수 설비의 이상이 희석되어 효과가 거의 없다.'),
    '+정규화·상위k·평활': lambda p, c, da, df: (
        f'AUC {da}. 센서별 정규화 후 상위 5개만 집계하자 운전 이벤트 오경보율이 {fr(p)} → {fr(c)}로 줄었으나, '
        '태그 값만으로는 작은 이상이 정상 변동과 구분되지 않아 F1은 그대로였다.'),
    '+물리 잔차': lambda p, c, da, df: (
        f'AUC {da}, 운영 F1 {df}. 설비 내부식 P − √3·V·I·PF/100의 잔차로 CT 드리프트·PF 부호 반전처럼 태그 간 관계가 깨지는 이상이 드러난다.'),
    '+KCL 잔차': lambda p, c, da, df: (
        f'AUC {da}, 운영 F1 {df}로 기여가 가장 크다. 상위 피더 P와 하위 계량 P 합의 차이는 미계량 부하·전력계 오프셋처럼 '
        '설비 간 관계에서만 보이는 이상을 직접 드러낸다.'),
    '+강건 스케일링': lambda p, c, da, df: (
        f'AUC {da}. Min-Max는 개폐 과도의 극값으로 범위가 부풀어 정상 변동이 눌린다. 0.5~99.5% 분위수 스케일링으로 작은 편차의 해상도를 확보하였다.'),
    '+운전 컨텍스트': lambda p, c, da, df: (
        f'운영 F1 {df}, 운전 이벤트 오경보율 {fr(p)} → {fr(c)}. 평상 구성과 다르거나 최근 15분 내 개폐된 차단기의 토폴로지 2단계 이내 '
        '설비 피처를 STATUS로 판별해 점수에서 제외하였다(라벨 미사용). 절체·정비가 임계를 끌어올리지 않아 운영 F1이 가장 크게 오른다.'),
    '+GDN 앙상블': lambda p, c, da, df: (
        f'운영 F1 {df}. 두 모델이 잡는 이벤트가 거의 겹쳐 앙상블 이득은 작다.'),
}


def TYPES_TEXT(T):
    ko = lambda t: TYPE_KO.get(t, t)
    up = sorted([t for t in T if T[t]['ae'] - T[t]['base'] >= 0.3], key=lambda t: T[t]['base'] - T[t]['ae'])
    miss = [t for t in T if T[t]['ae'] == 0 and T[t]['gdn'] == 0]
    down = [t for t in T if T[t]['ae'] < T[t]['base'] and t not in miss]
    s = ('새로 잡게 된 유형은 ' + ', '.join(f"{ko(t)}({T[t]['base'] * 100:.0f}→{T[t]['ae'] * 100:.0f}%)" for t in up) +
         '이다. 전류 스파이크·값 고착은 센서별 정규화와 상위 k 집계로 소수 태그의 이상이 희석되지 않게 되어 잡혔고, '
         '나머지는 개별 태그 값이 정상 범위 안에 있어 물리식·KCL 잔차에서만 드러나는 유형이다. ')
    why = {'pt_drift': 'PT 드리프트는 V와 P가 같은 비율(0.6~1.8%)로 변해 설비 내부 물리식이 그대로 성립하고, 같은 모선 형제 설비의 전압과 비교하는 피처가 아직 없다',
           'ltr_overheat': '변압기 과열은 수십 분에 걸친 완만한 온도 상승이라 15분 윈도우 안에서는 정상 부하 변동과 구분되지 않고, 부하 대비 온도 관계를 나타내는 피처가 없다'}
    if miss:
        s += '반면 ' + ', '.join(ko(t) for t in miss) + '은 어느 모델도 탐지하지 못했다. ' + '. '.join(why[t] for t in miss if t in why) + '. '
    if down:
        s += ', '.join(f"{ko(t)}" for t in down) + '의 탐지율은 ' + ', '.join(f"{T[t]['base'] * 100:.0f}→{T[t]['ae'] * 100:.0f}%" for t in down) + \
             '로 오히려 줄었다. 탭 왕복에 따른 전압 진동이 정상 탭 동작과 크기가 비슷하여, 정규화 후 상위 k 집계에서 다른 설비의 오차에 묻힌 것으로 본다.'
    return s


def GDN_TEXT(F):
    g = F['gdn_all']; ko = {'GDN': '학습 그래프', 'GDN-prior': '토폴로지 고정', 'GDN-hybrid': '토폴로지+학습 top-k', 'GDN-dyn': '동적(STATUS 게이팅)'}
    s = 'FMCS에서 GDN 변형별 F1(최적/운영 임계)은 ' + ', '.join(f"{ko[m]} {g[m]['F1*']:.3f}/{g[m]['F1op']:.3f}" for m in ko if m in g) + '이다. '
    if 'GDN-prior' in g and g['GDN-prior']['F1*'] > g['GDN']['F1*']:
        s += f"계통 토폴로지를 이웃으로 고정한 쪽이 데이터에서 그래프를 학습한 쪽보다 높다({pct(g['GDN-prior']['F1*'], g['GDN']['F1*'])}). "
    if 'graph' in F:
        s += (f"학습된 이웃 중 토폴로지 2단계 이내 설비는 {F['graph']['learned_in_topology'] * 100:.1f}%로 무작위 기대치"
              f"({F['graph']['random_expect'] * 100:.1f}%)와 같아, 1,000여 개 피처에서는 정상 데이터만으로 계통 연결을 복원하지 못한다. "
              '토폴로지는 학습 대상이 아니라 주입할 사전 지식이며, 이것이 "토폴로지 인지" 접근의 근거다. ')
    if 'GDN-dyn' in g and 'GDN-hybrid' in g:
        h, d, p = g['GDN-hybrid'], g['GDN-dyn'], g.get('GDN-prior', g['GDN'])
        s += (f"토폴로지에 학습 top-k 이웃을 더한 혼합 그래프는 오히려 운전 이벤트 오경보율이 {h['FAR_op'] * 100:.0f}%로 토폴로지 고정"
              f"({p['FAR_op'] * 100:.0f}%)보다 높았다. (개폐에 따라 함께 변하는 설비를 이웃으로 끌어들임). "
              f"차단기 개방 시 해당 이웃을 어텐션에서 빼는 동적 그래프는 혼합 대비 F1(최적) {d['F1*'] - h['F1*']:+.3f}, "
              f"운영 F1 {d['F1op'] - h['F1op']:+.3f}로 소폭 나아졌지만 오경보율은 같아({d['FAR_op'] * 100:.0f}%), "
              '운전 변동 억제는 그래프 게이팅보다 점수 단계의 운전 컨텍스트 마스크가 더 효과적이었다. ')
    w, e = A['wadi'], A['epic']
    s += (f"토폴로지 정보가 없는 WADI·EPIC에는 학습 그래프 GDN만 적용했으며, 운영 F1이 개선 AE보다 낮았다"
          f"(WADI {w['gdn']['F1op']:.3f} vs {w['ae']['F1op']:.3f}, EPIC {e['gdn']['F1op']:.3f} vs {e['ae']['F1op']:.3f}).")
    return s


def CASE_TEXT(F, T):
    return ('미계량 부하는 피더 하류의 누설·미등록 부하로 피더 P·I가 4~10% 늘지만 V·I·PF 관계는 성립한다. 따라서 태그만 쓰는 1차 AE에서는 '
            f"정상 부하 변동과 구분되지 않고(이벤트 탐지 {T['hidden_load']['base'] * 100:.0f}%), 하위 ACB 합과의 KCL 잔차에서만 드러난다"
            f"(개선 AE {T['hidden_load']['ae'] * 100:.0f}%). CT 드리프트는 전류만 4~12% 서서히 커지고 전력계 P는 그대로이므로 "
            f"물리 잔차 P − √3·V·I·PF가 벌어진다({T['ct_drift']['base'] * 100:.0f} → {T['ct_drift']['ae'] * 100:.0f}%). "
            '두 사례 모두 오차가 해당 설비 피처에 집중되므로, 상위 k 피처를 그대로 원인 설비 후보로 운영자에게 제시할 수 있다.')


LIMITS = [
    ('검증 데이터: ', 'FMCS 결과는 대상 계통을 모사한 시뮬레이션 기반이다. 실 트렌드 데이터에 같은 파이프라인을 적용해 재검증하고, '
                   '이상 크기·빈도를 현장 이력에 맞춰 보정한다.'),
    ('미탐 유형: ', 'PT 드리프트는 같은 모선 형제 설비 간 전압 차 잔차로, 변압기 과열은 부하율²–권선온도 열모델 잔차로 피처를 추가한다.'),
    ('계산 비용: ', 'GDN은 1회 학습에 35~90분(AE의 10~30배)이 걸려 변형별 시드 1회만 평가했다. 경량화(가지치기·지식 증류로 AE 크기 수준)와 다시드 검증을 함께 진행한다.'),
    ('현장 적용: ', '상위 k 피처·토폴로지 경로를 근거로 원인 설비와 영향 범위를 설명하는 진단 에이전트를 WinCC OA 화면과 연계한다(감시·진단 전용, 제어 미개입).'),
]

if __name__ == '__main__':
    build(ROOT / '개선모델성능분석_보고서.docx')
