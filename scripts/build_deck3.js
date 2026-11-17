// #3 발표자료(개선 모델 성능 분석) — 1차 발표자료(260927) 양식 재현, 수치는 results/report3/analysis.json에서 읽음.
// 사용: NODE_PATH=<pptxgenjs가 설치된 node_modules> node scripts/build_deck3.js
//       → 발표자료_3차_개선모델성능분석.pptx
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..");
const A = JSON.parse(fs.readFileSync(path.join(ROOT, "results/report3/analysis.json"), "utf8"));
const OUT = path.join(ROOT, "발표자료_3차_개선모델성능분석.pptx");
const APPLY_THEME = process.env.APPLY_THEME;   // 스킬의 scripts/apply_theme.js 경로

// 1차 발표자료 팔레트 (ppt/slides/*.xml에서 추출)
const THEME = {
  name: "SCADA Navy",
  headFontFace: "맑은 고딕",
  bodyFontFace: "맑은 고딕",
  colors: {
    dk1: "232A35", lt1: "FFFFFF", dk2: "16233A", lt2: "F6F8FC",
    accent1: "185FA5", accent2: "1D9E75", accent3: "EF9F27", accent4: "D85A30",
    accent5: "7F77DD", accent6: "6B7280", hlink: "185FA5", folHlink: "7F77DD",
  },
};
const HEX = { border: "D7DEE8", shadow: "B9C2D0", ice: "C7D3E6", muted: "93A4BE", tint: "EEF2F8",
              navy: "16233A", blue: "185FA5", green: "1D9E75", orange: "EF9F27", red: "D85A30", grey: "6B7280", base: "B9C2D0" };

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";                      // 13.33 × 7.5 in (1차와 동일)
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.author = "정기흔";
pres.title = "산업인공지능 문제해결 프로젝트 #3 개선 모델 성능 분석";
const C = pres.SchemeColor;

// ---------------------------------------------------------------- 레이아웃
pres.defineSlideMaster({
  title: "TITLE_DARK",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.62, y: 1.95, w: 12, h: 1.1, fontSize: 48, bold: true,
                                color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: C.background1 },
  objects: [
    { text: { text: "", options: { shape: pres.shapes.OVAL, x: 0.62, y: 0.64, w: 0.16, h: 0.16, fill: { color: C.accent3 }, line: { color: C.accent3 } } } },
    { placeholder: { options: { name: "title", type: "title", x: 0.9, y: 0.42, w: 11.8, h: 0.6, fontSize: 29, bold: true,
                                color: C.text1, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CLOSING_DARK",
  background: { color: C.text2 },
  objects: [
    { text: { text: "", options: { shape: pres.shapes.OVAL, x: 0.62, y: 0.78, w: 0.2, h: 0.2, fill: { color: C.accent3 }, line: { color: C.accent3 } } } },
    { placeholder: { options: { name: "title", type: "title", x: 0.95, y: 0.5, w: 11.5, h: 0.75, fontSize: 32, bold: true,
                                color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
  ],
});

// ---------------------------------------------------------------- 공통 요소
const shadow = () => ({ type: "outer", color: HEX.shadow, blur: 4, offset: 2, angle: 90, opacity: 0.45 });
function card(s, x, y, w, h, name, fill = C.background2) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.06, fill: { color: fill },
    line: { color: HEX.border, width: 0.75 }, shadow: shadow(), objectName: name });
}
function badge(s, x, y, n, color, d = 0.5) {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color }, line: { color }, objectName: `badge ${n}` });
  s.addText(String(n), { x, y, w: d, h: d, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle",
    margin: 0, isTextBox: true });
}
function text(s, t, o) { s.addText(t, Object.assign({ isTextBox: true, margin: 0, color: C.text1, fontSize: 14, valign: "top" }, o)); }
function pill(s, x, y, w, h, t, color) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.04, fill: { color }, line: { color }, objectName: `label ${t}` });
  text(s, t, { x, y, w, h, fontSize: 13, bold: true, color: C.background1, align: "center", valign: "middle" });
}
const f3 = (v) => v.toFixed(3);
const pct = (a, b) => `${a / b - 1 >= 0 ? "+" : ""}${Math.round((a / b - 1) * 100)}%`;
const best = (k) => ["ae", "gdn", "ens"].reduce((m, c) => (A[k][c].F1op > A[k][m].F1op ? c : m), "ae");
const nameOf = (k, c) => ({ ae: A[k].ae_model, gdn: A[k].gdn_model, ens: A[k].ens_models.join("+") }[c]);
const DSN = { wadi: "WADI", epic: "EPIC", fmcs: "FMCS 트렌드" };
const CHART = { catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", legendFontFace: "+mn-lt", dataLabelFontFace: "+mn-lt",
  catAxisLabelColor: HEX.grey, valAxisLabelColor: HEX.grey, catAxisLabelFontSize: 12, valAxisLabelFontSize: 11,
  valGridLine: { color: "E5E9F0", size: 0.75 }, catGridLine: { style: "none" }, legendFontSize: 12, legendColor: "232A35",
  dataLabelFontSize: 10, dataLabelColor: "232A35", valAxisLineShow: false, catAxisLineShow: true };
