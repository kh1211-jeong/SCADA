# 작업 계획 (TASKS) — Claude Code용

`README.md`를 먼저 읽을 것. 이 문서는 **무엇을, 어떤 순서로** 만들지 정의한다.
각 작업은 "산출물"과 "완료 기준"을 가진다. 순서대로 진행하되, 데이터 검증(Phase 1)이
가장 먼저다. 라벨 없는 FMCS가 주력이므로 **공개 데이터로 먼저 파이프라인을 검증**한 뒤
FMCS에 이식하는 흐름을 지킨다.

---

## 데이터셋별 "무엇을 하나" 요약

| 데이터셋 | 용도 | 이 프로젝트에서 하는 일 |
|---|---|---|
| **FMCS (fmcs/)** | 주력, 현장 적용 | 압축 해제→다변량 시계열 복원→토폴로지 그래프→IF/PCA/AE→(#2)GDN→(#3)경량화+에이전트. 라벨 없어 프록시로 평가 |
| **SWaT (swat/)** | 채점(라벨) | Normal/Attack 라벨로 IF/PCA/AE의 F1/ROC-AUC 실측 → 기초 성능 근거 |
| **WADI (wadi/)** | 채점(라벨) | 정상+공격 라벨로 탐지 성능 실측, 규모 큰 검증 |
| **PowerGraph** | 그래프/설명 | GNN이 위험 상태/끊긴 선로를 맞히는지 라벨로 검증(시계열 아님). #2/#3의 설명가능성 근거 |
| HAI | 보류 | LFS 실패로 미다운로드. 필요 시 릴리스 zip으로 재취득 |

---

## Phase 0 — 환경/공통 ✅ (2026-09-28 완료)

- [x] `src/` 패키지 구조 생성(`data/`, `models/`, `agent/`, `topology/`),
      `requirements.txt`(pandas, numpy, scikit-learn, scipy, pyarrow, torch,
      torch-geometric, h5py, matplotlib, langgraph, langsmith) 작성 — 전부 설치 확인.
- [x] `src/config.py`에 데이터 경로 상수 정의. PowerGraph는 실제 중첩 경로
      (`{grid}/{grid}/raw`)를 반영하는 헬퍼 함수(`powergraph_cascade_raw_dir` 등) 포함.
- 완료 기준: `python -c "import src"` 성공, 경로 상수로 각 데이터 폴더 접근 가능. **확인됨.**
- 추가로 확인됨: `torch_geometric`은 python 3.13 + torch 2.14+cpu 조합에서 순정 pip
  설치로 문제없이 동작(별도 wheel index 불필요). PowerGraph `.mat`은 v7.3(HDF5)이라
  `h5py` 필수 — `scipy.io.loadmat`은 `NotImplementedError` 발생.

## Phase 1 — 데이터 로더 & 검증 (최우선)

### 1a. FMCS 로더 (핵심)

- [x] `src/data/synth_fmcs.py`: EGMS 연결 규칙 기반 FMCS 합성 트렌드 생성기 (README 3.6).
  2026-10-13 검증: 정상 구간 `P=√3·V·I·PF/100` 상대오차 2e-7, GCB=BTR 입력, 트립/절체/ATS,
  OLTC 헌팅, 순간전압강하, CT 드리프트, 통신 두절(행 누락) 동작 확인.
  아래 로더는 이 출력(`fmcs_synth/raw/*.csv.gz`)으로 먼저 개발한다.

**검증 완료(2026-09-28, `sample image/trend data sample.png` 실물 쿼리 결과 기준):**
1. offset은 **초(0~57), 한 행=1분** — 확인됨(`TRND_DATE`가 00:00:00→00:01:00→...로 1분
   증가, 문자열이 `0:78.66;3:78.8;...;57:x`).
2. 물리량 구분은 **`EQP_NAME` 접미사**(예: `VCB_3F11A10_CURRENT`) — 확인됨.
   `PARAM_CODE`는 캡처된 행 전부 `PVLAST`로 **상수**이므로 구분자가 아니다.

**⚠️ 아래 참조 구현의 버그(2026-09-28, mock 데이터로 재현 확인):**
`pd.Timestamp(trnd_date)`처럼 포맷을 지정하지 않고 파싱하면, 실 `TRND_DATE` 포맷
(`YY/MM/DD HH:MM:SS`, 예: `26/09/24 00:00:00`)을 dateutil이 **날짜별로 다르게** 오파싱한다
(day/month가 둘 다 12 이하인 날짜는 뒤바뀌고, 특정 조합은 **연도까지** 틀어짐 — 예:
`05/09/24`가 `2005-09-24`로 파싱됨). 가끔은 우연히 맞아 테스트를 통과하므로 발견이 늦어지기
쉽다. **반드시 `pd.to_datetime(trnd_date, format='%y/%m/%d %H:%M:%S')`로 명시할 것.**

- [ ] `src/data/fmcs.py`: `TAG_COMPRS_VAL` 압축 문자열 파서.
```python
import pandas as pd
def unpack_row(trnd_date, comprs_val):
    base = pd.to_datetime(trnd_date, format='%y/%m/%d %H:%M:%S')  # NOT bare pd.Timestamp()
    rows = []
    for pair in str(comprs_val).split(';'):
        if ':' not in pair:
            continue
        sec, val = pair.split(':', 1)
        try:
            rows.append((base + pd.Timedelta(seconds=int(sec)), float(val)))
        except ValueError:
            continue
    return rows   # [(timestamp, value), ...]
```
- [ ] 추출 CSV(여러 태그, 여러 파티션)를 읽어 **태그별 long → pivot(wide)** 시계열로 변환.
- [ ] 고정 간격(예: 3초 또는 1분) 리샘플 + 보간. "기록 없음"이 안정인지 결측인지 플래그.
- 산출물: `fmcs_wide.parquet`(index=timestamp, columns=태그), 결측 리포트.
- 완료 기준: 한 계통(예: 3F11A) 하루치가 규칙적 간격 다변량 프레임으로 복원됨.
- **`fmcs/`가 비어 있는 동안**: `scripts/winccoa/gen_mock_csv.py`가 위와 동일한
  `EQP_NAME,PARAM_CODE,TRND_DATE,TAG_COMPRS_VAL` 스키마로 가상 CSV를 생성하므로,
  이 로더를 실데이터 도착 전에 mock으로 먼저 개발·검증할 수 있다(가상임을 반드시 표기).

### 1b. SWaT 로더
- [ ] `src/data/swat.py`: `swat/merged.csv` 로드. `df.columns.str.strip()`,
      `y = (df['Normal/Attack']=='Attack').astype(int)`. 액추에이터(MV/P/UV) 상태값 처리.
- **실측 확인(2026-09-28)**: `y` 자체는 위 한 줄로 정확히 나온다. 하지만 `merged.csv`는
  normal(1,387,098행)+attack(54,621행)이 **파일 끝에 한 블록으로 이어붙은 것**이고 그
  경계에서 타임스탬프가 역행한다(README.md 3.2). **슬라이딩 윈도우/시퀀스 생성 시 이
  경계를 걸치지 않도록 명시적으로 끊을 것** — 안 그러면 정상 구간 끝과 공격 구간 시작이
  섞인 가짜 시퀀스가 생긴다. 표준 SWaT 공개본과 클래스 비율이 다르므로(3.79% vs 공식
  11.98%) 논문 수치 직접 비교 금지.
- 완료 기준: `(timestamps, X, y)` 반환, y의 Attack 비율 출력.

### 1c. WADI 로더
- [ ] `src/data/wadi.py`: `WADI_14days_new.csv`(정상), `WADI_attackdataLABLE.csv`(공격+라벨).
      첫 줄이 설명행이면 `skiprows=1`, 컬럼 공백 strip, NaN 처리(전방 채움/제거),
      라벨 컬럼(끝 컬럼, 보통 1=정상/-1=공격) → 0/1 매핑.
- **실측 확인(2026-09-28, README.md 3.3)**: `WADI_attackdataLABLE.csv`는 `skiprows=1`
  맞음, 라벨 1=정상/-1=공격 맞음(공격 비율 5.77%). 단 **`Time` 컬럼의 시(hour)가
  소실**되어 있으므로 `Date`+`Time` 직접 파싱 대신 **`Row`(1초 간격 순번)로 타임스탬프
  재구성**할 것. `WADI_14days_new.csv`엔 전부 NaN인 컬럼 4개(`2_LS_001_AL`,
  `2_LS_002_AL`, `2_P_001_STATUS`, `2_P_002_STATUS`) 존재 → drop. normal 파일은
  11일치 부분본(공식 14일치 아님) — 규모 비교 시 유의.
- 완료 기준: 정상/공격 프레임 정렬, y 분포 출력.

### 1d. PowerGraph 로더
- [ ] `src/data/powergraph.py`: PyTorch Geometric `InMemoryDataset`로 `dataset_cascades`의
      `{ieee24,ieee39,ieee118,uk}` 로드(노드=모선, 엣지=선로/변압기, 라벨=DNS 기반, exp=엣지 정답).
- **실측 확인(2026-09-28, README.md 3.4)**: `root=`는 `src/config.py`의
  `powergraph_cascade_raw_dir(grid)`(이중 중첩 `{grid}/{grid}/raw`) 사용. `.mat`은
  v7.3(HDF5) → `h5py`로 읽을 것(`scipy.io.loadmat` 불가). ieee24 기준 `blist.mat`의
  `bList`(2,38)=IEEE RTS-24 표준 토폴로지(24모선/38선로)와 일치 확인. `of_reg.mat`의
  `dns_MW`만 시나리오 21,500개짜리 **직접 float 배열**(회귀 타깃)이고, `Bf/Ef/Ef_nc/
  of_bi/of_mc`는 시나리오별 HDF5 object-reference 배열이라 역참조 루프가 필요.
- 완료 기준: 한 그리드의 그래프 개수/노드·엣지 피처 shape/라벨 분포 출력.

## Phase 2 — 전처리 & 피처 & 그래프

- [ ] `src/features.py`: 표준화, 슬라이딩 윈도우, 3상 불평형, **물리 잔차**
      `resid = P - sqrt(3)*V*I*cosphi`(FMCS/전력계 데이터에 한함).
- [ ] `src/topology.py`: 명명규칙 파서로 FMCS 태그 → 토폴로지 그래프(노드/엣지 리스트).
      EGMS 룰(GCB/BTR/VCB(K/Q)/Feeder/LTR/ACB, TIE/DIS, 예외: 분전반·고압기동반·MCC 제외) 반영.
      커버리지/고아 노드 리포트 출력.
- 완료 기준: 그래프가 GDN 입력 형식(edge_index)으로 변환 가능.

## Phase 3 — 기초 모델 (#1)

- [ ] `src/models/baseline.py`: **Isolation Forest / PCA 재구성 / Autoencoder(정상만 학습)**.
      이상 스코어 = 예측·재구성 오차. 임계 = 정상 95% 분위.
- [ ] `src/eval.py`: 라벨 있는 데이터(SWaT/WADI)에서 Precision/Recall/F1/ROC-AUC/PR-AUC 산출,
      이상 스코어 타임라인 + ROC 그래프 저장.
- [ ] FMCS: 라벨 없으므로 **합성 이상 주입 + 물리 pseudo-label**로 프록시 지표 + 정성 국소화.
- 산출물: `results/baseline_{swat,wadi,fmcs}.png`, 지표 표(json).
- 완료 기준: SWaT/WADI에서 3모델 F1/AUC가 나오고, FMCS에서 파이프라인이 끝까지 돈다.
- 참고: 기존 `baseline.py`(합성 데이터 버전)의 로더만 각 데이터셋에 맞게 교체하면 재사용 가능.

## Phase 4 — 모델 개선 (#2)

- [ ] `src/models/gdn.py`: GDN(그래프 기반). **학습 그래프 대신 실제 위상 그래프를 prior로 주입.**
- [ ] ablation: 학습 그래프 vs 물리 그래프, 물리 잔차 피처 유무.
- [ ] 공개 데이터 라벨로 **기초 모델 대비 향상률** 보고.
- 완료 기준: GDN vs IF/PCA/AE 비교표 + 위상 prior 효과 정량화.

## Phase 5 — 경량화 + 에이전트 (#3)

- [ ] 경량화: pruning / int8 양자화 / 증류 → 크기·지연 vs 지표 손실 표.
- [ ] `src/agent/`: **LangGraph 진단 에이전트**. 이상 스코어 발생 시 tool-calling으로
      (1) 기여 상위 태그 (2) 물리룰 검산 (3) 최근 DI 알람 시퀀스 (4) 토폴로지 인접 조회
      → 근본원인 가설 + 권장 조치 생성. 실행 경로는 LangSmith로 추적.
      역할 분리: **탐지=모델, 진단·설명=에이전트**.
- 완료 기준: 이상 1건에 대해 에이전트가 국소화된 원인+조치를 산출하는 데모.

---

## 검증/우선순위 체크리스트

1. ~~**[최우선] FMCS 압축 포맷 가정 2개 확인**~~ — ✅ 2026-09-28 확인됨(1a 참고).
   대신 **`unpack_row`의 날짜 파싱 버그**(포맷 미지정 시 침묵 오파싱)를 반드시 고칠 것.
2. SWaT/WADI 로더가 라벨을 정확히 0/1로 만드는지 — ✅ 라벨 매핑 자체는 맞음. 대신
   SWaT는 **윈도우가 normal/attack 경계를 걸치지 않게**, WADI는 **Time 컬럼 대신 Row로
   타임스탬프 재구성**해야 함(1b/1c 참고).
3. 물리 잔차는 전력계 데이터(FMCS)에만 적용(SWaT/WADI는 도메인 달라 미적용). PF는
   **부호 유지**(README.md 3.1 참고, `abs()` 금지).
4. PowerGraph는 시계열 파이프라인에 넣지 말 것(그래프 분류 전용). 로더는 `h5py` 필수,
   경로는 `powergraph_cascade_raw_dir()` 사용(1d 참고).
5. HAI는 보류. **원인 확정(2026-09-28)**: 원격 저장소(`icsdataset/hai`)의 LFS 예산
   초과("exceeded its LFS budget") — 로컬에서 해결 불가한 업스트림 제약. 재시도보다
   대체 호스트 확보가 우선.
6. FMCS 실데이터가 오기 전까지는 `scripts/winccoa/`(WinCC OA SVR_TEST/CLI_TEST +
   mock CSV, `SKILL_winccoa.md` 참고)로 1a 로더와 CLI_TEST 화면을 예행할 것.

## 산출물 정리
- `src/` 코드, `results/` 그래프·지표, `fmcs_wide.parquet`, 토폴로지 그래프 파일,
  발표용 지표 표. #1 발표의 "기초 모델 적용 결과"는 우선 SWaT/WADI 실측 + FMCS 프록시로 구성.
- `scripts/winccoa/`: WinCC OA 테스트 프로젝트용 CTRL 스크립트, mock CSV 생성기,
  패널 스펙(`SKILL_winccoa.md`와 연동, 2026-09-28 완료 — 아래 참고).
