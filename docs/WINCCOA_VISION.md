# WinCC OA Vision에 데모 화면 띄우기 — 기술 검토 (2026-11-19)

질문: "데모(계통도·실시간 값·차단기 조작·이상 점수·진단 채팅)를 WinCC OA XML 패널로 만들어 Vision에서 띄울 수 있나?"
결론: **가능하다. 단, 두 단계로 나눠서 간다.** 1단계(웹 화면을 Vision 안에 임베드)는 바로 되고,
2단계(계통도를 WinCC OA 고유 XML 패널로 생성)는 생성기를 만들고 실제 설치본에서 검증해야 한다.

> 이 Mac에는 WinCC OA가 없다. 아래 WinCC OA 기능은 제품 문서 기준의 판단이며, **설치본(3.21)에서 확인 필요** 표시가 있는 항목은
> Windows PC(`C:\WinCC_OA_Proj\CLI_TEST`)에서 실제로 열어 보기 전까지 확정이 아니다.

## 현재 기술 스택

| 층 | 지금(데모) | 비고 |
|---|---|---|
| 계통 구조 | `EGMS/build_topology.py` (277 노드·317 연결) | 원본. 재구현 금지 |
| 계통 시뮬레이터 | `src/data/synth_fmcs.py` (Python, 3초 샘플 → 1분 기록) | 학습 데이터와 같은 물리 |
| 운전 규칙 | `demo/grid_rules.py` (인터록·과부하 보호·백업) | 단일 원본 |
| 이상 탐지 | 경량 그래프 편차 신경망 78KB (PyTorch, CPU) | `demo/engine.py` |
| 진단 에이전트 | goclaw + LiteLLM + Gemini, 도구 10종(MCP) | 감시·진단 전용 |
| 화면 | Starlette 웹 서버 + 자체 SVG 단선도(`demo/static`) | 브라우저 |

## WinCC OA 쪽 선택지

### 1단계 (권장, 바로 가능): Vision 패널 안에 웹 화면 임베드
- Vision 패널에 웹 브라우저 위젯(WebView 계열 EWO)을 하나 올리고 `http://<데모서버>:8765` 를 연다. **확인 필요: 3.21 설치본의 WebView EWO 이름·속성**
- 장점: 지금 화면·에이전트·이상 점수 팝업을 그대로 Vision 안에서 쓴다. 패널 파일은 위젯 1개짜리라 XML로 손쉽게 만든다.
- 단점: 데이터가 WinCC OA 데이터포인트(DP)를 거치지 않는다(WinCC OA 알람·아카이브와 무관).

### 2단계: 계통도를 WinCC OA XML 패널로 생성
- WinCC OA는 패널을 **XML 형식**으로도 저장·로드한다(GEDI에서 PNL↔XML 변환). 텍스트라서 우리 레이아웃(`demo/server.py`의 `diagrams()`, 이미 좌표 계산됨)으로 **패널 XML을 자동 생성**할 수 있다. **확인 필요: 3.21의 XML 패널 스키마 — GEDI에서 샘플 패널 1개를 XML로 저장해 형식을 떠온 뒤 생성기를 그 형식에 맞춘다(추측으로 스키마를 쓰지 않는다).**
- 패널 구성: 선(LINE)·사각형(차단기)·원(변압기)·텍스트 + 각 설비 `dpConnect`로 색(활선 적색/무전압 녹색, 투입 적색/개방 녹색)과 값 표시. 차단기 클릭 → 조작 확인 대화 → DP에 명령 쓰기.
- 데이터 경로(택1):
  - (a) 우리 Python 시뮬레이터 → WinCC OA DP에 값 쓰기(WinCC OA의 외부 인터페이스: REST/OPC UA 서버/드라이버 중 설치본에서 쓸 수 있는 것). 이상 점수·경보도 DP로 → WinCC OA 알람 화면·아카이브 활용.
  - (b) 실제 현장: WinCC OA가 원래 받는 실측 DP를 우리 탐지 서버가 읽기만 → 이상 점수·진단만 되돌려 씀(현장 적용 목표 구성).
- 기존 자산: `scripts/winccoa/gen_svg_diagram.py`·`gen_interactive_panel.py`(SVG 배경 + 차단기 심볼 참조, **런타임 미검증**), `SKILL_winccoa.md`, EGMS의 `wincc/*.ctl`(DP 타입 생성·브릿지, **실행 미검증**).
- 진단 채팅·이상 점수 팝업은 2단계에서도 웹 위젯(1단계 방식)으로 패널 한쪽에 붙이는 게 현실적이다.

## 진행 순서 제안
1. (Windows PC) Vision 빈 패널 + WebView 위젯으로 데모 URL 열기 → 1단계 완료 확인.
2. (Windows PC) GEDI에서 선·사각형·텍스트·dpConnect 스크립트가 든 샘플 패널을 XML로 저장 → 저장소에 `docs/winccoa_sample_panel.xml`로 커밋.
3. (여기) 샘플 형식에 맞춘 XML 패널 생성기 `scripts/winccoa/gen_xml_panel.py` 작성 — 좌표는 데모와 같은 레이아웃 재사용.
4. DP 생성(CTRL 스크립트 또는 ASCII 관리자 가져오기) + 시뮬레이터 → DP 값 쓰기 경로 구성 → Vision에서 실시간 확인.
