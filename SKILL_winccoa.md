# SKILL: WinCC OA 3.21 FMCS 테스트 프로젝트 제작 (CLI_TEST / SVR_TEST)

> 목적: WinCC OA 3.21에서 **CLI_TEST**(클라이언트/UI)와 **SVR_TEST**(서버/데이터) 두
> 프로젝트를 만들고, 지금까지 정리된 FMCS 전력계통 레퍼런스(계통 위계, 태그 명명규칙,
> 화면 구성)를 그대로 재현한다. 트렌드 CSV는 아직 추출 전이므로 **아래 설비 목록 기준으로
> 가상(mock) CSV를 생성**하는 절차까지 포함한다.
> 이 문서는 사람이 읽고 Claude Code/CTRL 스크립트가 실행하도록 작성한다.

> **2026-09-28 갱신**: 4장 설비 표는 `sample image/`의 실제 SCADA 화면 5장
> (154k_1/2.png, 6.6_1/2/3.png)을 기준으로 재확정했고, 룰베이스 생성기
> `src/topology/equipment_catalog.py`로 코드화했다(신뢰도 `confirmed`/`inferred`
> 태그 포함 — 어떤 설비가 화면에서 직접 읽었는지, 어떤 게 패턴으로 추정했는지 구분됨).
> 5~6장의 CTRL 스크립트/mock CSV 생성기도 `scripts/winccoa/`에 실제로 구현·검증
> 완료했다. 이 문서의 표는 이제 **참고용 요약**이고, 실제 태그 목록의 단일 진실 공급원은
> 카탈로그 모듈이다.

---

## 0. 전제 / 환경

- WinCC OA **3.21**. 프로젝트 2개를 분리 생성한다.
  - **SVR_TEST**: 서버 역할. Data/Event Manager, 태그(DPT/DP) 생성, 값 주입(가상 CSV 재생),
    아카이브/트렌드 저장 담당.
  - **CLI_TEST**: 클라이언트 역할. SVR_TEST에 **distributed(-distNr)로 연결**하여 화면(패널),
    트렌드 조회, 알람 UI 담당. 로컬 DP는 최소화.
- 문자셋: 태그명은 ASCII 대문자/숫자/`_`만 사용(한글 금지). 화면 라벨은 한글 가능.
- 단위/규칙은 아래 표를 **단일 원천**으로 삼는다. 표에 없는 건 만들지 않는다.

## 1. 프로젝트 생성 순서

1. **SVR_TEST 먼저 생성** → DPT/DP/값 주입까지 끝낸 뒤
2. **CLI_TEST 생성** → SVR_TEST에 분산 연결 → 화면 제작.

프로젝트 생성(예시, 실제 경로/버전 확인 후 실행):
```
# WinCC OA Project Administrator(GUI)로 생성하거나 CLI로:
WCCILpmon -config <config> ...        # 실제 3.21 설치 경로의 도구 사용
# config 파일에 distributed 설정:
#   SVR_TEST/config/config :  distributed = 1 ,  distComponent 설정
#   CLI_TEST/config/config :  distributed = 1 ,  [dist] 에 SVR_TEST 노드/ distNr 등록
```
> 분산 연결의 정확한 옵션은 3.21 도움말의 Distributed Systems 항목을 따른다.
> 핵심: **SVR_TEST가 DP의 소유자**, CLI_TEST는 원격 참조만 한다.

## 2. 계통 위계 (레퍼런스)

강압 위계: **154kV 인입 → GIS(GCB) → BTR(154k→6.6k, OLTC) → 6.6kV MAIN VCB →
VCB K → VCB Q → Feeder → LTR(몰드 TR, 6.6k→220V) → 220V ACB → 부하**.
母線 간 DIS/TIE, 뱅크 간 TIE(예: `3F11'2'`).

## 3. 태그(설비) 명명규칙 — **가장 중요**