const F = A.fmcs, ab = A.ablation, T = A.fmcs_types, G = F.gdn_all;
const S = (name) => pres.addSlide({ masterName: name, sectionTitle: sec });
let sec;

// ================================================================ 1. 표지
pres.addSection({ title: "도입" }); sec = "도입";
let s = S("TITLE_DARK");
s.addShape(pres.shapes.OVAL, { x: 0.62, y: 1.2, w: 0.22, h: 0.22, fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: "dot" });
text(s, "산업인공지능 문제해결 프로젝트   #3", { x: 1.0, y: 1.1, w: 8, h: 0.42, fontSize: 16, bold: true, color: C.accent3, valign: "middle" });
s.addText("전력 수배전 계통 이상탐지", { placeholder: "title" });
text(s, "SCADA 트렌드 기반 조기 이상탐지   ｜   개선 모델 성능 분석", { x: 0.62, y: 3.3, w: 12, h: 0.5, fontSize: 19, color: HEX.ice });
s.addShape(pres.shapes.LINE, { x: 0.65, y: 4.15, w: 2.6, h: 0, line: { color: C.accent3, width: 1.5 }, objectName: "divider" });
text(s, [{ text: "발표자  ", options: { color: HEX.muted } }, { text: "정기흔", options: { bold: true, color: C.background1 } }],
  { x: 0.62, y: 4.5, w: 6, h: 0.4, fontSize: 16 });
text(s, "대상: 154kV 수전 ~ 220V 수배전 (WinCC OA)", { x: 0.62, y: 4.95, w: 8, h: 0.35, fontSize: 13, color: HEX.muted });
s.addNotes("1차에서 데이터셋과 기초 오토인코더를 정했고, 2차에서 개선 계획을 세웠다. 이번 3차는 그 개선을 실제로 구현해 기초 모델 대비 얼마나, 왜 좋아졌는지를 보고한다.");

// ================================================================ 2. 1차 이후 진행 경과
s = S("CONTENT");
s.addText("1차 발표 이후 진행 경과", { placeholder: "title" });
text(s, "데이터셋 선정(#1) → 개선 계획(#2) → 구현과 성능 분석(#3)까지 진행하였다.", { x: 0.62, y: 1.3, w: 12, h: 0.4, fontSize: 15, color: C.accent6 });
const steps = [
  ["09.27", "#1 발표", "데이터셋 선정·기초 모델", "공개 벤치마크 + 현장 SCADA\nIF·PCA·AE, 합성 AUC 0.874", C.accent1],
  ["10.13~14", "#2 보고서", "기초 모델 개선 계획", "WADI·EPIC·FMCS 재측정\n시계열 AE·GDN 개선 설계", C.accent2],
  ["10.20~21", "#3 연구", "개선 기법 구현·학습", "FMCS 42일 · 이상 10종\n62회 학습 (M2 GPU 6시간)", C.accent3],
  ["10.21", "#3 보고서", "개선 모델 성능 분석", "기초 대비 향상 비율·원인\n단계별·유형별·GDN 비교", C.accent4],
];
const sx = 0.62, cw = 2.88, gap = 0.17;
s.addShape(pres.shapes.LINE, { x: sx + 0.5, y: 2.47, w: 4 * cw + 3 * gap - 1.0, h: 0, line: { color: HEX.border, width: 2 }, objectName: "timeline" });
steps.forEach(([d, tag, head, body, col], i) => {
  const x = sx + i * (cw + gap);
  badge(s, x + cw / 2 - 0.25, 2.22, i + 1, col);
  text(s, d, { x, y: 1.85, w: cw, h: 0.3, fontSize: 13, bold: true, color: col, align: "center" });
  card(s, x, 2.95, cw, 2.35, `step ${i + 1}`);
  text(s, tag, { x: x + 0.22, y: 3.12, w: cw - 0.44, h: 0.3, fontSize: 13, bold: true, color: col });
  text(s, head, { x: x + 0.22, y: 3.45, w: cw - 0.44, h: 0.4, fontSize: 16, bold: true });
  text(s, body, { x: x + 0.22, y: 4.0, w: cw - 0.44, h: 1.15, fontSize: 13, color: C.accent6, paraSpaceAfter: 6 });
});
card(s, 0.62, 5.65, 12.08, 0.85, "this talk", HEX.tint);
text(s, [{ text: "이번 발표  ", options: { bold: true, color: C.accent1 } },
         { text: "#2에서 계획한 개선을 모두 구현해, 1차 기초 오토인코더와 같은 데이터·같은 분할에서 얼마나·왜 좋아졌는지를 보인다." }],
  { x: 0.85, y: 5.65, w: 11.7, h: 0.85, fontSize: 14, valign: "middle" });
