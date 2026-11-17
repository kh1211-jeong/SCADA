# -*- coding: utf-8 -*-
"""#2 기초 모델 개선 계획 보고서(docx) 생성 — 1차 보고서 서식(맑은 고딕, 남색 제목선, 표 음영) 재현.
수치는 results/*/metrics.json 에서 직접 읽는다(수기 전사 금지).

사용: python -m scripts.build_report2  → 기초모델개선계획_보고서.docx
"""
import json
from pathlib import Path
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm, Twips

ROOT = Path(__file__).resolve().parents[1]
GDNP = 66113  # GDN-prior 파라미터 수 (FMCS 947 피처, w=15)
RES = ROOT / 'results'
FONT = '맑은 고딕'
INK, NAVY, GREY, LINE = '2C2C2A', '1F3A6B', '6F6E68', 'B9B7AD'


def M(name):
    return json.load(open(RES / name / 'metrics.json'))


# ---------------------------------------------------------------- 서식 헬퍼
def _run(p, text, size=10, bold=False, color=INK, italic=False):
    r = p.add_run(text)
    r.font.name = FONT; r.font.size = Pt(size); r.font.bold = bold; r.font.italic = italic
    r.font.color.rgb = RGBColor.from_string(color)
    rpr = r._element.get_or_add_rPr(); rf = rpr.find(qn('w:rFonts'))
    for a in ('w:ascii', 'w:hAnsi', 'w:eastAsia', 'w:cs'): rf.set(qn(a), FONT)
    return r


def _spacing(p, before=0, after=0, line=None):
    pf = p.paragraph_format
    pf.space_before = Twips(before); pf.space_after = Twips(after)
    if line: pf.line_spacing = line / 240


def _border(p, color, sz, space, side='bottom'):
    ppr = p._p.get_or_add_pPr(); b = OxmlElement('w:pBdr'); e = OxmlElement(f'w:{side}')
    for k, v in (('w:val', 'single'), ('w:color', color), ('w:sz', str(sz)), ('w:space', str(space))): e.set(qn(k), v)
    b.append(e); ppr.append(b)


def body(doc, segs, after=90):
    """segs: str 또는 [(text, bold), ...]"""
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; _spacing(p, 0, after, 245)
    for t, b in ([(segs, False)] if isinstance(segs, str) else segs): _run(p, t, 10, b)
    return p


def h1(doc, text):
    p = doc.add_paragraph(); _spacing(p, 130, 70); _border(p, NAVY, 10, 3)
    _run(p, text, 11.5, True, NAVY)


def h2(doc, text):
    p = doc.add_paragraph(); _spacing(p, 60, 50); _run(p, '■ ' + text, 10, True, NAVY)


def bullet(doc, head, text, after=50):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; _spacing(p, 0, after, 240)
    p.paragraph_format.left_indent = Cm(0.45); p.paragraph_format.first_line_indent = Cm(-0.3)
    _run(p, '· ', 10); _run(p, head, 10, True); _run(p, text, 10)


def caption(doc, text, before=40, after=50, center=False):
    p = doc.add_paragraph(); _spacing(p, before, after)
    if center: p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p, text, 9, True)


def note(doc, text):
    p = doc.add_paragraph(); _spacing(p, 20, 80, 240); _run(p, text, 8, False, GREY)


