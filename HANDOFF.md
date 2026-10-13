# 인수인계: 이전 Windows PC 작업 내역 (2026-09-27 ~ 10-03)

이 PC(Windows, C: 223GB 단일 디스크)에서는 더 이상 작업하지 않는다. 디스크 용량 문제로 M2 환경으로 옮긴다.
아래 내용은 이 PC의 Claude Code 세션 기록과 실제 파일을 근거로 정리했다.

## 0. 가장 중요한 것: 새 환경의 문서/코드가 구버전일 수 있다

새 환경 Claude는 "Phase 0~3 전부 미착수이고 src/와 results/가 없다"고 봤다. 반면 이 PC에서는 아래 작업이 끝나 있었다.
**아래 파일들을 이 PC에서 그대로 복사해 가야 한다.** 그렇지 않으면 검증해 둔 내용이 사라진다.

- `README.md`, `TASKS.md`, `SKILL_winccoa.md`: 2026-09-28에 실측 검증 결과를 반영해 갱신함
- `requirements.txt`: 버전 고정(torch≥2.14, torch_geometric≥2.8, langgraph≥1.2 등)
- `src/`: 패키지 골격 + `config.py` + `topology/equipment_catalog.py` + **`data/synth_fmcs.py`(FMCS 합성 트렌드 생성기)**
- `EGMS/`: 생성기가 `build_topology.py`를 import한다. 없으면 `git clone https://github.com/kh1211-jeong/EGMS.git`로 받는다
- `scripts/winccoa/`: WinCC OA 리허설과 웹 SCADA 화면 생성 스크립트

## 1. 이 PC에서 실제로 한 작업

### 완료
- **Phase 0 완료**
  - `src/{data,models,agent,topology}` 골격을 만들었다.
  - `src/config.py`에 데이터셋 경로 상수를 정의했다. 단, 경로는 **옛 Kaggle판 기준**이라 새 데이터 구조에 맞춰 고쳐야 한다(아래 3절 참고).
- **FMCS 포맷 가정 2개 확인 완료** (TASKS.md 1a, `sample image/trend data sample.png` 실물 쿼리 기준)
  1. `TAG_COMPRS_VAL`의 offset 단위는 **초(0~57)**이고 **한 행이 1분**이다. 형식은 `0:78.66;3:78.8;...` 같은 꼴이다.
  2. 물리량은 **`EQP_NAME` 접미사**로 구분한다(예: `VCB_3F11A10_CURRENT`). `PARAM_CODE`는 전부 `PVLAST`인 상수라서 구분자로 쓸 수 없다.
  3. ⚠️ **버그 주의**: `TRND_DATE`(`26/09/24 00:00:00` 형식)는 반드시 `pd.to_datetime(x, format='%y/%m/%d %H:%M:%S')`처럼 형식을 명시해 파싱해야 한다. 형식을 빼면 날짜와 연도가 틀어진다.
- **물리 잔차** `P = √3·V·I·(PF/100)`: PF는 **부호가 있는 값**(-99~99, 진상/지상)이므로 `abs()`를 쓰면 안 된다.
- **설비 카탈로그**: `src/topology/equipment_catalog.py`에 243개 그룹, 1309개 태그를 정리했다. 그룹마다 근거 스크린샷과 confidence를 기록해 두었다.
- **WinCC OA 리허설과 웹 SCADA 화면** (프로젝트 본류 밖의 부가 작업)
  - `C:\WinCC_OA_Proj\SVR_TEST`(서버)와 `CLI_TEST`(클라이언트)를 분산 연결로 구성했다.
  - 전체 설비 계통도는 Node.js 웹 화면(포트 8090)으로 구현했다. 연결 관계는 EGMS 레포(github.com/kh1211-jeong/EGMS)의 토폴로지를 참고했다.
  - 차단기를 열면 그 아래 구간이 BFS로 무전압 처리된다. 색 규칙은 **활선=빨강, 무전압=초록**이다.
  - 소스는 `scripts/winccoa/web/`에 있다. Windows와 WinCC OA 3.21 전용이라 M2에서는 실행할 수 없다.

- **FMCS 트렌드 = 계획 기반 합성 데이터로 진행** (`src/data/synth_fmcs.py`, README 3.6)
  - 설비/연결: EGMS `build_topology.gen_grid()`를 그대로 import한다(277노드/317엣지, 재구현 안 함). 태그 1027개
  - 형식: Oracle 추출과 같다. `raw/TH_CM_FMCS_TRND_YYYYMMDD.csv.gz`(EQP_NAME, PARAM_CODE, TRND_DATE, TAG_COMPRS_VAL) + `TN_CM_EQP.csv`
  - 물리: KCL, `P=√3·V·I·PF/100`(부호 유지), 차단기 개방 시 하위 0, TIE/XCB/ATS 절체, OLTC, 열모델
  - 라벨: `events.csv`(operational / anomaly / data_quality 구간과 영향 태그), `labels_1min.csv`
  - 실행: `python -m src.data.synth_fmcs --days 7 --seed 0` → `fmcs_synth/` (하루 약 45초, 27MB)
  - 2026-10-13 검증: 정상 구간 물리 잔차 2e-7, 트립/절체/ATS/전압강하/드리프트/통신 두절이 의도대로 나오는 것 확인
  - 확인 필요: EGMS 규칙상 C라인 피더도 A뱅크 Q에 붙어서 B뱅크 BTR은 C4만 부담한다(README 3.6 끝). 사용자 확인 후 EGMS를 수정하고 다시 생성할 것