s.addNotes("9월 27일 1차 발표 이후 활동. 10월 중순 2차 개선 계획 보고서에서 세 데이터셋으로 기초 AE 한계를 실측하고 개선 방향을 정했다. 10월 20~21일에는 FMCS 트렌드 42일치를 만들고 개선 기법을 전부 구현해 62회 학습했다. 결과를 3차 보고서로 정리했다.");

// ================================================================ 3. 개선 내용 비교
pres.addSection({ title: "개선 내용" }); sec = "개선 내용";
s = S("CONTENT");
s.addText("개선 내용: 기초 모델에서 무엇을 바꿨나", { placeholder: "title" });
const rowsCmp = [
  ["모델", "시점 단위 MLP-AE", "15분 윈도우 LSTM/Conv-AE + GDN 4변형"],
  ["입력", "태그 값, Min-Max 정규화", "+ 물리 잔차 + KCL 잔차, 분위수 스케일"],
  ["스코어", "전체 센서 평균 오차", "센서별 정규화 → 상위 5개 → 인과 평활"],
  ["임계", "정상 검증 99% 분위", "개폐 직후 설비는 STATUS로 제외 후 99%"],
];
[["1차 기초 모델", C.accent6, 1], ["개선 모델", C.accent1, 2]].forEach(([h, col, j], k) => {
  const x = k === 0 ? 0.62 : 7.05;
  card(s, x, 1.45, 5.65, 4.75, h);
  pill(s, x + 0.25, 1.68, 1.9, 0.42, h, col);
  rowsCmp.forEach((r, i) => {
    const y = 2.4 + i * 0.92;
    text(s, r[0], { x: x + 0.3, y, w: 1.0, h: 0.7, fontSize: 13, bold: true, color: col, valign: "middle" });
    text(s, r[j], { x: x + 1.35, y, w: 4.1, h: 0.7, fontSize: 15, bold: k === 1, valign: "middle" });
  });
});
s.addShape(pres.shapes.RIGHT_ARROW, { x: 6.37, y: 3.55, w: 0.6, h: 0.55, fill: { color: C.accent3 }, line: { color: C.accent3 }, objectName: "arrow" });
text(s, "같은 데이터·같은 분할에서 비교. 향상률 = (개선 − 기초) / 기초. 개선 AE는 시드 3회 평균, GDN 변형은 시드 1회.",
  { x: 0.62, y: 6.45, w: 12, h: 0.35, fontSize: 12, italic: true, color: C.accent6 });
s.addNotes("왼쪽이 1차 기초 모델, 오른쪽이 개선 모델. 모델 구조, 입력 피처, 스코어 집계, 임계 산정의 네 군데를 바꿨다. 특히 물리·KCL 잔차와 운전 컨텍스트(STATUS) 처리가 전력 계통 도메인 지식을 넣은 부분이다.");

// ================================================================ 4. 실험 설정
s = S("CONTENT");
s.addText("실험 설정: 데이터셋과 평가 지표", { placeholder: "title" });
const hdr = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text2 }, fontSize: 13 } });
s.addTable([
  [hdr("데이터셋"), hdr("구성"), hdr("평가 이상"), hdr("역할")],
  ["WADI", `배수 ICS, 센서 ${A.wadi.D}개, 10초`, `공격 ${A.wadi.n_events}건`, "라벨 벤치마크 채점"],
  ["EPIC", `전력 테스트베드, 계측 ${A.epic.D}개, 2초`, `전력 이상 ${A.epic.n_events}건`, "전력 도메인 검증"],
  ["FMCS 트렌드", `대상 계통 형식, 피처 ${F.D.toLocaleString()}개, 1분\n학습 26일 · 검증 4일 · 평가 12일`, `10종 ${F.n_events}건`, "토폴로지·운전 컨텍스트 적용"],
], { x: 0.62, y: 1.45, w: 12.08, colW: [2.0, 5.1, 1.9, 3.08], fontSize: 13, color: C.text1, valign: "middle",
     border: { type: "solid", pt: 0.75, color: HEX.border }, rowH: [0.45, 0.55, 0.55, 0.8], margin: [0.05, 0.12, 0.05, 0.12],
     objectName: "dataset table" });
