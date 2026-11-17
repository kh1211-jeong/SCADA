# -*- coding: utf-8 -*-
"""#4 모델 고도화·경량화 및 현장 적용·검증 계획 보고서(docx, 표지 없음, 2~3쪽).
약어를 쓰지 않는다(분야 밖 독자용). 수치는 results/report3/analysis.json, results/fmcs_v2/lite/eval.json에서 읽음.

사용: FMCS_DATA=fmcs_synth_v2 python -m scripts.build_report4  → 모델고도화경량화_현장적용계획_보고서.docx
"""
import json
from pathlib import Path
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, Twips
from scripts.build_report2 import ROOT, FONT, NAVY, GREY, LINE, _run, _spacing, _border, body, h1, h2, bullet, caption, note, table, figure

A = json.load(open(ROOT / 'results' / 'report3' / 'analysis.json'))
E = json.load(open(ROOT / 'results' / 'fmcs_v2' / 'lite' / 'eval.json'))
R4 = ROOT / 'results' / 'report4'
F = A['fmcs']
T, S, K, Q = (E.get(k) for k in ('GDN-prior', 'GDN-lite', 'GDN-lite-KD', 'GDN-lite-KD-int8'))


def pct(a, b): return f'{(a / b - 1) * 100:+.0f}%'


