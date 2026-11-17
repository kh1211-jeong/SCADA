# 수배전 계통 이상탐지·진단 데모

웹에서 6개 계통 단선도와 실시간 값(시뮬레이터)을 보고, 차단기를 조작하거나 이상 이벤트를 주입하면
경량 그래프 신경망이 매 분 판정하고, 진단 에이전트(goclaw + Gemini)가 원인 위치를 채팅으로 설명한다.

```
브라우저 :8765 ─ demo/server.py ─┬─ engine.py  시뮬레이터(src/data/synth_fmcs, 1초 = 모의 1분) + 경량 모델 + 경보
                                 ├─ MCP :8766/mcp  읽기 전용 조회 도구 9종(tools.py)
                                 └─ agent_client.py ─► goclaw :18790 (에이전트 scada-diag) ─► LiteLLM :4000 ─► Gemini
                                                         └─ 도구 호출 ─► MCP :8766
```

## 실행
```
zsh ~/SCADA/demo/run.sh          # goclaw·LiteLLM·데모 서버를 모두 띄우고 브라우저를 연다
```
따로 띄울 때: `zsh ~/agents/goclaw-scada/start.sh` → `cd ~/SCADA && .venv/bin/python -m demo.server` →
`zsh ~/agents/goclaw-scada/setup_agent.sh`(에이전트·도구 등록/재연결, 데모 서버를 재시작했으면 다시 실행).

## 화면 사용법
- 위쪽: 진행 속도(일시정지 / 1·3·10분/초), 자동 진단 켜기, 평상 복귀(주입 이벤트 종료 + 차단기 원위치)
- 계통도: 설비를 누르면 측정값, 차단기 **투입 / 개방 / 트립(고장 모의)**, **이벤트 주입**(설비 종류에 맞는 것만) 메뉴
  - 주황 원 = 현재 이상 점수에 크게 기여하는 설비, 파란 선 = 가압, 회색 = 무전압, 점선 = 연계(평상 개방)
- 오른쪽: 이상 점수 추이(점선 = 경보 임계), 경보 / 개폐 기록 / 주입 이벤트(정답 — 에이전트에는 비공개), 진단 채팅
- 자동 진단: 차단기 조작 3분 뒤, 그리고 경보가 3분 이상 지속되면 에이전트에 자동으로 진단을 요청한다.

## 주입 가능한 이벤트 (engine.EVENT_TYPES)
계기용 변류기 비율 오차 · 계기용 변압기 비율 오차 · 측정값 고착 · 전류 순간 급등 · 역률 부호 반전 · 전력량계 치우침(220V 차단기) ·
계량되지 않는 부하(배전선) · 저압 변압기 과열 · 탭 절환기 헌팅(주 변압기) · 154kV 순간 전압 강하 · 통신 두절
- 3차 평가에서 계기용 변압기 비율 오차·변압기 과열은 모델이 못 잡았다 → 데모에서도 경보가 안 뜰 수 있다(채팅으로 직접 물어보면 에이전트가 물리 점검 도구로 찾을 수는 있음).

## 모델
`results/fmcs_v2/lite/bundle.json`(scripts/export_lite.py가 생성): 토폴로지 고정 그래프 편차 신경망, 은닉 16·이웃 12,
지식 증류 + 8비트 양자화. 학습: `FMCS_DATA=fmcs_synth_v2 python -m scripts.run_light` → `python -m scripts.export_lite`.
시뮬레이터는 학습 데이터(fmcs_synth_v2)와 같은 시나리오(seed 7, 42일, 일평균 이상 1건 설계 후 예정 이벤트 제거)를 30일째 08시부터 진행한다.

## 알려진 사항
- goclaw는 SQLite 빌드에서 Go 1.27의 JSON 타입 변경으로 MCP 서버 설정 열을 못 읽는 버그가 있어
  `internal/store/sqlitestore/mcp_servers_access.go`를 국소 패치했다(`git -C ~/agents/goclaw diff`).
- goclaw 보안 정책상 stdio MCP는 경로 없는 `python`만 허용 → 가상환경 파이썬을 못 써서 HTTP(streamable-http) 방식으로 붙인다.
- 에이전트 지침은 goclaw DB에 저장된다. `~/agents/goclaw-scada/workspace/{AGENTS,SOUL}.md`를 고친 뒤
  `python3 ~/agents/goclaw-scada/sync_context.py` 실행 후 goclaw 재시작.
- 응답 시간은 Gemini 상태에 따라 20초~1분. Gemini가 503(과부하)이면 LiteLLM이 대체 모델로 넘긴다.