text(s, "■ 평가 지표", { x: 0.62, y: 4.1, w: 6, h: 0.35, fontSize: 16, bold: true, color: C.accent1 });
const mets = [["ROC-AUC", "임계와 무관한 분리 능력"], ["F1(최적)", "PR 곡선에서 최대인 F1"], ["F1(운영 임계)", "검증 99% 임계로 판정 — 배포 시 실제 성능"],
              ["이벤트 탐지율", "이상 구간 중 한 번이라도 경보한 비율"], ["운전 이벤트 오경보율", "절체·정비 등 정상 운전 구간의 경보 비율"]];
mets.forEach(([h, d], i) => {
  const x = 0.62 + (i % 3) * 4.08, y = 4.6 + Math.floor(i / 3) * 1.05;
  card(s, x, y, 3.92, 0.9, h, i === 2 ? HEX.tint : C.background2);
  text(s, h, { x: x + 0.2, y: y + 0.1, w: 3.5, h: 0.32, fontSize: 14, bold: true, color: i === 2 ? C.accent1 : C.text1 });
  text(s, d, { x: x + 0.2, y: y + 0.45, w: 3.6, h: 0.35, fontSize: 12, color: C.accent6 });
});
text(s, "학습 환경\nApple M2 GPU(MPS), PyTorch\nFMCS 62회 학습 약 6시간", { x: 8.98, y: 5.65, w: 3.7, h: 0.9, fontSize: 12, italic: true,
  color: C.accent6, valign: "middle" });
s.addNotes("세 데이터셋에서 비교했다. FMCS 트렌드는 대상 계통의 토폴로지, 태그 명명, 저장 형식을 따른 데이터에 이상 10종을 현장 수준 크기로 넣어 채점했다. 핵심 지표는 F1(운영 임계)로, 배포했을 때 실제로 나오는 판정 성능이다.");

// ================================================================ 5. 종합 결과
pres.addSection({ title: "결과" }); sec = "결과";
s = S("CONTENT");
s.addText("종합 결과: 기초 오토인코더 대비 향상 비율", { placeholder: "title" });
["wadi", "epic", "fmcs"].forEach((k, i) => {
  const c = best(k), x = 0.62 + i * 4.08, col = [C.accent6, C.accent2, C.accent1][i];
  card(s, x, 1.4, 3.92, 1.75, `stat ${k}`);
  text(s, DSN[k], { x: x + 0.25, y: 1.55, w: 2.2, h: 0.32, fontSize: 14, bold: true, color: col });
  text(s, nameOf(k, c), { x: x + 1.7, y: 1.55, w: 2.0, h: 0.32, fontSize: 12, color: C.accent6, align: "right" });
  text(s, pct(A[k][c].F1op, A[k].base.F1op), { x: x + 0.25, y: 1.9, w: 3.4, h: 0.75, fontSize: 44, bold: true, color: col });
  text(s, `F1(운영 임계) ${f3(A[k].base.F1op)} → ${f3(A[k][c].F1op)}`, { x: x + 0.25, y: 2.68, w: 3.5, h: 0.32, fontSize: 13, color: C.accent6 });
});
const fam = [["base", "1차 기초 AE"], ["ae", "개선 AE"], ["gdn", "GDN(최적 변형)"], ["ens", "AE+GDN 앙상블"]];
s.addChart(pres.charts.BAR, fam.map(([c, l]) => ({ name: l, labels: ["WADI", "EPIC", "FMCS 트렌드"], values: ["wadi", "epic", "fmcs"].map((k) => +A[k][c].F1op.toFixed(3)) })),
  Object.assign({}, CHART, { x: 0.62, y: 3.4, w: 7.9, h: 3.55, barDir: "col", barGrouping: "clustered", barGapWidthPct: 60,
    chartColors: [HEX.base, HEX.navy, "B5487A", "6E8CC4"], showLegend: true, legendPos: "t", valAxisMinVal: 0, valAxisMaxVal: 0.8,
    valAxisMajorUnit: 0.2, showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00",
    showTitle: true, title: "F1(운영 임계): 모델 계열별", titleFontFace: "+mn-lt", titleFontSize: 13, titleColor: "232A35", objectName: "F1op chart" }));
