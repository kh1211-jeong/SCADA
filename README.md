# 전력 수배전 계통 이상탐지 (FMCS Anomaly Detection)

> 이 문서는 프로젝트 개요이자 **Claude Code용 컨텍스트 브리핑**입니다.
> 작업을 시작하기 전에 이 파일과 `TASKS.md`를 먼저 읽으세요.
> (원하면 이 파일을 `CLAUDE.md`로 복사해 두면 Claude Code가 자동으로 불러옵니다.)

---

## 1. 프로젝트 개요

반도체 FAB 전력 수배전 계통(154kV 수전 ~ 220V 수배전)의 SCADA 트렌드 데이터로
**비지도 이상탐지 모델**을 만든다. 목표는 감시 방식을 다음과 같이 바꾸는 것이다.

- 현재: 임계값 초과 시 DI 알람이 다발한 **후에** 인지 → 사후 대응
- 목표: 정상 운전 패턴을 학습한 모델이 **미세한 이탈을 조기에** 포착하고,
  계통 위상 정보를 이용해 **이상의 위치와 원인을 설명**한다.
- 지향점: 시간기반 정비에서 **조건기반 정비(CBM)**로 전환.

산학/수업 과제이며, 산업AI 문제해결 프로젝트의 3단계 산출물(#1 데이터셋+기초모델,
#2 모델 개선, #3 경량화+현장적용)로 이어진다. **에이전트 활용 시 가산점**이 있어,
탐지 하류에 진단/설명 레이어로 LangGraph 기반 에이전트를 둔다.

## 2. 대상 계통 구조

강압 위계: **154kV 인입 → GIS(GCB) → BTR(154k→6.6k, OLTC) → 6.6kV MAIN VCB →
VCB K → VCB Q → Feeder → LTR(몰드 TR, 6.6k→220V) → 220V ACB → 부하**.
母線 간에는 DIS/TIE 결선이 있고, 뱅크 간에는 TIE(예: 3F11'2')로 연결된다.

태그(설비) 명명규칙 예시:
- `VCB_3F11A10_CURRENT` = 3F11 계통 / A 스테이지 / 10번 feeder / 전류
- `GCB-3A1A`, `GCB-3A1M`, `GCB-3A1B` = 154kV GIS의 A/M/B 구분 차단기
- `3F11A OLTC`, feeder `A1~A15 / C1~C15`, `LTR` 온도 3점, `ACB(220V)`, `UPS`

이 명명규칙에서 **룰베이스로 토폴로지(그래프)를 파싱**할 수 있다(EGMS에서 만든 빌더 재사용).
그래프: 노드 = 태그(설비+물리량), 엣지 = (같은 EQP 내부) + (계통 위상 상하류).

## 3. 데이터셋

| 역할 | 데이터셋 | 위치 | 라벨 | 형식 |
|---|---|---|---|---|
| **주 (적용/현장 입증)** | FMCS SCADA (계획 기반 합성) | `fmcs_synth/` (Oracle 추출 형식) | events.csv 구간 라벨 | 아래 3.1, 3.6 |
| **채점 (성능 실증)** | SWaT (Kaggle) | `swat/` | 있음(Normal/Attack) | CSV — 아래 3.2 주의 |
| **채점 (성능 실증)** | WADI (Kaggle) | `wadi/` | 있음(별도 파일) | CSV — 아래 3.3 주의 |
| **그래프/설명 검증** | PowerGraph | `fig_share_powergraph_22820534/dataset_cascades/dataset_cascades/{ieee24,ieee39,ieee118,uk}/{grid}/raw/*.mat` | 있음(DNS + 엣지 정답) | .mat v7.3(HDF5) — 아래 3.4 |
| 보류(외부 차단) | HAI (git+LFS) | `hai/` | (미다운로드) | LFS 실패 — 아래 3.5 |

전략: **공개 데이터(SWaT/WADI)로 방법의 정량 성능(F1, ROC-AUC)을 먼저 채점**하고,
검증된 파이프라인을 **라벨 없는 FMCS 실데이터에 이식**한다. PowerGraph는 그래프/설명
가능성 검증 전용(시계열 아님, 지도 분류).

FMCS 트렌드는 **계획 기반 합성 데이터**(`src/data/synth_fmcs.py` → `fmcs_synth/`)로 진행한다.
설비/연결은 EGMS `build_topology.py` 규칙(277노드/317엣지)을 그대로 쓰고, 출력은 아래 3.1의
Oracle 추출 형식과 같다. 생성 방법과 규칙은 3.6 참고. 산출물에는 "합성 데이터"라고 표기한다.

### 3.2 SWaT 주의사항 (2026-09-28 실측)

`merged.csv`(1,441,719행) = `normal.csv` 뒤에 `attack.csv`가 **한 덩어리로 이어붙은 것**
(라벨: Normal 1,387,098 / Attack 54,621행, 전부 파일 끝 한 블록, 3.79%). 경계에서
**타임스탬프가 역행**(`2016-01-02 14:59:59 → 2015-12-22 16:00:00`)한다. 이 배포본은
공식 SWaT(정상 495k/공격 449,919, 11.98%)과 다른 서브셋이므로 논문 수치와 직접
비교하지 말 것. **슬라이딩 윈도우가 정상/공격 경계를 걸치지 않도록** 분할해야 한다.

### 3.3 WADI 주의사항 (2026-09-28 실측)

- `WADI_attackdataLABLE.csv`의 `Time` 컬럼이 앞선 Excel 처리로 시(hour)가 소실됨
  (`00:00.0` = `mm:ss.f`만 남음). 타임스탬프는 `Time` 파싱 대신 **`Row`(1초 간격
  인덱스)로 재구성**할 것.
- `WADI_14days_new.csv`에 전부 NaN인 컬럼 4개 존재: `2_LS_001_AL`, `2_LS_002_AL`,
  `2_P_001_STATUS`, `2_P_002_STATUS` → 로더에서 drop.
- `WADI_14days_new.csv`는 784,570행/11일치 부분본(공식 14일치는 1,209,601행).
- 라벨 컬럼(끝 컬럼)은 `1`=정상/`-1`=공격, 공격 비율 5.77%. `skiprows=1` 필요(첫 줄은
  인덱스 숫자행).

### 3.4 PowerGraph 주의사항 (2026-09-28 실측)

- 실제 폴더가 표 경로보다 한 단계 더 중첩됨: PyG `InMemoryDataset(root=...)`는
  `dataset_cascades/dataset_cascades/{grid}/{grid}`(안쪽 폴더, 바깥 아님)를 가리켜야
  raw/*.mat을 찾는다. `src/config.py`의 `powergraph_cascade_raw_dir()` 사용.
- `.mat` 파일은 **MATLAB v7.3(HDF5)** — `scipy.io.loadmat`이 아니라 `h5py`로 읽어야
  함(`NotImplementedError: Please use HDF reader...`).
- 확인된 구조(ieee24, cascades): `blist.mat`의 `bList`(2,38) = 24모선/38선로 IEEE
  RTS-24 토폴로지 일치. `Bf.mat`/`Ef.mat`/`Ef_nc.mat`/`of_bi.mat`/`of_mc.mat`는
  시나리오 21,500개짜리 object-reference 배열(시나리오별로 역참조 필요),
  `of_reg.mat`의 `dns_MW`만 (1,21500) 직접 float 배열(회귀 타깃).
- `dataset_pf_opf/`에는 `texas`가 추가로 있음(cascades엔 없음); `texas`는 다른 4개
  그리드와 달리 이중 중첩이 아니라 `dataset_pf_opf/texas/raw`로 한 단계만 중첩.

### 3.5 HAI 주의사항 (2026-09-28 실측, 원인 확정)

`git lfs ls-files`로 30개 파일이 전부 LFS 추적 대상임을 확인했고, `git lfs fetch --all`
실행 결과 원격(`icsdataset/hai`)이 **"This repository exceeded its LFS budget"**를
반환한다 — 저장소 소유자 쪽 LFS 대역폭/스토리지 한도 초과로, 로컬에서 해결 불가한
외부 차단이다. 필요 시 대체 호스트(예: 별도 미러/릴리스)에서 재취득해야 한다.

### 3.1 주 데이터: FMCS 실 SCADA (핵심)

- 저장: Oracle `TH_CM_FMCS_TRND` (일자별 파티션 `TH_CM_FMCS_TRND_YYYYMMDD`)
- 설비 마스터: `TN_CM_EQP` (조인 키 `EQP_NO`, `EQP_NAME`, `USE_YN`)
- 핵심 컬럼: `EQP_NAME`(=태그), `PARAM_CODE`(예: PVLAST), `TRND_DATE`(분 단위),
  `TAG_COMPRS_VAL`(압축 문자열)
- **압축 포맷**: 한 행이 1분이고, 그 분의 3초 간격 샘플이
  `초offset:값;초offset:값;...` 로 들어 있다.
  예: `0:78.66;3:78.8;6:78.97;...;57:79.2` → 초 0,3,6,...,57 의 값.
  → 전처리에서 **펴서(unpack)** (timestamp, value) 시계열로 복원해야 한다.
- 수집 1초, 저장 3초 exception 압축(변화 없으면 미기록) → **불규칙 샘플링**.
- 라벨 거의 없음. DI 알람/차단기 STATUS 이력을 **약(弱)라벨**로만 사용.
- 물리 제약 존재: `P = √3 × V × I × cosφ`, 3상 전류 균형 → **물리 잔차 피처**로 활용.
  실측(계통도 화면값)으로 검증됨, 오차 0.15~3% 수준.
- **PF는 부호 있음(-99~99)**: 부호가 진상(leading)/지상(lagging)을 인코딩한다
  (`sample image/154k_2.png`의 `GCB-3A3M -99 PF` 등에서 확인). 물리 잔차 계산 시
  `abs(PF)`가 아니라 부호를 유지한 `PF/100`을 그대로 곱할 것.

추출 SQL 템플릿(한 계통의 여러 태그를 며칠치):
```sql
SELECT A.EQP_NAME, B.PARAM_CODE, B.TRND_DATE, B.TAG_COMPRS_VAL
FROM   TN_CM_EQP A, TH_CM_FMCS_TRND PARTITION (TH_CM_FMCS_TRND_20260924) B
WHERE  A.EQP_NO = B.EQP_NO
AND    A.USE_YN = 'Y'
AND    A.EQP_NAME LIKE 'VCB_3F11A%';   -- 계통/스테이지 단위로 확장
```

### 3.6 FMCS 합성 트렌드 생성기 (`src/data/synth_fmcs.py`)

```
python -m src.data.synth_fmcs --days 7 --seed 0            # -> fmcs_synth/ (하루 약 27MB gz, 약 45초)
python -m src.data.synth_fmcs --days 1 --write-truth        # 잡음 전 3초 참값 parquet 추가
# EGMS 경로: 기본 ./EGMS, 아니면 --egms-path 또는 EGMS_PATH 환경변수
```

출력:
- `raw/TH_CM_FMCS_TRND_YYYYMMDD.csv.gz`: `EQP_NAME,PARAM_CODE,TRND_DATE,TAG_COMPRS_VAL` (3.1과 동일)
- `TN_CM_EQP.csv`: EQP_NO/EQP_NAME/USE_YN + 노드·타입·물리량·단위
- `topology_nodes.csv`, `topology_edges.csv`: GDN prior용 EGMS 그래프 (정상 개폐 상태, 정격 포함)
- `events.csv`: 이벤트 구간 라벨 (kind = operational / anomaly / data_quality, 영향 태그 목록)
- `labels_1min.csv`: 분 단위 라벨, `meta.json`: 시드, 단위, 규칙

반영된 규칙:
- 연결: BUS→GCB→BTR→MAIN→K→Q→피더 VCB→LTR→ACB. TIE/XCB는 평상시 개방, DIS는 투입
- 태그: 8090 화면 규칙과 같다 (`gen_full_topology.py`). BTR은 TAP을 추가했고, LTR 온도는 C/W 2점이다
- 물리: 부하는 ACB에 걸린다. 상위 P/Q = 하위 합 + 변압기 손실(KCL). `P = √3·V·I·PF/100` (PF 부호 유지)
- 차단기 개방: 하위 구간이 가압되지 않아 V/I/P가 0. 이중화 피더는 TIE_AC, 비상 피더는 XCB, MAIN은 TIE_BA(ATS)로 절체
- BTR OLTC: 2차 6.6kV를 ±1% deadband, 60초 지연으로 제어. U계열 콘덴서는 5분 주기로 단계 투입
- 수집: 3초 격자, 매 분 offset 0은 기록. 이후는 deadband를 넘는 변화만 기록(exception 압축)
- 주입 이벤트: 피더 트립, 계획정비, MAIN 트립/ATS(operational) / CT 드리프트, 값 고착, 스파이크,
  PF 부호 반전, 전력계 오프셋, LTR 과열, OLTC 헌팅, 154kV 순간전압강하(anomaly) / 통신 두절(data_quality)

EGMS 규칙을 그대로 따른 결과, F계열 C라인 피더(C1~C3)도 A뱅크 Q(`VCB_..AQ`)에 붙는다.
그래서 B뱅크 BTR은 C4(주비상)만 부담한다. `build_topology.py`의 `'A' if line in 'AC'`
때문인데, 같은 파일 주석("C라인→모선2")과 다르다. 규칙이 확정되면 EGMS 쪽을 고치고 다시 생성한다.

## 4. 접근과 방법

1. **전처리**: FMCS 압축 해제 → 태그별 pivot(wide) → 고정 간격 리샘플/보간.
2. **피처**: 원시값 + 3상 불평형 + 물리 잔차(`P - √3·V·I·cosφ`) 등.
3. **그래프**: 명명규칙 룰베이스로 토폴로지 그래프 생성(노드=태그, 엣지=EQP내부+위상).
4. **기초 모델(#1)**: Isolation Forest, PCA 재구성, Autoencoder(정상만 학습).
5. **개선(#2)**: GDN(토폴로지 prior 주입) — 학습 그래프 대신 실제 위상 사용.
6. **경량화+에이전트(#3)**: pruning/양자화/증류 + LangGraph 진단 에이전트.
7. **평가**: 라벨 있는 공개 데이터는 F1/ROC-AUC 실측, FMCS는 합성 이상 주입 +
   물리 pseudo-label 프록시 + 정성 국소화로 보고.

## 5. 제출물 매핑

- **#1 데이터셋+기초모델**: SWaT/WADI 채점 + FMCS 특성 + IF/PCA/AE 기초 성능.
- **#2 모델 개선**: GDN(+토폴로지/물리) vs 기초 모델 향상률(공개 데이터 라벨로).
- **#3 경량화+현장적용**: 경량 모델 배포 + 진단 에이전트 데모(FMCS).

## 6. 기술 스택 / 폴더 구조

- Python 3.13, pandas/numpy, scikit-learn(IF/PCA/MLP), PyTorch + PyTorch Geometric(GDN),
  h5py(PowerGraph .mat v7.3), matplotlib. 에이전트는 LangGraph(+LangSmith).
  설치 상태와 버전은 `requirements.txt` 참고(2026-09-28 기준 전부 설치·검증됨).
```
PROJECT_ELEC/
├─ README.md                     # 이 문서
├─ TASKS.md                      # 작업 계획
├─ SKILL_winccoa.md              # WinCC OA 3.21 테스트 프로젝트(SVR_TEST/CLI_TEST) 절차
├─ requirements.txt
├─ fmcs_synth/                   # ★ FMCS 합성 트렌드 (src/data/synth_fmcs.py 출력, 3.6)
├─ swat/                         # merged.csv, normal.csv, attack.csv (Kaggle)
├─ wadi/                         # WADI_14days_new.csv, WADI_attackdataLABLE.csv (Kaggle)
├─ fig_share_powergraph_22820534/dataset_cascades/dataset_cascades/{ieee24,ieee39,ieee118,uk}
├─ hai/                          # 보류 — 원격 LFS 예산 초과, 로컬 해결 불가
├─ sample image/                 # SCADA 화면 캡처(참고, 명명규칙/물리식 검증 출처)
├─ src/                          # 코드
│  ├─ config.py                  # 데이터 경로 상수(PowerGraph 실제 중첩 경로 포함)
│  ├─ topology/equipment_catalog.py  # 룰베이스 설비/태그 카탈로그(신뢰도 태깅)
│  ├─ data/, models/, agent/     # Phase 1~5 (TASKS.md)
└─ scripts/winccoa/              # SVR_TEST/CLI_TEST용 CTRL 스크립트 + mock CSV 생성기
```

## 7. 원칙 / 제약

- 우선순위: **Feasibility > Explainability > Maintainability > OT Safety > AI Novelty**.
- **OT 안전**: 이 프로젝트는 감시/진단만. 활선 계통을 ML이 제어하지 않는다.
- **라벨 부재**가 최대 제약. 성능은 공개 데이터로 채점, FMCS는 프록시로 보고(숨기지 말 것).
- **기밀**: FMCS 실데이터/태그명은 사내 자산. 외부 공유(발표/깃 공개) 시 정규화/마스킹.
- 에이전트는 "가산점용 장식"이 아니라 **설명가능성을 제공하는 진단 레이어**로만 둔다.