### 3.1 기본 패턴
```
<종별>_<계통><스테이지><인덱스>_<물리량>
```
- 예: 설비 `VCB_3F11A` → 태그 `VCB_3F11A_CURRENT`, `VCB_3F11A_VOLTAGE`, ...
- 설비 하나(EQP)에 **여러 물리량 태그**가 붙는다(설비=DP, 물리량=DPE 또는 개별 DP).
- 154kV GIS 차단기는 하이픈 표기 사용: `GCB-3A1A`(레퍼런스 화면 표기 그대로).
  → DP명 규칙 충돌을 피하려면 **DP명은 `GCB_3A1A`(언더스코어)로 만들고, 화면 라벨만
  `GCB-3A1A`로 표시**한다.

### 3.2 종별(설비 Prefix)
| Prefix | 설비 | 전압 레벨 |
|---|---|---|
| GCB | Gas Circuit Breaker (GIS) | 154kV |
| BTR | Bank TR (154k→6.6k, OLTC) | 154/6.6kV |
| VCB | Vacuum Circuit Breaker (MAIN/K/Q/Feeder) | 6.6kV |
| LTR | 몰드 TR (6.6k→220V) | 6.6k/220V |
| ACB | Air Circuit Breaker | 220V |
| TIE | 母線/뱅크 연계 차단기 | 해당 레벨 |
| DIS | 단로기 | 해당 레벨 |
| ECB | Feeder 분기(A/C, B/D) 간 연계 차단기 | 220V 부근 |

> ECB는 원 설계엔 없었으나 `6.6_3.png`에서 `ECB-3F11AC(ATO)`, `ECB-3F11BC`로
> 실측 확인되어 추가.

### 3.3 물리량(Suffix) — 물리량별 태그 접미사
| Suffix | 의미 | 단위 | 적용 설비(예) |
|---|---|---|---|
| CURRENT | 전류 | A | GCB/VCB/ACB/Feeder |
| VOLTAGE | 전압 | kV 또는 V | GCB/VCB/ACB |
| POWER | 유효전력 | kW/MW | BTR/VCB/Feeder |
| REACTIVE | 무효전력 | kVAR | Feeder/ACB |
| PF | 역률 | % | 전 계측 지점 (부호 있음, -99~99: 진상/지상 부호. `abs()` 취하지 말 것) |
| STATUS | 차단기 개폐(DI) | 0/1 | GCB/VCB/ACB/TIE/DIS |
| TAP | OLTC 탭 | 단 | BTR |
| TEMP | 온도 | ℃ | BTR/LTR |
| LOAD | 부하율 | % | BTR/LTR |

> 규칙: 설비별로 **적용 가능한 물리량만** 생성한다(예: DIS는 STATUS만, BTR은
> POWER/VOLTAGE/CURRENT/PF/TAP/TEMP/LOAD).

## 4. 계통 대상(설비) 목록 — **단일 진실 공급원: `src/topology/equipment_catalog.py`**

`sample image/`의 실제 SCADA 화면 5장 기준으로 재확정한 목록(2026-09-28)이다.
전체 태그(1,309개)는 `python -m src.topology.equipment_catalog` 또는
`scripts/winccoa/gen_mock_csv.py` 실행 시 생성되는 `tag_list.csv`에서 확인한다.
각 항목은 `confidence`(`confirmed`=화면에서 직접 판독, `inferred`=패턴으로 추정)와
`source`(어느 캡처에서 확인했는지)를 갖는다 — 5장의 CTRL 스크립트로 DP를 만들기 전에
`confirmed`만 먼저 생성하고 싶다면 `tag_list.csv`를 `confidence` 컬럼으로 필터링하면 된다.

### 4.1 154kV GIS (GCB) — 물리량: CURRENT, VOLTAGE, POWER, PF, STATUS
버스 그룹별 확인된 스테이지(A/M/B)가 다르다 — **균일하게 A/M/B 3종이 아니다**:

| 버스그룹 | 확인된 스테이지 | 비고 |
|---|---|---|
| 3A1, 3A2, 3A5 | A, M, B | |
| 3A3, 3A4 | A, M | B 미관측(3A4는 T/L 인입 뱅크) |
| 3B1, 3B3 | M, B | A는 크롭 밖, 미확인 |
| 3B2, 3B5 | A, M, B | |
| 3B4 | (전체 미관측) | 생성하지 않음 — 존재 여부 TN_CM_EQP로 확인 필요 |