card(s, 8.8, 3.4, 3.9, 3.55, "takeaways", HEX.tint);
text(s, "읽는 법", { x: 9.05, y: 3.58, w: 3.4, h: 0.35, fontSize: 15, bold: true, color: C.accent1 });
text(s, [
  { text: `FMCS: 기초 AE가 운전 이벤트 구간의 ${Math.round(F.base.FAR_op * 100)}%를 이상으로 판정 → 운영 임계가 무력화. 최종 ${Math.round(F[best("fmcs")].FAR_op * 100)}%`, options: { bullet: true, breakLine: true } },
  { text: `AUC ${f3(F.base["ROC-AUC"])} → ${f3(F[best("fmcs")]["ROC-AUC"])}, 이벤트 탐지 ${Math.round(F.base.event_recall * 100)} → ${Math.round(F[best("fmcs")].event_recall * 100)}%`, options: { bullet: true, breakLine: true } },
  { text: "WADI·EPIC은 토폴로지가 없어 개선 AE 단독이 최선", options: { bullet: true } },
], { x: 9.05, y: 4.0, w: 3.45, h: 2.8, fontSize: 13, paraSpaceAfter: 8 });
s.addNotes("운영 임계 F1 기준 향상률. FMCS가 +345%로 가장 큰데, 기초 AE는 절체·정비 같은 정상 운전을 대부분 이상으로 봐서 실제 판정이 거의 불가능했기 때문이다. WADI와 EPIC은 토폴로지 정보가 없어 GDN보다 개선 AE가 낫다.");

// ================================================================ 6. 향상 원인 ①: 단계별
pres.addSection({ title: "원인 분석" }); sec = "원인 분석";
s = S("CONTENT");
s.addText("향상 원인 ①: 개선 요소를 하나씩 추가", { placeholder: "title" });
const short = { "1차 기초 AE": "1차 AE", "+시계열 윈도우": "+윈도우", "+정규화·상위k·평활": "+정규화·top-k", "+물리 잔차": "+물리 잔차",
  "+KCL 잔차": "+KCL 잔차", "+강건 스케일링": "+강건 스케일", "+운전 컨텍스트": "+운전 컨텍스트", "+GDN 앙상블": "+GDN 앙상블" };
const labs = ab.map((a) => short[a.step] || a.step);
s.addChart(pres.charts.LINE, [
  { name: "F1(최적)", labels: labs, values: ab.map((a) => +a["F1*"].toFixed(3)) },
  { name: "F1(운영 임계)", labels: labs, values: ab.map((a) => +a.F1op.toFixed(3)) },
  { name: "운전 이벤트 오경보율", labels: labs, values: ab.map((a) => +a.FAR_op.toFixed(3)) },
], Object.assign({}, CHART, { x: 0.62, y: 1.35, w: 8.0, h: 5.5, chartColors: [HEX.navy, HEX.orange, HEX.base], lineSize: 2.5,
  lineDataSymbol: "circle", lineDataSymbolSize: 7, showLegend: true, legendPos: "t", valAxisMinVal: 0, valAxisMaxVal: 1, valAxisMajorUnit: 0.2,
  showValue: false, catAxisLabelFontSize: 11, catAxisLabelRotate: -30, objectName: "ablation chart" }));
const k = (st) => ab.findIndex((a) => a.step === st);
const iK = k("+KCL 잔차"), iC = k("+운전 컨텍스트"), iP = k("+물리 잔차");
const calls = [
  ["KCL 잔차", `AUC ${(ab[iK]["ROC-AUC"] - ab[iK - 1]["ROC-AUC"] >= 0 ? "+" : "")}${(ab[iK]["ROC-AUC"] - ab[iK - 1]["ROC-AUC"]).toFixed(3)}`,
   "상위 피더 P − 하위 계량 P 합. 설비 간 관계에서만 보이는 이상을 직접 드러내는 가장 큰 단일 기여", C.accent1],
  ["운전 컨텍스트", `오경보 ${Math.round(ab[iC - 1].FAR_op * 100)}→${Math.round(ab[iC].FAR_op * 100)}%`,
   "개폐 직후 2단계 이내 설비를 STATUS로 판별해 제외, 라벨 미사용. 운영 F1이 가장 크게 오른 단계", C.accent3],
  ["물리 잔차", `운영 F1 +${(ab[iP].F1op - ab[iP - 1].F1op).toFixed(3)}`, "P − √3·V·I·PF. CT 드리프트·PF 부호 반전 포착", C.accent2],
];
calls.forEach(([h, v, d, col], i) => {
  const y = 1.4 + i * 1.83;
  card(s, 8.9, y, 3.8, 1.65, h);
  text(s, h, { x: 9.12, y: y + 0.13, w: 2.0, h: 0.32, fontSize: 14, bold: true, color: col });
  text(s, v, { x: 10.6, y: y + 0.1, w: 1.9, h: 0.38, fontSize: 15, bold: true, color: col, align: "right" });
  text(s, d, { x: 9.12, y: y + 0.55, w: 3.4, h: 1.0, fontSize: 12, color: C.accent6 });
});
s.addNotes("한 요소씩 누적해 추가했을 때의 변화. 윈도우만 바꾸면 거의 그대로이고, 물리 잔차와 KCL 잔차에서 분리 능력이 크게 오르며, 운전 컨텍스트 마스크에서 오경보가 줄어 운영 F1이 크게 오른다. 즉 향상의 대부분은 모델 크기보다 전력 도메인 지식을 피처와 스코어링에 넣은 데서 왔다.");