def table(doc, rows, widths, bold_rows=(), align_right_from=None):
    t = doc.add_table(rows=len(rows), cols=len(rows[0])); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    tblPr = t._tbl.tblPr; bd = OxmlElement('w:tblBorders')
    for side, c, sz in (('top', LINE, 5), ('left', LINE, 5), ('bottom', LINE, 5), ('right', LINE, 5),
                        ('insideH', 'D5D3C9', 4), ('insideV', 'D5D3C9', 4)):
        e = OxmlElement(f'w:{side}'); [e.set(qn(k), v) for k, v in (('w:val', 'single'), ('w:color', c), ('w:sz', str(sz)))]; bd.append(e)
    tblPr.append(bd)
    t.autofit = False
    tw = OxmlElement('w:tblW'); tw.set(qn('w:w'), str(int(sum(widths) * 567))); tw.set(qn('w:type'), 'dxa')
    for old in tblPr.findall(qn('w:tblW')): tblPr.remove(old)
    tblPr.append(tw)
    lay = OxmlElement('w:tblLayout'); lay.set(qn('w:type'), 'fixed'); tblPr.append(lay)
    grid = t._tbl.tblGrid
    for gc, wcm in zip(grid.findall(qn('w:gridCol')), widths): gc.set(qn('w:w'), str(int(wcm * 567)))
    for i, row in enumerate(rows):
        tr = t.rows[i]._tr; trPr = tr.get_or_add_trPr(); cs = OxmlElement('w:cantSplit'); trPr.append(cs)
        if i == 0: trPr.append(OxmlElement('w:tblHeader'))
        for j, val in enumerate(row):
            c = t.cell(i, j); c.width = Cm(widths[j])
            tcPr = c._tc.get_or_add_tcPr(); shd = OxmlElement('w:shd')
            shd.set(qn('w:val'), 'clear'); shd.set(qn('w:fill'), 'E8EDF6' if i == 0 else ('F4F6FA' if i in bold_rows else 'FFFFFF'))
            tcPr.append(shd)
            mar = OxmlElement('w:tcMar')
            for side, v in (('top', 30), ('left', 80), ('bottom', 30), ('right', 80)):
                e = OxmlElement(f'w:{side}'); e.set(qn('w:w'), str(v)); e.set(qn('w:type'), 'dxa'); mar.append(e)
            tcPr.append(mar)
            p = c.paragraphs[0]; _spacing(p, 0, 0, 240)
            if align_right_from is not None and j >= align_right_from and i > 0: p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if i == 0 and align_right_from is not None and j >= align_right_from: p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _run(p, str(val), 8, i == 0 or i in bold_rows)
    return t


def figure(doc, path, width_cm, cap):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; _spacing(p, 40, 10)
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    caption(doc, cap, 0, 70, center=True)


# ---------------------------------------------------------------- 수치
def f3(x): return f'{x:.3f}'


def pick(rep, scoring, model, key):
    return rep[scoring][model][key][0]