母線 연계(TIE): `TIE-3ABB1`, `TIE-3ABA1`(154kV, A버스~B버스 간).
"EMG T/L" 계열(P3-P2/P3-V2/고덕2-삼성P3#1 등)은 상위 유틸리티 연계 플래그로
**태그 생성 대상 아님**(EQP_NAME 규칙 밖).

### 4.2 BTR (뱅크 변압기) — 물리량: POWER, VOLTAGE, CURRENT, PF, TAP, TEMP, LOAD, STATUS
`3F11A/B, 3F12A/B, 3F13A/B, 3F14A/B` **8뱅크 전부 확인됨**(154kV/154k_2.png 하단
스트립 + 6.6_2/6.6_3.png의 개별 OLTC 박스).

### 4.3 6.6kV MAIN VCB — 물리량: CURRENT, VOLTAGE, POWER, PF, STATUS
BTR 뱅크 1:1 대응. `3F11A/B`, `3F12A/B`는 화면에서 직접 확인, `3F13A/B`, `3F14A/B`는
BTR은 확인되나 6.6kV 측 자체 화면은 못 찍어 **추정**(`inferred`).

### 4.4 뱅크 내부 연계 (DIS/TIE)
| 설비(DP) | 화면 라벨 | 비고 |
|---|---|---|
| DIS_3F11AB | DIS 3F11AB | |
| TIE_3F11BA | TIE 3F11BA | |
| TIE_3F112 | TIE 3F11'2' | 뱅크 간(3F11B↔3F12A), **화면 실제 표기는 "3F112"** |
| DIS_3F12AB | DIS 3F12AB | |
| TIE_3F12BA | TIE 3F12BA | |
| DIS_3F11AD | DIS 3F11AD | 독립 단로기(개방 상태로 관측) |

### 4.5 K/Q 단 VCB — 물리량: CURRENT, POWER, PF, STATUS
**뱅크마다 K단 문자 범위가 다르다**(전 계통 순차 채번, 뱅크별 리셋 아님):

| 뱅크 | K단 문자 | Q단 문자 | 비고 |
|---|---|---|---|
| 3F11 | A, B, C, D | A, C | Q단 B/D는 미관측 |
| 3F12 | C, D, E, F | (미확인) | K단은 확인, Q단 패턴 추정만 |

K단 버스 노드(토폴로지 전용, 값 태그 없음): `3US1AK`, `3US1CK`.

### 4.6 Feeder — 물리량: CURRENT, POWER, PF, STATUS
인덱스 **1~15 전 구간 확인됨**(A15/C15까지 화면에서 직접 판독, 더 이상 샘플 축약 아님).

| 뱅크 | 분기 문자 | 여유(spare) | 신뢰도 |
|---|---|---|---|
| 3F11 | A, C | AC, CC | confirmed (6.6_1/2/3.png) |
| 3F12 | B, D | (없음) | inferred — 화면에 못 담음, SKILL 관례 유지 |

220V 레벨의 분기 간 연계는 `ECB_3F11AC`, `ECB_3F11BC`(3.2절 ECB 참고).

### 4.7 LTR (몰드 TR) — 물리량: POWER, VOLTAGE, CURRENT, PF, TEMP, LOAD
Feeder에 1:1 대응. **TEMP는 2점**(`_TEMP_C`, `_TEMP_W`) — 원래 "3점"으로 가정했던 것을
`6.6_3.png`에서 확인된 실제 표기(℃(C)/℃(W) 두 박스)로 정정.

### 4.8 220V ACB — 물리량: CURRENT, VOLTAGE, POWER, PF, STATUS
Feeder에 1:1 대응. 값 박스(kW/V/A)는 화면에서 보이나 "ACB_" 텍스트 라벨 자체는 각도상
판독 못 함 → **명명 규칙은 유지하되 신뢰도 `inferred`**로 표시.

> **제외(모니터링 대상 아님, 태그 생성하지 말 것)**: 분전반, Q하위 고압기동반/MCC,
> (콘덴서 AC/CC는 필요 시만), 상위 유틸리티 EMG T/L 연계 플래그. 레퍼런스 규칙 유지.

## 5. SVR_TEST — DPT/DP/태그 생성 (CTRL 스크립트)

### 5.1 DPT(자료형) 정의
설비 종별마다 DPT를 만들고, 3.3의 물리량을 DPE로 둔다(설비=1 DP, 물리량=DPE).
```ctrl
// 예: VCB 자료형
main() {
  dyn_string dpes  = makeDynString("CURRENT","VOLTAGE","POWER","PF","STATUS");
  dyn_int    types = makeDynInt(DPEL_FLOAT,DPEL_FLOAT,DPEL_FLOAT,DPEL_FLOAT,DPEL_BOOL);
  // dpTypeCreate 로 "VCB_TYPE" 생성 (구조: 루트 아래 각 DPE)
  // GCB_TYPE/BTR_TYPE/LTR_TYPE/ACB_TYPE/TIE_TYPE/DIS_TYPE 동일 방식, 물리량만 표에 맞게
}
```
> 대안(더 단순): 설비+물리량을 **개별 DP**로 만들고 이름을 `VCB_3F11A_CURRENT`처럼 붙인다.
> 이 경우 DPT는 물리량 타입별(FLOAT/BOOL)만 있으면 된다. **레퍼런스가 `EQP_NAME=태그` 
> (예: VCB_3F11A10_CURRENT)이므로, 개별 DP 방식이 실 데이터와 1:1로 맞아 권장**된다.

### 5.2 표 → 태그 자동 생성 — **구현 완료**

의사코드 대신 실제 CTRL 스크립트 `scripts/winccoa/svr_test_create_dps.ctl`을 작성했다.
`tag_list.csv`(4장의 카탈로그를 `gen_mock_csv.py`가 export, 또는
`python -m src.topology.equipment_catalog`로 직접 확인)를 읽어 `dpExists` 체크 후
`dpCreate`, 생성 목록을 `created_tags.txt`로 출력한다. 개별 DP 방식(위 "대안") 채택.

```
WCCOActrl -proj SVR_TEST scripts/winccoa/svr_test_create_dps.ctl tag_list.csv
```

- 완료 기준: 4장 모든 설비에 대해 태그가 `dpExists`로 확인됨. 생성 목록을 `created_tags.txt`로 출력.
  (CTRL 스크립트는 작성·정적 검토 완료. 실제 SVR_TEST 프로젝트가 아직 없어 WinCC OA
  런타임에서의 실행 자체는 미검증 — 프로젝트 생성 후 1회 실행해 확인할 것.)

## 6. 가상(mock) 트렌드 CSV 생성 — **CSV 미추출 상태 대응**

실 FMCS 트렌드가 아직 없으므로, **위에서 만든 설비명 기준으로 가상 CSV를 생성**한다.
용도: SVR_TEST 값 주입 + 화면/트렌드 동작 확인 + 이상탐지 파이프라인 예행.

### 6.1 포맷 (실 데이터 구조를 모사)
실 데이터의 압축 포맷(`초offset:값;`)을 흉내 낸 **원본형**과, 파이프라인용 **펴진형** 둘 다 생성.
- 펴진형(권장, 분석용): `timestamp, tag, value`  또는 wide(`timestamp, VCB_3F11A_CURRENT, ...`)
- 원본형(WinCC/실data 모사): `EQP_NAME, PARAM_CODE, TRND_DATE, TAG_COMPRS_VAL`
  여기서 `TAG_COMPRS_VAL = "0:v0;3:v3;6:v6;...;57:v57"` (1분당 3초 간격 20샘플)

### 6.2 값 생성 규칙(현실감)
- CURRENT/POWER: 완만한 부하 곡선 + 소량 노이즈, 물리 관계 유지
  `POWER ≈ √3 × VOLTAGE × CURRENT × PF`(단위 맞춰 스케일).
- VOLTAGE: 정격 근처(6.6kV/220V), 부하 오를 때 소폭 강하.
- PF: 95~99 근처. TEMP: 40~55℃. TAP: 8~9. STATUS: 대부분 1(정상), 가끔 0.
- (선택) 이상 주입 옵션: 특정 태그/구간에 급등·상관붕괴·물리위반 주입 + 라벨 컬럼.

### 6.3 생성 스크립트 — **구현·검증 완료**

`scripts/winccoa/gen_mock_csv.py` (실행: `python scripts/winccoa/gen_mock_csv.py --minutes 120 --seed 0`).
카탈로그의 1,309개 태그에 대해 설비별로 CURRENT/VOLTAGE/PF를 먼저 생성한 뒤
`POWER = √3·V·I·(PF/100)`으로 역산해 물리관계를 강제하고(부호 있는 PF 유지),
`mock_wide.csv` / `mock_fmcs_raw.csv` / `tag_list.csv` 세 파일을 낸다.

**검증됨(2026-09-28)**:
- 물리 잔차(POWER vs √3·V·I·PF/100) 상대오차 최대 3.5% 수준(의도된 노이즈 범위).
- `mock_fmcs_raw.csv`를 TASKS.md의 `unpack_row`(날짜 포맷 명시 버전)로 되풀어 보면
  `mock_wide.csv`와 정확히 일치 — 압축 왕복(round-trip) 확인.
- `EQP_NAME`은 (버그 수정 후) 전체 태그명(`VCB_3F11A1_CURRENT`)을 담는다 — README.md
  3.1의 실측과 동일하게 맞춤.
- 용량 주의: 10분 분량이 이미 ~7.6MB(1,309태그 × 20샘플/분). 기본값 120분이면
  ~90MB — 저장소에 커밋하지 말고 필요할 때마다 재생성할 것.
- 완료 기준: `mock_wide.csv`, `mock_fmcs_raw.csv` 생성, 태그 수 = 카탈로그 태그 수(1,309)와 일치. **확인됨.**
- **주의(문서에 명시)**: 이 CSV는 **가상 데이터**다. 실 FMCS 추출본으로 반드시 교체.
  발표/평가에 쓸 땐 "가상 데이터(실데이터 추출 전 예행)"라고 표기.

### 6.4 SVR_TEST에 주입 — **CTRL 스크립트 작성 완료**

`scripts/winccoa/svr_test_replay_mock.ctl`이 `mock_fmcs_raw.csv`를 읽어 압축 문자열을
풀고 `dpSet`으로 재생한다(배속 인자로 재생 속도 조절). `TRND_DATE` 파싱은 날짜 필드를
직접 split — CTRL엔 dateutil류 자동 추정이 없어 이 버그 자체는 발생하지 않지만, Python
쪽에서 재사용할 경우 반드시 명시적 포맷을 쓸 것(TASKS.md 1a 참고).

```
WCCOActrl -proj SVR_TEST scripts/winccoa/svr_test_replay_mock.ctl mock_fmcs_raw.csv 20
```

- 완료 기준: CLI_TEST 화면에서 값이 갱신되고 트렌드 곡선이 그려짐. (CTRL 스크립트
  작성·정적 검토 완료. SVR_TEST 프로젝트가 아직 없어 실제 런타임 실행은 미검증.)

## 7. CLI_TEST — 화면(패널) 제작 (레퍼런스 기준)

레퍼런스 SCADA 화면(단선결선도 스타일)을 모사. **직각/직선 배선만** 사용(사선/곡선 금지),
전력 심볼(변압기=원 2개 Y/Δ, 차단기=개폐기 기호) 사용.

`.pnl`은 WinCC OA GEDI 전용 바이너리라 텍스트로 직접 만들 수 없다 — 대신 위젯
배치·DP 바인딩을 전부 명세한 `scripts/winccoa/panels/panel_specs.md`를 작성해 두었다
(패널별 구획, 어떤 태그를 어디에 바인딩할지, 빌드 순서 포함). GEDI에서 그 문서를 보고
그리면 된다.

### 7.1 화면 목록
| 패널 | 내용 | 스펙 |
|---|---|---|
| `overview.pnl` | 154kV GIS + 6.6kV 뱅크 + feeder 개요(레퍼런스 이미지 3/4/6 구도) | panel_specs.md §4 |
| `bank_3F11.pnl` | 3F11 계통 상세(MAIN/K/Q/Feeder/LTR/ACB, TIE/DIS) | panel_specs.md §2 |
| `bank_3F12.pnl` | 3F12 계통 상세 — K단 문자가 3F11과 다름(4.5절), 레이아웃 미검증 | panel_specs.md §3 |
| `gis_154k.pnl` | 154kV GIS(버스그룹별 확인된 스테이지만, 4.1절) | panel_specs.md §1 |
| `trend.pnl` | 태그 선택 트렌드 조회 | panel_specs.md §5 |
| `alarm.pnl` | STATUS/임계 알람 리스트 | panel_specs.md §6 |

### 7.2 표준 계측 블록(레퍼런스의 kW/V/A/PF 박스)
각 설비 옆에 값 박스: `POWER(kW) / VOLTAGE(V) / CURRENT(A) / PF`. STATUS는 색(정상/개방).
- 위젯은 DP에 바인딩(`dpConnect`)하여 실시간 갱신.

### 7.3 배선/심볼 규칙
- 母線=굵은 수평선, 분기=수직/수평 직각. 차단기=개폐기 심볼, 변압기=원 2개(Y/Δ).
- 라벨은 화면표기명(GCB-3A1A 등), DP 바인딩은 언더스코어명(GCB_3A1A).

## 8. 작업 순서 요약 (체크리스트)

**코드/문서 산출물 (2026-09-28 완료):**
- [x] 4장 목록을 코드화 → `src/topology/equipment_catalog.py` (243 설비군, 1,309 태그,
      신뢰도 태깅).
- [x] `scripts/winccoa/gen_mock_csv.py` → 가상 CSV 3형식(`mock_wide.csv`,
      `mock_fmcs_raw.csv`, `tag_list.csv`) 생성·물리검증·압축왕복 검증 완료.
- [x] `scripts/winccoa/svr_test_create_dps.ctl` — DP 생성 CTRL 스크립트 작성.
- [x] `scripts/winccoa/svr_test_replay_mock.ctl` — mock 재생 CTRL 스크립트 작성.
- [x] `scripts/winccoa/panels/panel_specs.md` — 5+1 패널 배치/바인딩 명세 작성.

**WinCC OA 런타임 작업 (미착수 — GEDI/Project Administrator GUI 필요, 아직 실행 안 함):**
1. [ ] SVR_TEST 생성(distributed=1, DP 소유자).
2. [ ] SVR_TEST 안에서 `svr_test_create_dps.ctl tag_list.csv` 실행 → `created_tags.txt` 확인.
3. [ ] `python scripts/winccoa/gen_mock_csv.py --minutes 120` 으로 가상 CSV 생성(로컬, 실행만 하면 됨).
4. [ ] SVR_TEST에서 `svr_test_replay_mock.ctl mock_fmcs_raw.csv` 실행 → 값 갱신 확인.
5. [ ] CLI_TEST 생성 → SVR_TEST 분산 연결.
6. [ ] `panel_specs.md` 순서대로 gis_154k → bank_3F11 → trend/alarm → overview → bank_3F12 제작.
7. [ ] 트렌드/알람 동작 확인.
8. [x] (문서화) 가상 데이터임을 명시 완료(README.md, 본 문서, 스크립트 docstring 전부).
      실 FMCS 추출본 도착 시 `fmcs/`를 채우고 TASKS.md Phase 1a로 전환.

## 9. 원칙 / 주의

- 태그명 ASCII 대문자/숫자/`_`만. 화면 라벨만 한글/하이픈 허용.
- 표에 없는 설비/물리량은 만들지 않는다(일관성 유지).
- **가상 CSV는 예행용**. 실데이터 교체 전까지 발표/평가에 "가상"이라고 반드시 표기.
- 제외 대상(분전반/고압기동반/MCC) 태그 생성 금지.
- 실 태그명/계통 정보는 사내 자산 → 외부 공유 시 마스킹.