// ================================================================ 7. 향상 원인 ②: 유형별
s = S("CONTENT");
s.addText("향상 원인 ②: 이상 유형별 이벤트 탐지율", { placeholder: "title" });
const TY = [["hidden_load", "미계량 부하", "KCL 잔차"], ["meter_offset", "전력계 오프셋", "KCL 잔차"], ["ct_drift", "CT 드리프트", "물리 잔차"],
            ["pf_sign_flip", "PF 부호 반전", "물리 잔차"], ["spike_burst", "전류 스파이크", "센서별 정규화"], ["sensor_stuck", "값 고착", "윈도우·정규화"],
            ["voltage_sag", "순간전압강하", "태그 값(전 설비 동시)"], ["oltc_hunting", "OLTC 헌팅", "정상 탭 동작과 유사"],
            ["pt_drift", "PT 드리프트", "미탐 — 형제 모선 전압 비교 필요"], ["ltr_overheat", "변압기 과열", "미탐 — 부하-온도 열모델 필요"]];
const cell = (v) => {
  const p = Math.round(v * 100), fill = p >= 80 ? HEX.navy : p >= 50 ? "6E8CC4" : p > 0 ? "D8E2F0" : "F6F8FC";
  return { text: `${p}%`, options: { align: "center", bold: p >= 80, fill: { color: fill }, color: p >= 50 ? "FFFFFF" : "232A35" } };
};
s.addTable([[hdr("이상 유형 (건수)"), hdr("드러나는 신호"), hdr("1차 AE"), hdr("개선 AE"), hdr("GDN")]].concat(
  TY.map(([t, ko, why]) => [`${ko} (${T[t].n})`, { text: why, options: { color: why.startsWith("미탐") ? HEX.red : "232A35" } },
                            cell(T[t].base), cell(T[t].ae), cell(T[t].gdn)])),
  { x: 0.62, y: 1.35, w: 8.6, colW: [2.2, 3.3, 1.03, 1.03, 1.04], fontSize: 13, color: C.text1, valign: "middle", rowH: 0.47,
    border: { type: "solid", pt: 0.75, color: "FFFFFF" }, margin: [0.03, 0.1, 0.03, 0.1], objectName: "type table" });
card(s, 9.5, 1.35, 3.2, 2.45, "new", HEX.tint);
text(s, "새로 잡은 유형", { x: 9.72, y: 1.5, w: 2.8, h: 0.35, fontSize: 15, bold: true, color: C.accent1 });
text(s, "미계량 부하·오프셋·CT 드리프트·스파이크는 탐지율 0~33% → 100%. 개별 태그는 정상 범위지만 물리식·KCL 관계가 깨지는 이상이다.",
  { x: 9.72, y: 1.95, w: 2.8, h: 1.75, fontSize: 12.5 });
card(s, 9.5, 4.0, 3.2, 2.55, "missed");
text(s, "남은 과제", { x: 9.72, y: 4.15, w: 2.8, h: 0.35, fontSize: 15, bold: true, color: C.accent4 });
text(s, "PT 드리프트는 V·P가 같은 비율로 변해 내부 물리식이 성립 → 같은 모선 형제 설비와의 비교 피처가 필요. 과열은 완만한 온도 상승 → 열모델 잔차.",
  { x: 9.72, y: 4.6, w: 2.8, h: 1.85, fontSize: 12.5 });
s.addNotes("FMCS 평가 구간 40건을 유형별로 본 것. 새로 잡은 유형은 대부분 태그 값 자체는 정상 범위인데 설비 내부 물리식이나 상하위 KCL 관계가 깨지는 경우다. PT 드리프트와 변압기 과열은 아직 못 잡고, OLTC 헌팅은 오히려 떨어졌다. 이 셋이 다음 단계의 피처 과제다.");

