# CLAUDE.md — 전력 수배전 이상탐지·진단 프로젝트

Claude Code가 이 저장소에서 작업할 때 가장 먼저 읽는 파일. 상태가 바뀌면 **"현재 상태"와 "다음 할 일"을 갱신해서 같이 커밋**한다.
자세한 배경: `README.md`(도메인·데이터 포맷), `TASKS.md`(원 작업 계획), `HANDOFF.md`(초기 인수인계), `demo/README.md`(데모 웹), **`GUIDE.md`(사내 리눅스 서버 설치·운영)**, **`docs/WINCCOA_VISION.md`(WinCC OA Vision 연동 기술 검토·기술 스택)**.

## 한 줄 요약
반도체 공장 154kV~220V 수배전 계통의 감시 데이터(WinCC OA 트렌드, 3초 exception 압축)로 비지도 이상탐지 →
계통 연결(토폴로지)을 이웃으로 고정한 **그래프 편차 신경망(GDN-prior)** → 경량화 → **진단 에이전트(goclaw + Gemini)** 가
원인 위치를 설명하는 **웹 데모**까지. 산업AI 과제 #1~#4 (보고서는 표지 없는 Word 2~3쪽, 한국어).

## 저장소 지도
| 경로 | 내용 |
|---|---|
| `src/data/synth_fmcs.py` | FMCS 합성 트렌드 생성기(EGMS 토폴로지 import). `Simulator.run_block(t0,n)` = 데모 실시간 스트림 |
| `src/data/fmcs.py` · `wadi.py` · `epic.py` | 로더·물리/KCL 잔차·운전 컨텍스트 마스크 |
| `src/models/ae.py` · `gdn.py` | 오토인코더 4종, GDN(학습/prior/hybrid/dyn) |
| `src/lite/features.py` | 학습·실시간 공용 피처 변환기(정규화 상수 저장) |
| `src/agent/` | (구) 오프라인 경보 저장소·stdio MCP. 현재 데모는 `demo/tools.py` 사용 |
| `scripts/run_*.py`, `analyze*.py` | 학습·채점. `run_light.py`(#4 경량화), `export_lite.py`(채점 + 데모 번들) |
| `scripts/build_report{2,3,4}.py`, `build_report_gdn.py`, `report_figs*.py` | 보고서 docx·그림 생성(수치는 results JSON에서 자동) |
| `demo/grid_rules.py` | **계통 운전 규칙 단일 원본**: 설비 역할·트립 가능·정전 판단·병렬 금지 인터록·과부하 보호 곡선·백업 용량·모의 한계. 엔진이 실제로 적용하고 에이전트는 `get_grid_rules`로 읽음. 전기 규칙은 여기만 고친다 |
| `demo/` | 웹 데모: `server.py`(:8765 웹, :8766 MCP), `engine.py`(시뮬레이터+모델+경보), `tools.py`(에이전트 도구 10종), `static/` |
| `agent/` | 진단 에이전트 설정 사본 + `install.sh`(새 PC에서 ~/agents 구성) + goclaw 패치 |
| `EGMS/` | 서브모듈(github.com/kh1211-jeong/EGMS) — `build_topology.py`가 설비·연결 규칙의 원본. **재구현 금지, import** |
| `results/` | 보고서 그림·수치 JSON·경량 모델(`fmcs_v2/lite/*.pt`, `bundle.json`). 오차 캐시 npz는 git 제외 |

## 새 환경에서 시작
```
git clone --recursive https://github.com/kh1211-jeong/SCADA && cd SCADA
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# 합성 데이터(학습·채점용, 1.2GB, 수십 분): 데모만 돌릴 거면 불필요
.venv/bin/python -m src.data.synth_fmcs --profile v2 --days 42 --seed 7 --start "2026-09-07 00:00:00" \
    --anomalies-per-day 1 --eval-days 12 --eval-per-type 3 --out-dir fmcs_synth_v2
zsh agent/install.sh            # 진단 에이전트(~/agents) 구성 → ~/agents/litellm/.env 에 GEMINI_API_KEY 입력
zsh demo/run.sh                 # goclaw + LiteLLM + 데모 서버 → http://127.0.0.1:8765
```

## 현재 상태 (2026-11-18)
- #1 데이터셋·기초모델, #2 개선계획, #3 성능분석 보고서·발표 완료 (루트의 docx/pptx).
  #3 결론: 운영 임계 탐지 정확도 FMCS 0.135 → 0.600(GDN-prior), 학습 그래프의 토폴로지 일치 3.5% = 무작위.
- #4 진행 중: "모델 고도화·경량화 계획 + 현장 적용/검증 계획"(2~3쪽) + "그래프 편차 신경망 기술 정리" 보고서.
  - **사용자 요구: 보고서에 약어 금지**(SCADA→설비 감시 시스템, CT→계기용 변류기, F1→탐지 정확도 등 모두 풀어 씀. 제품명·단위만 허용).
  - 경량화 결과(`results/fmcs_v2/lite/eval.json`): 교사 523KB·운영 F1 0.516 → 축소 0.629 → 축소+증류+16비트 저장 78KB·0.582·원인 설비 적중 91%(데모 탑재). 8비트 양자화는 이득 없음. 생성 순서 `run_light` → `export_lite` → `report_figs4` → `build_report4`·`build_report_gdn`.
- 데모 웹·진단 에이전트 동작 확인(차단기 트립 → 약 25초 후 위치·정전 범위 진단).

## 다음 할 일
1. #4 보고서 2종 완료(모델고도화경량화_현장적용계획 3쪽, 그래프편차신경망_기술정리 5쪽). 사용자 검토 의견 반영 대기.
2. 데모 개선 후보(사용자와 협의): 경보 확인·조치 흐름, 6계통 개요 화면, 트립 시 자동 절체 모의, 사건 순서 기록, 조작 권한, 모선을 굵은 막대로 그리는 단선도.
   - 완료(11-19): 병렬 금지 인터록, 백업 부하율 예측, 변압기 과부하 반한시 트립(`grid_rules.py`).
   - 완료(11-19): 검은 배경, 상단 "에이전트" 버튼 → 연결 정보·연결/해제·호출 경로(자동/goclaw/직접), 이상 점수 버튼 → 실시간 추이 팝업 + 에이전트 실시간 해설(`/api/score`, `/api/narrate`, 도구 없이 LiteLLM 직접 수 초).
4. **병렬(루프) 조류 계산 — 보류, 할 때 참고.** 계산 자체는 어렵지 않다(노드 수백 개, 고리는 연계 투입 때만 생김).
   어려운 건 **학습 데이터와의 일관성**: `synth_fmcs.Simulator`의 조류·전압 계산(방사상 트리 누적)이 학습 데이터 생성과 데모가 공유하는 원본이라,
   바꾸면 학습 때 본 적 없는 측정 분포가 나와 모델이 오경보를 낸다(재생성·재학습 필요). 권장 방식:
   (a) 데모 엔진에서 **고리가 생긴 순간에만** 별도 계산기를 쓴다 — 두 변압기 병렬이면 부하 분담 ∝ 1/%Z, 순환 전류 ≈ 탭 전압차/(Z1+Z2),
       단락 용량은 두 변압기 기여 합. 일반 고리는 6.6kV 구간 노드 어드미턴스 행렬로 직류 조류(선형) 근사.
   (b) 방사상일 때는 기존 계산 그대로(학습 분포 유지). (c) `grid_rules.py`의 limits 문구를 함께 갱신.
   예상 작업량: 1~2일(검증 포함). 인터록이 병렬을 막고 있어 실사용 영향은 작다.
3. **외부 공개(11-19, 임시)**: 맥북 + Cloudflare 빠른 터널(`cloudflared tunnel --url http://127.0.0.1:8765`, 주소 `*.trycloudflare.com`는 재시작마다 바뀜).
   로그인 `demo/auth.py`: 비밀번호 2종(보기 전용/운영자)은 `~/agents/demo-web/.env`(git 제외, 파일 없으면 로그인 꺼짐). 운영자 전용 POST: switch·inject·control·agent·narrate.
   Gemini 상한 `SCADA_LLM_PER_HOUR`(기본 120회/시간). MCP(:8766)·LiteLLM·goclaw는 127.0.0.1 전용이라 터널로 안 나감.
   상시 운영으로 옮길 때 후보는 아래.
   (개발·잔버그 정리 후) 외부 접속용 서버 배포 — 후보: 맥북+Cloudflare Tunnel / 클라우드 VM+Docker compose(권장). 로그인·조작 권한·Gemini 사용량 제한 필수, Gemini 키는 서버에만.

## 함정 (실제로 겪은 것)
- **TRND_DATE 파싱**은 `format='%y/%m/%d %H:%M:%S'` 명시(dateutil 오파싱). pandas 3 타임스탬프는 µs → int64 저장 시 ns 변환.
- WADI `2B_AIT_002_PV` 드리프트 센서 → `--drop-drift` 없으면 성능 붕괴. FMCS 검증 구간의 계획정비가 임계를 폭등시킴 → 평상 개폐 구성 시점만으로 임계.
- GDN(D≈1000) 추론은 MPS 메모리 부족 → 배치 128. 맥북 **덮개를 닫으면 학습이 멈춘다**(caffeinate로 못 막음).
- 데모 시뮬레이터는 학습 데이터와 **같은 시나리오**여야 모델이 맞는다: seed 7, 42일, v2, anomalies_per_day=1, eval 12/3 (`demo/engine.py`).
- goclaw: config.json의 agents/mcp 설정을 안 씀 → DB 등록(`setup_agent.sh`). stdio MCP는 경로 없는 python만 허용 → HTTP MCP.
  Go 1.27 json v2로 SQLite JSON 열 Scan 실패 → `agent/goclaw-sqlite-scan.patch`. 도구를 9종으로 제한 안 하면 내장 49개 노출로 2분+.
  지침(AGENTS/SOUL.md)은 DB에 저장 → `sync_context.py` 후 재시작. 데모 서버 재시작 후 MCP 재연결은 `setup_agent.sh`.
- 데모 시계는 시나리오 42일 끝에 닿으면 멈췄었음(배속 10으로 하룻밤 두면 도달 → 조작이 반영 안 됨). 지금은 `Engine._rewind()`가 1주 되감아 무한 진행, 표시 시각은 `t_off`로 계속 흐름.
- 활선 판정은 `Plant.solve` BFS(연계 TIE 경로 포함). 주 차단기가 열려도 연계가 닫혀 있으면 하위는 살아 있는 게 맞다 → 화면에 "연계 공급 ← 변압기"와 흐르는 점선으로 표시(`Engine.tie_fed`).
- `run.sh`: 이미 떠 있는 LiteLLM·goclaw는 재사용하고, 자기가 띄운 것만 **Ctrl+C 때** 정리. 데모 서버만 죽였다 다시 띄워도 에이전트는 유지된다(개발 중 재시작은 `pgrep -f "[P]ython -m demo.server"`로 서버만 kill → run.sh 재실행).
- zsh는 `HOST`를 호스트명으로 자동 설정 → 바인드 주소 변수는 `SCADA_HOST`. `run.sh` 종료 trap은 자기가 띄운 goclaw·LiteLLM만 정리한다(예전엔 무조건 죽여서 재시작이 겹치면 에이전트가 꺼졌음). 에이전트 호출 실패 → 4000·18790 포트 확인.
- 계통도 색은 국내 관례(사용자 지정): 활선·투입 **적색**, 무전압·개방 **녹색**(전압 등급별 색 없음). 계통 간 연계 차단기는 레이아웃이 주 차단기와 겹치게 놓으므로 `server.diagrams()`에서 바깥으로 ±120 빼고 상대 계통 이름 표시.
- 에이전트가 "트립 = 하위 정전"으로 넘겨짚음 → 개폐 기록에 `impact`(정전된_부하_수·상실_부하_kW)를 넣고 지침에 "정전 범위는 impact로 판단" 규칙. 단로기(DIS)는 트립 불가(`NO_TRIP`).
- 데모 프로세스 종료 시 `pkill -f "패턴"`이 그 문자열을 담은 내 셸까지 죽인다(exit 144) → `pgrep -f "[d]emo.server"`처럼 대괄호 패턴.
- 계통도: 모선 가로 구간에 여러 선로가 겹쳐 그려짐 → 가압 선로를 항상 위로(`paint()`), 아니면 정전처럼 보임.
- Word PDF 변환은 AppleScript save-as가 -1708로 실패. 쪽수는 `python3 scripts/tools/word_pages.py *.docx` — Word에 다른 문서가 열려 있으면 active document가 엉뚱한 문서를 세므로 모두 닫고 이름으로 센다.
- 사용자는 보고서에 "데이터를 다 받지 못한 사정"을 쓰는 걸 원치 않음(SWaT 사본 손상 등). FMCS가 시뮬레이션이라는 사실은 짧게 표기.

## 규칙
- 커밋·푸시 전에 `.env`·API 키가 없는지 확인. 원본 데이터·npz 캐시는 올리지 않는다(.gitignore).
- 학습을 새로 돌리면 `results/TRAINING_HISTORY.md`에 기록을 추가한다.
- 에이전트는 감시·진단 전용(제어 지시 금지) — 지침을 바꿀 때도 유지.