def build(out_path):
    W, E = M('wadi/drift_filtered'), M('epic')
    Fr, Fp = M('fmcs/raw'), M('fmcs/physics')
    Wall = M('wadi/all_sensors')
    B, I = 'raw-mean', 'norm-top5+smooth'

    def best_of(rep, models, key='F1*', scoring=I):
        ms = [m for m in models if m in rep[scoring]]
        return max(ms, key=lambda m: rep[scoring][m][key][0])

    AE = ['MLP-AE', 'Window-AE', 'Conv-AE', 'LSTM-AE']
    bw, be, bf, bfr = best_of(W, AE), best_of(E, AE), best_of(Fp, AE), best_of(Fr, AE)

    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Twips(11906), Twips(16838)
    for k in ('left_margin', 'right_margin', 'top_margin', 'bottom_margin'): setattr(s, k, Twips(1080))
    st = doc.styles['Normal']; st.font.name = FONT; st.font.size = Pt(10)
    st.element.rPr.rFonts.set(qn('w:eastAsia'), FONT)

    # 머리 (표지 없음)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; _spacing(p, 0, 34)
    _run(p, '산업인공지능 문제해결 프로젝트  #2 기초 모델 개선 계획', 14.5, True)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; _spacing(p, 0, 34)
    _run(p, '전력 수배전 계통 SCADA 이상탐지: 오토인코더 기초 모델의 진단과 모델 종류·크기·기법 개선안', 10.5, False, NAVY)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; _spacing(p, 0, 120); _border(p, LINE, 6, 6)
    _run(p, '주제: 토폴로지 인지 그래프 기반 조기 이상탐지    /    대상: 154kV 수전 ~ 220V 수배전 (WinCC OA)', 8, False, GREY)

    # I
    h1(doc, 'I. 개요 (1차 결과와 개선 방향)')
    body(doc, '1차에서는 Isolation Forest, PCA 재구성, 오토인코더(AE) 세 가지 비지도 기초 모델을 적용하였고, 정상만 학습한 AE가 '
              '가장 높은 성능을 보였다. 이번 단계에서는 같은 파이프라인을 공개 라벨 벤치마크(WADI), 전력 테스트베드(EPIC), 현장 형식의 '
              'FMCS 트렌드 데이터에 그대로 재측정하여 기초 AE의 한계를 진단하고, 이를 근거로 모델 종류, 크기, 학습·스코어링 기법의 '
              '개선 계획을 수립한다. 개선은 세 축으로 진행한다. ')
    for h, t in [('시간 맥락: ', '시점 단위 AE를 윈도우 기반 시계열 AE(Window/Conv/LSTM)로 확장한다.'),
                 ('스코어링: ', '센서별 오차 정규화, 상위 k 집계, 인과적 평활로 오경보를 줄이고 임계를 안정화한다.'),
                 ('도메인 지식: ', '물리 잔차(P = √3·V·I·PF)와 계통 토폴로지를 피처와 그래프 prior로 주입한다(GDN).')]:
        bullet(doc, h, t)

    # II
    h1(doc, 'II. 기초 모델 진단 (실측)')
    dsrow = lambda name, rep, n, qk='F1@q': [name, n, f3(pick(rep, B, 'IF', 'ROC-AUC')), f3(pick(rep, B, 'PCA', 'ROC-AUC')),
                                  f3(pick(rep, B, 'MLP-AE', 'ROC-AUC')), f3(pick(rep, B, 'MLP-AE', 'F1*')), f3(pick(rep, B, 'MLP-AE', qk))]
    caption(doc, '표 1. 1차 기초 모델(동일 설정)의 데이터셋별 실측 성능 — ROC-AUC, AE의 F1 (3회 시드 평균)')
    table(doc, [['데이터셋', '구성 / 평가 이벤트', 'IF AUC', 'PCA AUC', 'AE AUC', 'AE F1(최적)', 'AE F1(운영 임계)'],
                dsrow('WADI', W, '센서 122개, 10초, 공격 14건'),
                dsrow('EPIC', E, '계측 162개, 2초, 전력 이상 20건'),
                dsrow('FMCS 트렌드', Fr, f"태그 {Fr['info']['D']}개, 1분, 이상 이벤트 {Fr['info']['n_events']}건", 'F1@qS')],
          [2.2, 4.6, 1.6, 1.6, 1.6, 1.9, 2.3], align_right_from=2)
    note(doc, '※ F1(최적)은 PR 곡선에서 최대인 F1이다. F1(운영 임계)는 정상 검증 구간의 99% 분위수를 임계로 쓴 값으로, 배포 시 실제로 쓰는 방식이다. '
              'FMCS는 차단기 STATUS가 평상 개폐 구성인 시점만으로 임계를 산정했다(IV장 참고). FMCS 트렌드는 대상 계통의 토폴로지, 명명규칙, '
              'Oracle 저장 형식(3초 exception 압축)을 그대로 따른 시뮬레이션 트렌드에 이상·운전 시나리오를 주입해 채점하였다.')
    body(doc, '실측 결과에서 기초 AE의 한계는 다음 네 가지로 정리된다(그림 1(a)).', 50)
    bullet(doc, '시간 맥락 부재: ', '시점 단위 재구성은 완만한 드리프트나 순서가 어긋난 제어 동작을 정상 값의 조합으로 복원해 버린다.')
    bullet(doc, '오차 스케일 편중: ', f'단순 평균 오차는 변동 폭이 큰 소수 센서가 지배한다. WADI에서는 분석기 센서 1개의 교정 변화만으로 '
                               f'AE의 ROC-AUC가 {f3(pick(Wall, B, "MLP-AE", "ROC-AUC"))}까지 떨어졌다.')
    bullet(doc, '임계 불안정: ', '점 단위 판정은 순간 잡음에 민감해, 정상 구간에서도 운영 임계를 자주 넘는다.')
    bullet(doc, '운전 이벤트 오인: ', '차단기 개폐, 절체(ATS), 계획정비 같은 정상 운전 변동이 큰 오차를 만들어 오경보와 임계 왜곡을 일으킨다.', 40)
    figure(doc, RES / 'report' / 'fig1_wadi_timeline.png', 14.2,
           '[그림 1] WADI 테스트 구간 이상 점수: (a) 1차 기초 AE, (b) 개선 구성 — 점선은 정상 검증 99% 운영 임계')

    # III
    h1(doc, 'III. 개선 계획 ① 모델 종류와 크기')
    body(doc, '모델은 1차 AE를 기준선으로 두고, 시간 맥락을 다루는 방식이 다른 세 가지 시계열 AE와 센서 간 관계를 명시적으로 학습하는 '
              '그래프 모델(GDN)로 확장한다. 크기는 #3 경량화와 현장 배포(엣지 서버)를 고려해 파라미터 10만 개 이하를 기본 목표로 한다(그림 2(c)).', 60)
    caption(doc, '표 2. 개선 후보 모델의 구조와 크기 (파라미터 수는 WADI 122개 센서 기준)')
    table(doc, [['모델', '구조', '입력', '크기', '역할'],
                ['MLP-AE (기준)', '122-64-16-64-122, ReLU', '단일 시점', '17.9k', '1차 기초 모델'],
                ['Window-AE', '윈도우 펼침 MLP, 256-32-256', '30시점', '1.89M', '시간 맥락(단순 확장)'],
                ['Conv-AE', '1D-Conv 2층(64ch, k=5, stride 2) + 전치합성곱', '30시점', '87.6k', '국소 시간 패턴'],
                ['LSTM-AE', 'LSTM 인코더(h=64) → 잠재 32 → LSTM 디코더', '30시점', '83.2k', '순차 의존성(주력 후보)'],
                ['GDN', '센서 임베딩 64, 상위 15 이웃 그래프 어텐션, 다음 시점 예측', '29→1시점', '14.3k', '센서 관계·국소화'],
                ['GDN-prior', 'GDN + 계통 토폴로지 이웃 고정(같은 설비+상하류)', '15→1분', '%.1fk*' % (GDNP / 1e3), '위상 prior 주입(FMCS)']],
          [2.4, 6.6, 1.7, 1.4, 3.7], align_right_from=2)
    note(doc, '※ 윈도우는 WADI 30×10초(5분), EPIC 30×2초(60초), FMCS 15×1분. * GDN-prior는 FMCS 947개 피처(태그+물리 잔차) 기준. '
              'Window-AE는 입력 차원(센서×윈도우)에 비례해 커지므로 경량화 대상에서 제외하고 비교용으로만 둔다.')

    # IV
    h1(doc, 'IV. 개선 계획 ② 학습·스코어링 기법')
    for h, t in [
        ('센서별 robust 오차 정규화: ', '검증 구간 센서별 오차의 중앙값·IQR로 (e − median)/(IQR + ε)를 계산해 센서 간 스케일 차이를 없앤다.'),
        ('상위 k 집계 + 인과적 평활: ', '상위 5개 센서의 정규화 오차 평균을 스코어로 써 국소 이상이 희석되지 않게 하고, 과거 60초(FMCS 6분) 이동평균으로 순간 잡음을 억제한다(온라인 적용 가능).'),
        ('센서 드리프트 필터: ', '운영 입력의 20% 이상이 학습 범위를 벗어난 센서는 계측 교정 문제로 분리해 별도 알림으로 돌린다(라벨 미사용).'),
        ('물리 잔차 피처: ', '전력계 설비마다 r = (P − √3·V·I·PF/100)/P₉₅(PF 부호 유지)를 추가해, CT 드리프트·전력계 오프셋처럼 단일 태그만 어긋나는 이상을 직접 드러낸다.'),
        ('학습 프로토콜: ', '정상 윈도우만 학습, 정상 마지막 10~20%로 조기 종료(patience 5), Adam(lr 1e-3, batch 256), Min-Max 후 ±5 클리핑, 시드 3회 평균으로 보고한다.'),
        ('운영 임계와 운전 컨텍스트: ', '임계는 정상 검증 스코어의 99% 분위로 고정하되, FMCS는 차단기 STATUS가 평상 개폐 구성인 시점만으로 산정하고 운전 이벤트 구간 오경보율을 따로 관리한다.')]:
        bullet(doc, h, t)

    # V
    h1(doc, 'V. 예비 검증 결과')
    def row(name, rep, base_rep, m, qk='F1@q'):
        a0, a1 = pick(base_rep, B, 'MLP-AE', 'ROC-AUC'), pick(rep, I, m, 'ROC-AUC')
        f0, f1 = pick(base_rep, B, 'MLP-AE', 'F1*'), pick(rep, I, m, 'F1*')
        q0, q1 = pick(base_rep, B, 'MLP-AE', qk), pick(rep, I, m, qk)
        return [name, m + ' + 개선 스코어링', f'{f3(a0)} → {f3(a1)}', f'{f3(f0)} → {f3(f1)}', f'{f3(q0)} → {f3(q1)}', f'{(f1 / f0 - 1) * 100:+.0f}%']
    caption(doc, '표 3. 기초 AE(1차 방식) 대비 개선 구성의 성능 변화 (3회 시드 평균)')
    table(doc, [['데이터셋', '개선 구성', 'ROC-AUC', 'F1(최적)', 'F1(운영 임계)', 'F1 향상'],
                row('WADI', W, W, bw), row('EPIC', E, E, be),
                row('FMCS (태그만)', Fr, Fr, bfr, 'F1@qS'), row('FMCS (+물리 잔차)', Fp, Fr, bf, 'F1@qS')],
          [2.6, 4.2, 2.4, 2.4, 2.4, 1.6], align_right_from=2)
    figure(doc, RES / 'report' / 'fig3_gain_ablation.png', 14.2,
           '[그림 2] (a) 데이터셋별 F1 변화, (b) WADI 스코어링 단계를 하나씩 더할 때의 F1, (c) 모델 크기 대비 F1')
    lw, le, lf = W['localization'], E['localization'], Fp['localization']
    gdn = [f"WADI {f3(pick(W, I, 'GDN', 'F1*'))}" if 'GDN' in W[I] else None,
           f"EPIC {f3(pick(E, I, 'GDN', 'F1*'))}" if 'GDN' in E[I] else None]
    gdn = ', '.join(g for g in gdn if g)
    body(doc, [('결과 해석. ', True),
               (f'WADI에서는 시간 맥락({bw})과 개선 스코어링의 효과가 단계마다 누적되었다(그림 2(b)). 순간형 이상이 중심인 EPIC에서는 '
                f'{be}가 가장 좋아, 주력 모델은 데이터셋별 검증으로 선택한다. FMCS에서는 물리 잔차의 효과가 가장 커 ROC-AUC가 '
                f'{f3(pick(Fr, I, bfr, "ROC-AUC"))}에서 {f3(pick(Fp, I, bf, "ROC-AUC"))}로 올랐고, 기초 AE가 놓친 완만한 드리프트형 '
                f'이상도 임계를 넘었다(그림 3(b)). 계획정비 구간까지 임계 산정에 넣으면 F1이 {f3(pick(Fp, I, bf, "F1@q"))}에 그쳐, '
                f'STATUS 기반 임계가 필수임을 확인하였다.', False)])
    figure(doc, RES / 'report' / 'fig4_fmcs_loc.png', 14.2,
           '[그림 3] FMCS 테스트 4일 이상 점수 (a) 1차 AE, (b) 개선 구성, (c) 원인 센서 국소화 적중률(상위 1/3/5위)')
    g = lambda rep, m, k='F1*': f3(pick(rep, I, m, k))
    body(doc, [('진단과 그래프 모델. ', True),
               (f'원인 센서 상위 3위 적중률은 WADI {lw[bw]["top3"] * 100:.0f}%, EPIC {le[be]["top3"] * 100:.0f}%, '
                f'FMCS {lf[bf]["top3"] * 100:.0f}%로 #3 진단 에이전트의 원인 후보로 쓸 수 있다(그림 3(c)). 튜닝 전 GDN의 F1은 '
                f'WADI {g(W, "GDN")}, EPIC {g(E, "GDN")}, FMCS {g(Fp, "GDN")}로 아직 시계열 AE보다 낮고, 정적 토폴로지 prior(GDN-prior '
                f'{g(Fp, "GDN-prior")})는 차단기 개폐 직후 오경보율이 {pick(Fp, I, "GDN-prior", "FAR_op") * 100:.0f}%로 높아 STATUS로 '
                f'결선을 갱신하는 동적 그래프가 필요하다.', False)])

    # VI
    h1(doc, 'VI. 평가 계획과 진행 일정')
    for h, t in [
        ('평가: ', 'SWaT·WADI(공격 라벨), EPIC(전력 이상 주입), FMCS 트렌드(이상/운전/데이터 품질 구분 라벨)에 같은 프로토콜로 ROC-AUC, PR-AUC, F1(최적·운영 임계), 국소화 top-k, 운전 이벤트 오경보율을 보고한다.'),
        ('1단계 (AE 개선 확정): ', '스코어링과 시계열 AE 비교를 마무리하고, 윈도우 길이·잠재 차원·k에 대한 민감도 분석을 수행한다.'),
        ('2단계 (그래프 모델): ', 'GDN의 이웃 수·윈도우·임베딩을 튜닝하고, STATUS로 결선을 갱신하는 동적 토폴로지 prior를 학습 그래프·정적 prior와 ablation해 위상 정보의 기여를 정량화한다.'),
        ('3단계 (#3 연계): ', '선정 모델에 pruning·int8 양자화·증류를 적용해 크기·지연 대비 성능 손실을 측정하고, 상위 기여 센서를 LangGraph 진단 에이전트에 연결한다.')]:
        bullet(doc, h, t)
    doc.save(out_path)
    print('saved', out_path)


if __name__ == '__main__':
    build(ROOT / '기초모델개선계획_보고서.docx')