// ================================================================ 8. GDN
s = S("CONTENT");
s.addText("GDN 적용 효과: 토폴로지는 학습보다 주입", { placeholder: "title" });
const gv = [["GDN", "학습 그래프"], ["GDN-prior", "토폴로지 고정"], ["GDN-hybrid", "토폴로지+학습"], ["GDN-dyn", "동적(STATUS)"]].filter(([g]) => G[g]);
s.addChart(pres.charts.BAR, [
  { name: "F1(최적)", labels: gv.map((x) => x[1]), values: gv.map(([g]) => +G[g]["F1*"].toFixed(3)) },
  { name: "F1(운영 임계)", labels: gv.map((x) => x[1]), values: gv.map(([g]) => +G[g].F1op.toFixed(3)) },
  { name: "운전 이벤트 오경보율", labels: gv.map((x) => x[1]), values: gv.map(([g]) => +G[g].FAR_op.toFixed(3)) },
], Object.assign({}, CHART, { x: 0.62, y: 1.35, w: 7.6, h: 5.5, barDir: "col", barGrouping: "clustered", barGapWidthPct: 55,
  chartColors: [HEX.navy, HEX.orange, HEX.base], showLegend: true, legendPos: "t", valAxisMinVal: 0, valAxisMaxVal: 0.8, valAxisMajorUnit: 0.2,
  showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00", objectName: "GDN chart" }));
card(s, 8.5, 1.35, 4.2, 2.3, "overlap stat", HEX.tint);
text(s, `${(F.graph.learned_in_topology * 100).toFixed(1)}%`, { x: 8.75, y: 1.5, w: 2.2, h: 0.85, fontSize: 40, bold: true, color: C.accent1 });
text(s, `= 무작위 ${(F.graph.random_expect * 100).toFixed(1)}%`, { x: 10.7, y: 1.72, w: 1.9, h: 0.5, fontSize: 15, bold: true, color: C.accent6 });
text(s, "학습 그래프 이웃 중 실제 계통에서 2단계 이내인 설비 비율. 정상 데이터만으로는 계통 연결을 복원하지 못한다.",
  { x: 8.75, y: 2.45, w: 3.8, h: 1.1, fontSize: 12.5 });
text(s, [
  { text: `토폴로지 고정: F1(최적) ${f3(G["GDN-prior"]["F1*"])}, 오경보 ${Math.round(G["GDN-prior"].FAR_op * 100)}%로 최선`, options: { bullet: true, breakLine: true } },
  { text: `학습 이웃을 섞으면 오경보 ${Math.round(G["GDN-hybrid"].FAR_op * 100)}% (개폐에 같이 변하는 설비를 끌어들임)`, options: { bullet: true, breakLine: true } },
  { text: `STATUS 동적 그래프는 혼합 대비 운영 F1 ${(G["GDN-dyn"].F1op - G["GDN-hybrid"].F1op >= 0 ? "+" : "")}${(G["GDN-dyn"].F1op - G["GDN-hybrid"].F1op).toFixed(3)}로 소폭`, options: { bullet: true, breakLine: true } },
  { text: "학습 1회 35~90분(AE의 10~30배) → 경량화 필요", options: { bullet: true } },
], { x: 8.5, y: 3.9, w: 4.2, h: 2.9, fontSize: 13, paraSpaceAfter: 8 });
s.addNotes("GDN 변형 네 가지 비교. 계통 토폴로지를 이웃으로 고정한 쪽이 데이터로 그래프를 배우는 쪽보다 낫고 오경보도 가장 낮다. 학습 그래프는 실제 계통 연결과의 일치율이 무작위와 같았다. 그래서 토폴로지는 배울 대상이 아니라 사전 지식으로 넣어야 한다는 것이 이 과제 접근의 근거다.");

// ================================================================ 9. 사례
s = S("CONTENT");
s.addText("사례: 설비 간 관계로만 보이는 이상", { placeholder: "title" });
s.addImage({ path: path.join(ROOT, "results/report3/fig3_cases.png"), x: 0.62, y: 1.4, w: 8.4, h: 8.4 * 717 / 1626,
  altText: "미계량 부하와 CT 드리프트 사례의 원신호와 설비별 정규화 오차", objectName: "case figure" });
text(s, "(a)(b) 원신호, (c)(d) 해당 설비 피처의 정규화 오차(로그). 주황 구간이 실제 이상.", { x: 0.62, y: 5.25, w: 8.4, h: 0.3,
  fontSize: 11, italic: true, color: C.accent6 });
[["미계량 부하", `${Math.round(T.hidden_load.base * 100)}% → ${Math.round(T.hidden_load.ae * 100)}%`,
  "피더 P·I가 4~10% 늘지만 V·I·PF 관계는 성립. 태그만으로는 정상 부하 변동과 구분 불가 → 하위 ACB 합과의 KCL 잔차에서만 드러남", C.accent1],
 ["CT 드리프트", `${Math.round(T.ct_drift.base * 100)}% → ${Math.round(T.ct_drift.ae * 100)}%`,
  "전류만 4~12% 서서히 증가, 전력계 P는 그대로 → 물리 잔차 P − √3·V·I·PF가 벌어짐", C.accent2]].forEach(([h, v, d, col], i) => {
  const y = 1.4 + i * 2.05;
  card(s, 9.3, y, 3.4, 1.85, h);
  text(s, h, { x: 9.5, y: y + 0.13, w: 1.7, h: 0.32, fontSize: 14, bold: true, color: col });
  text(s, v, { x: 10.9, y: y + 0.1, w: 1.6, h: 0.38, fontSize: 15, bold: true, color: col, align: "right" });
  text(s, d, { x: 9.5, y: y + 0.55, w: 3.05, h: 1.25, fontSize: 12 });
});
card(s, 0.62, 5.75, 12.08, 1.0, "localization", HEX.tint);
text(s, [{ text: "국소화  ", options: { bold: true, color: C.accent1 } },
         { text: "오차가 해당 설비 피처에 집중 → 상위 k 피처를 그대로 원인 설비 후보로 제시하고, 진단 에이전트가 토폴로지 경로와 함께 설명한다." }],
  { x: 0.85, y: 5.75, w: 11.7, h: 1.0, fontSize: 14, valign: "middle" });
s.addNotes("왼쪽 미계량 부하는 피더 전력이 조금 늘 뿐 정상 부하 변동처럼 보여서 1차 AE는 오차가 거의 없다. 개선 모델은 하위 차단기 합과의 차이를 보므로 구간 전체에서 오차가 크게 뜬다. 오른쪽 CT 드리프트도 같은 원리다. 오차가 해당 설비에 몰리므로 원인 위치까지 바로 짚을 수 있다.");

// ================================================================ 10. 요약과 다음 단계
pres.addSection({ title: "정리" }); sec = "정리";
s = S("CLOSING_DARK");
s.addText("요약과 다음 단계", { placeholder: "title" });
const fk = best("fmcs");
[["결과", `운영 F1 향상 WADI ${pct(A.wadi[best("wadi")].F1op, A.wadi.base.F1op)} · EPIC ${pct(A.epic[best("epic")].F1op, A.epic.base.F1op)} · FMCS ${pct(F[fk].F1op, F.base.F1op)} (AUC ${f3(F.base["ROC-AUC"])} → ${f3(F[fk]["ROC-AUC"])})`, C.accent1],
 ["원인", `KCL·물리 잔차(관계형 이상 포착) + 운전 컨텍스트(오경보 ${Math.round(F.base.FAR_op * 100)} → ${Math.round(F[fk].FAR_op * 100)}%) + 토폴로지 고정 GDN`, C.accent2],
 ["한계", "PT 드리프트·변압기 과열 미탐, OLTC 헌팅 하락, GDN 학습 비용(시드 1회)", C.accent4]].forEach(([h, t, col], i) => {
  const y = 1.75 + i * 0.95;
  pill(s, 1.0, y, 2.2, 0.6, h, col);
  text(s, t, { x: 3.5, y, w: 9.2, h: 0.6, fontSize: 15, color: C.background1, valign: "middle" });
});
s.addShape(pres.shapes.LINE, { x: 1.0, y: 4.75, w: 11.7, h: 0, line: { color: "3A4E70", width: 1 }, objectName: "rule" });
text(s, "다음 단계 (#4 경량화 + 현장 적용)", { x: 1.0, y: 5.0, w: 11, h: 0.45, fontSize: 17, bold: true, color: C.accent3 });
text(s, [
  { text: "실 트렌드 데이터에 같은 파이프라인 적용·재검증, 미탐 유형용 피처(형제 모선 전압차, 열모델 잔차) 추가", options: { bullet: true, breakLine: true } },
  { text: "GDN 경량화(가지치기·지식 증류)와 다시드 검증", options: { bullet: true, breakLine: true } },
  { text: "상위 k 피처·토폴로지 경로 기반 LLM 진단 에이전트를 WinCC OA와 연계 (감시·진단 전용)", options: { bullet: true } },
], { x: 1.0, y: 5.5, w: 11.7, h: 1.6, fontSize: 14, color: "D8E2F0", paraSpaceAfter: 6 });
s.addNotes("정리하면 향상의 대부분은 전력 계통 지식(KCL·물리식·개폐 상태·토폴로지)을 모델에 넣은 데서 왔다. 못 잡은 유형과 GDN 비용은 4차에서 피처 추가와 경량화로 다루고, 탐지 결과를 설명하는 진단 에이전트를 붙인다.");

// ---------------------------------------------------------------- 저장
pres.writeFile({ fileName: OUT }).then(async () => {
  if (APPLY_THEME) await require(APPLY_THEME).applyTheme(OUT, THEME);
  console.log("saved", OUT);
});