### 미착수 (새 환경에서 시작할 것)
- Phase 1 로더(`src/data/fmcs.py`, `swat.py`, `wadi.py`, `powergraph.py`)는 **하나도 작성하지 않았다.** FMCS 로더는 합성 출력으로 먼저 개발한다.
- IF/PCA/AE 결과는 아직 **없다.** `results/`는 비어 있다.
- `raw.7z`가 무엇인지는 이 PC 기록에 없다.

## 2. 데이터셋 이력 (이 PC에서 겪은 문제)

| 데이터 | 이 PC에서의 결과 | 새 환경에서 할 일 |
|---|---|---|
| WaDi | 정상. A1(2017) `WADI_14days.csv` + `WADI_attackdata.csv`, A2(2019)도 있음 | 그대로 사용 |
| EPIC | 1차 zip은 전부 Drive 다운로드 실패 스텁이었다. 2차 zip(20GB)은 무결성 검사를 통과했지만 공간이 부족해 압축을 풀지 못했다. 안에 `Oct 2021.zip`(9.1GB) 같은 중첩 zip이 있다 | 압축 해제에 30GB 이상 필요 |
| SWaT | 1차 zip은 1836개 파일 중 1478개가 `_Error.txt` 스텁이었고 물리 센서 라벨 데이터가 전부 빠져 있었다. 2차 zip(21GB)은 받는 도중 디스크가 꽉 차서 **잘렸다**(central directory 없음) | 새 환경의 SWaT.zip을 `unzip -t`로 검사. 실패하면 재다운로드 |
| HAI | git LFS 예산 초과로 받을 수 없음. 폴더는 삭제함 | 사용 안 함 |
| PowerGraph | 정상. 경로가 이중 중첩됨(`dataset_cascades/dataset_cascades/ieee24/ieee24/raw`) | `config.py`의 헬퍼 함수 사용 |

**zip 검사 팁**: Google Drive에서 큰 폴더를 통째로 zip으로 받으면, 받지 못한 파일 자리에 `파일명_Error.txt` 스텁이 들어가고 `___All_Errors.txt`가 같이 생긴다.
압축을 푼 뒤에는 반드시 `*_Error.txt`가 몇 개인지 세어서 데이터가 실제로 있는지 확인할 것.

옛 Kaggle판 데이터의 주의사항(`config.py` 주석에 있음)은 새 원본 데이터에서 그대로 적용되지 않을 수 있으니 다시 확인할 것.
- SWaT `merged.csv`: normal과 attack 경계에서 타임스탬프가 역행한다.
- WADI attack 파일: `Time` 열에서 시(hour)가 사라져 있다.

## 3. 새 환경 Claude의 질문에 대한 답

1. **2차 발표 범위 (AE 개선이냐, AE를 기준선으로 두고 GDN과 비교하냐)**: 이 PC 기록에는 결정한 내용이 없다. **사용자가 직접 답해야 한다.**
2. **다른 PC에서 한 작업**: 1절 참고. 정리하면 FMCS 포맷 가정 2개 확인, 설비 카탈로그, 경로 config, WinCC OA와 웹 SCADA까지 했다. 로더와 모델 결과는 없다.
3. **SWaT.zip**: 이 PC의 사본은 잘린 파일이었다. 새 환경의 파일은 복사가 끝난 뒤 `unzip -t`로 확인할 것.
4. **raw.7z가 FMCS 원본인가**: 이 PC 기록으로는 확인할 수 없다. 사용자에게 물어보거나 `7z l raw.7z`로 목록을 확인할 것.

권장 시작 순서:
1. `python -m src.data.synth_fmcs --days 7`로 FMCS 합성 데이터를 생성한다.
2. `src/data/fmcs.py` 로더(unpack → pivot → 3초/1분 리샘플)를 만든다.
3. AE를 학습한다. 라벨은 `events.csv`의 anomaly 구간으로 채점하고, operational 구간은 따로 보고한다.
4. 공개 데이터는 라벨이 있는 **WADI A2**부터 같은 파이프라인으로 돌린다. SWaT는 zip 검사를 통과한 뒤에 진행한다.