def build(out):
    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Twips(11906), Twips(16838)
    for k in ('left_margin', 'right_margin', 'top_margin', 'bottom_margin'): setattr(s, k, Twips(1080))
    st = doc.styles['Normal']; st.font.name = FONT; st.font.size = Pt(10)
    st.element.rPr.rFonts.set(qn('w:eastAsia'), FONT)

    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; _spacing(p, 0, 34)
    _run(p, '산업인공지능 문제해결 프로젝트  #4 모델 고도화·경량화 및 현장 적용·검증 계획', 14, True)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; _spacing(p, 0, 34)
    _run(p, '계통 연결 정보를 쓰는 그래프 신경망을 작게 만들어 현장 서버에 올리고, 진단 에이전트와 함께 단계적으로 검증한다', 10, False, NAVY)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; _spacing(p, 0, 110); _border(p, LINE, 6, 6)
    _run(p, '대상: 154kV 수전 ~ 6.6kV 배전 ~ 220V 저압의 전력 수배전 설비 (설비 감시 시스템 WinCC OA의 3초 측정 기록)', 8, False, GREY)

    # I
    h1(doc, 'I. 현재 수준과 남은 과제')
    body(doc, [('3차까지의 결과. ', True), (
        '1분 단위 측정값 1,077개(차단기 전력·전압·전류·역률, 변압기 온도·부하율 등과 물리식 잔차)를 입력으로, '
        '계통 연결(어느 설비가 어느 설비 아래에 붙어 있는지)을 이웃 관계로 고정한 그래프 편차 신경망(Graph Deviation Network)이 '
        f"가장 좋았다. 운영 임계에서의 탐지 정확도(정밀도와 재현율의 조화평균)는 1차 기초 모델 {F['base']['F1op']:.3f} → "
        f"{F['gdn']['F1op']:.3f}, 차단기 개폐 같은 정상 운전 변동을 이상으로 잘못 판정하는 비율은 "
        f"{F['base']['FAR_op'] * 100:.0f}% → {F['gdn']['FAR_op'] * 100:.0f}%로 줄었다.", False)])
    body(doc, [('남은 과제. ', True), (
        '① 계기용 변압기 비율 오차·변압기 과열은 아직 잡지 못하고 탭 절환기 반복 동작은 탐지율이 낮다. '
        '② 모델 1회 학습에 47분이 걸리고 은닉 크기 64의 모델을 그래픽 처리 장치에서 돌렸다 — 현장 감시 서버(일반 프로세서)에 그대로 올리기 부담스럽다. '
        '③ 검증이 계통을 모사한 시뮬레이션 데이터 기준이다. 실제 기록에서의 오경보 수와 운영자에게 주는 설명의 품질은 아직 확인하지 않았다.', False)])

    # II
    h1(doc, 'II. 모델 고도화 계획')
    for h, t in [
        ('미탐 유형 전용 피처 추가: ', '같은 모선에 붙은 형제 설비들의 전압 중앙값과의 편차(계기용 변압기 비율 오차), 부하율의 제곱으로 예측한 '
                               '변압기 온도와 실측 온도의 차(냉각 이상·과열), 최근 30분 탭 변경 횟수와 하위 전압 진동 폭(탭 절환기 반복 동작). '
                               '세 가지 모두 측정값만으로 계산되므로 현장 시스템 변경 없이 추가할 수 있다.'),
        ('실데이터 적응: ', '현장 기록 중 이상 기록이 없는 2~4주를 골라 미세조정한다. 설비 정격·부하 패턴이 시뮬레이션과 다르므로 '
                        '정규화 기준(분위수)과 경보 임계는 반드시 현장 데이터로 다시 구한다. 계절 부하 변화에 대비해 월 1회 재학습하고, '
                        '정상 구간 점수 분포가 학습 때보다 커지면(분포 이동) 재학습을 앞당긴다.'),
        ('운전 변동 구분 고도화: ', '지금은 차단기 상태 변화로부터 계통상 2단계 이내 설비를 15분간 점수에서 빼는 규칙을 쓴다. '
                                '여기에 작업 계획·운영 일지(계획 정비, 절체 작업)를 연동해 계획된 조작은 사전에 제외하고, '
                                '계획에 없는 차단기 개방(보호계전기 동작)은 오히려 진단 대상으로 넘긴다.'),
        ('신뢰성 검증: ', '그래프 신경망 변형별 시드 1회만 평가했으므로, 최종 구성은 시드 5회 평균과 편차로 다시 보고한다.'),
    ]:
        bullet(doc, h, t)

    # III
    h1(doc, 'III. 경량화 계획과 예비 결과')
    body(doc, '현장 감시 서버의 일반 프로세서에서 1분마다 전 계통을 한 번에 판정하는 것을 목표로, 세 가지를 순서대로 적용해 실제로 학습·측정하였다. '
              '(1) 구조 축소: 은닉 크기 64 → 16, 센서당 이웃 24 → 12개. (2) 지식 증류: 축소 모델이 실측값과 함께 기준 모델의 예측도 따라 하도록 학습. '
              '(3) 8비트 정수 양자화: 학습이 끝난 모델의 선형 계층 가중치를 32비트 실수 대신 8비트 정수로 저장·계산.')
    rows = [['구성', '파라미터 수', '저장 크기', '1회 추론 시간', '판별력', '탐지 정확도(운영)', '이벤트 탐지율', '원인 설비 적중']]
    nm = {'GDN-prior': '기준 모델(은닉 64)', 'GDN-lite': '구조 축소(은닉 16)', 'GDN-lite-KD': '축소 + 지식 증류', 'GDN-lite-KD-int8': '축소 + 증류 + 8비트'}
    for m, r in E.items():
        rows.append([nm[m], f"{r['params']:,}", f"{r['size_kb']:.0f} KB", f"{r['latency_ms']:.1f} ms", f"{r['ROC-AUC']:.3f}",
                     f"{r['F1op']:.3f}", f"{r['event_recall'] * 100:.0f}%", f"{r['node_top3'] * 100:.0f}%"])
    caption(doc, '표 1. 경량화 단계별 크기·속도·탐지 성능 (시뮬레이션 평가 12일, 일반 프로세서 4스레드, 1분 1회 판정 기준)')
    table(doc, rows, [3.6, 1.8, 1.6, 1.9, 1.4, 2.2, 1.9, 1.9], align_right_from=1)
    note(doc, '※ 판별력 = 정상·이상 점수 분포의 분리 정도(곡선 아래 면적), 원인 설비 적중 = 이벤트 구간 오차 상위 3개 설비 안에 실제 고장 설비가 있는 비율.')
    best = Q or K
    body(doc, [('해석. ', True), (
        f"최종 경량 모델(축소+증류+8비트)은 저장 크기 {T['size_kb']:.0f} → {best['size_kb']:.0f} KB({best['size_kb'] / T['size_kb'] * 100:.0f}%), "
        f"추론 시간 {T['latency_ms']:.1f} → {best['latency_ms']:.1f} ms로, 1분 주기 판정에 쓰는 시간이 무시할 수준이다. "
        f"운영 임계 탐지 정확도는 {T['F1op']:.3f} → {best['F1op']:.3f}({pct(best['F1op'], T['F1op'])}), 원인 설비 적중률은 "
        f"{T['node_top3'] * 100:.0f}% → {best['node_top3'] * 100:.0f}%이다. "
        + (f"지식 증류는 같은 크기를 정답만으로 학습한 경우({S['F1op']:.3f})보다 {('높았다' if K['F1op'] >= S['F1op'] else '낮았다')}({K['F1op']:.3f}). " if S and K else '')
        + '계획 단계에서는 계통별 분할 모델(계통 하나가 고장 나도 나머지 판정 유지)과 이웃 수 추가 축소를 시험하고, '
          '정확도 저하 5% 이내·저장 크기 1MB 이하·전 계통 판정 10ms 이하를 경량화 합격선으로 둔다.', False)])

    # IV
    h1(doc, 'IV. 현장 적용 계획')
    figure(doc, R4 / 'fig_deploy.png', 15.5, '[그림 1] 현장 적용 구성: 감시 시스템 기록 → 경량 모델 → 경보 → 진단 에이전트 → 운영자 화면')
    for h, t in [
        ('데이터 연결(읽기 전용): ', '설비 감시 시스템의 측정 기록 데이터베이스를 1분마다 조회만 한다. 제어망에는 쓰기 경로를 두지 않으며, '
                               '감시 서버는 제어망과 분리된 내부망에 둔다.'),
        ('진단 에이전트: ', '오픈소스 에이전트 실행기(goclaw)에 대규모 언어 모델(Google Gemini, 중계기 LiteLLM 경유)을 붙였다. 에이전트는 '
                         '모델 컨텍스트 프로토콜로 공개한 읽기 전용 조회 도구 9종(경보·개폐 기록·계통 위치·추이·물리식 점검 등)만 호출하며, '
                         '판정·위치·근거 수치·운영자 확인 권고 형식으로 답한다. 차단기 조작 기능은 없다. 언어 모델은 외부 호출이므로 '
                         '현장 보안 정책에 따라 내부 설치형 언어 모델로 바꿀 수 있게 중계기를 사이에 두었다.'),
        ('시연 환경(구축 완료): ', '웹 화면에서 6개 계통의 단선 계통도와 실시간 값(시뮬레이터, 1초에 1분 진행)을 보고, 운영자가 차단기를 개폐·트립하거나 '
                              '계측 이상 11종을 주입하면 경량 모델이 매 분 판정하고 경보가 3분 이상 이어지면 에이전트가 자동으로 원인 설비와 영향 범위를 '
                              '채팅으로 설명한다. 배전선 차단기 트립 시험에서 에이전트는 약 25초 만에 트립 위치·정전된 하위 변압기·영향 없는 형제 배전선을 '
                              '정확히 구분해 답했다.'),
    ]:
        bullet(doc, h, t)

    # V
    h1(doc, 'V. 현장 검증 계획')
    caption(doc, '표 2. 단계별 검증 방법과 합격 기준')
    table(doc, [
        ['단계(기간)', '방법', '합격 기준'],
        ['1. 과거 기록 재생\n(4주)', '현장 기록 3개월 추출 → 정상 기간으로 미세조정 → 나머지 기간을 재생하며 판정. 운영 일지·고장 기록과 경보 대조. '
                                 '실제 기록에 시뮬레이션과 같은 방식으로 계측 이상을 주입해 탐지율 측정',
         '오경보 계통당 하루 1건 이하 · 주입 이상 탐지율 70% 이상 · 탐지 지연 중앙값 5분 이내 · 원인 설비 상위 3 적중 80% 이상'],
        ['2. 병행 운전\n(4주)', '실시간 연결, 경보는 기록만 하고 운영자 화면에는 표시하지 않음. 매주 경보 목록을 운영 담당자와 검토',
         '1단계 기준 유지 · 감시 시스템 부하 영향 없음 · 판정 누락(1분 주기 초과) 0건'],
        ['3. 시범 운영\n(4주)', '운영자 화면과 진단 채팅 공개. 경보마다 운영자가 진단의 정확성·유용성을 5점 척도로 평가',
         '진단 응답 60초 이내 · 근거 수치가 도구 조회값과 100% 일치 · 제어 지시 0건 · 운영자 평가 평균 4점 이상'],
    ], [2.6, 7.6, 6.2])
    body(doc, [('운영 원칙. ', True), ('검증 기간 동안 모델과 에이전트는 판단 보조로만 쓰고 조치는 운영자가 결정한다. 오경보·미탐 사례는 '
               '모두 기록해 피처와 임계를 고치는 근거로 쓰며, 3단계를 통과하면 월 1회 재학습 절차와 함께 정식 운영으로 전환한다.', False)])
    doc.save(out)
    print('saved', out)


if __name__ == '__main__':
    build(ROOT / '모델고도화경량화_현장적용계획_보고서.docx')
