# GUIDE.md — 사내 리눅스 서버에 데모 웹·진단 에이전트 올리기

이 문서는 **사내망 리눅스 서버에서 이 저장소를 받은 Claude Code(또는 사람)** 가 그대로 따라 할 수 있게 쓴 설치·운영 안내다.
프로젝트 전체 배경과 작업 규칙은 `CLAUDE.md`를 먼저 읽는다. 여기서는 "서버에 띄워서 사내에서 접속"만 다룬다.

## 0. 무엇을 띄우는가

```
[사내 사용자 브라우저] ──▶ ① 데모 서버  demo/server.py  (Python)
                              :8765  웹 화면(계통도·실시간 값·차단기 조작·이벤트 주입·진단 채팅)
                              :8766  에이전트용 조회 도구(MCP, 읽기 전용 9종)
                              내부: 시뮬레이터(src/data/synth_fmcs.py) + 경량 이상탐지 모델(78KB, CPU) + 경보
                                 │ 경보/트립 시 진단 요청
                                 ▼
                         ② (선택) goclaw :18790  에이전트 실행기(Go). 지침 demo/AGENTS.md, 도구는 ①:8766
                                 │
                                 ▼
                         ③ LiteLLM :4000  OpenAI 형식 → Gemini(또는 사내 LLM) 변환 프록시
                                 │
                                 ▼
                         ④ LLM: Google Gemini API(인터넷) 또는 사내 LLM 서버
```

- **사내 서버 권장 구성 = `AGENT_MODE=direct`**: ②goclaw를 빼고 ①이 ③LiteLLM에 직접 붙어 같은 도구로 진단한다
  (`demo/agent_client.py`의 예비 경로). 이유: goclaw는 **CC BY-NC 4.0(비상업) 라이선스** → 회사 사용은 법무 확인 전 쓰지 않는다.
  기능 차이는 거의 없다(지침·도구 동일).
- 외부에 여는 포트는 **:8765 하나만**. :8766·:4000·:18790은 127.0.0.1 전용으로 둔다(코드 기본값).
- 에이전트는 **감시·진단 전용**이다. 제어 도구를 추가하지 말 것.

## 1. 사전 점검 (설치 전에 사용자에게 확인)

| 항목 | 확인 방법 | 안 되면 |
|---|---|---|
| 배포판 | `cat /etc/os-release` | Ubuntu 22.04+/RHEL 9+ 기준. 아래 패키지명만 다름 |
| Python 3.12+ | `python3 --version` | `apt install python3.12 python3.12-venv` / `dnf install python3.12` |
| GitHub 접근 | `git ls-remote https://github.com/kh1211-jeong/SCADA` | 사내 프록시 설정 또는 사용자가 zip/번들로 반입 |
| PyPI 접근 | `pip download --no-deps six -d /tmp/x` | 사내 PyPI 미러 주소를 `pip config`에 지정 |
| LLM 접근 | `curl -sI https://generativelanguage.googleapis.com` | 막혀 있으면 4-2(사내 LLM)로. 진단 채팅만 안 되고 화면·탐지는 동작 |
| 보안 정책 | 사용자에게 질문 | 경보 내용·설비명이 LLM으로 전송됨. 현재 데이터는 **합성(시뮬레이션)** 이라 민감도 낮음. 실데이터 연결 시 외부 LLM 승인 필요 |

사내 프록시가 있으면 셸과 서비스 모두에 `HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY=127.0.0.1,localhost` 를 지정한다
(NO_PROXY를 빠뜨리면 내부 포트 간 호출이 프록시로 새서 진단이 실패한다).

## 2. 설치

```bash
# 시스템 패키지 (Ubuntu 예; RHEL은 dnf)
sudo apt install -y git zsh curl openssl sqlite3 python3-venv

git clone --recursive https://github.com/kh1211-jeong/SCADA && cd SCADA      # EGMS 서브모듈 필수(--recursive)
python3 -m venv .venv
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU 판 (GPU 불필요, 용량 작음)
.venv/bin/pip install -r requirements.txt

SKIP_GOCLAW=1 zsh agent/install.sh       # ~/agents/litellm 구성 (goclaw 빌드 생략)
```

- 데모만 돌릴 때는 **합성 데이터 생성(1.2GB)·학습이 필요 없다.** 필요한 파일은 저장소에 있다:
  `fmcs_synth_v2/{TN_CM_EQP,topology_nodes,topology_edges}.csv`, `results/fmcs_v2/lite/{bundle.json,feat.json,GDN-lite-KD-fp16.pt,neighbors_k12.npy}`, `EGMS/`.
- `requirements.txt`의 `torch_geometric`, `h5py`, `langgraph` 등은 데모에 안 쓴다. 설치가 막히면 데모용 최소 패키지만 설치해도 된다:
  `pandas numpy scipy scikit-learn torch mcp uvicorn starlette`.
- 비밀값: `~/agents/litellm/.env` 의 `GEMINI_API_KEY=` 에 **사용자가 직접** 키를 넣는다(Claude가 키를 만들거나 받아 적지 않는다).
  `.env` 파일은 git에 올리지 않는다(권한 600).

## 3. 실행

```bash
cd ~/SCADA
HOST=0.0.0.0 AGENT_MODE=direct zsh demo/run.sh        # 웹 :8765 를 사내망에 공개, LiteLLM 직결
```

| 환경변수 | 기본값 | 의미 |
|---|---|---|
| `HOST` | 127.0.0.1 | 웹(:8765)이 열릴 주소. 사내 접속은 `0.0.0.0`. MCP(:8766)는 항상 127.0.0.1 |
| `PORT` | 8765 | 웹 포트 |
| `AGENT_MODE` | (goclaw) | `direct`면 goclaw를 띄우지도 쓰지도 않음 |
| `WARMUP` | 40 | 시작 시 모델 입력 창을 채우는 모의 분 수 |
| `LITELLM_URL`, `GOCLAW_URL` | 127.0.0.1 | 프록시를 다른 곳에 둘 때 |

확인:
```bash
curl -s 127.0.0.1:8765/api/agent            # {"backend": "litellm", ...}  → 진단 경로 정상
curl -s 127.0.0.1:8765/api/state | head -c 200   # time 값이 1초마다 증가하면 시뮬레이터 정상
```
방화벽: `sudo ufw allow 8765/tcp` (또는 `firewall-cmd --add-port=8765/tcp --permanent && firewall-cmd --reload`).
사내 사용자 접속 주소: `http://<서버IP>:8765`.

## 4. LLM 선택

### 4-1. Gemini (기본)
`agent/litellm/config.yaml`: `scada-gemini` = `gemini/gemini-flash-lite-latest`, 오류·한도 초과 시 `gemini-3.5-flash`로 자동 전환.
사용량 제한은 Google AI Studio 쪽 한도로 건다.

### 4-2. 사내 LLM (외부 호출 불가·불허일 때)
`~/agents/litellm/config.yaml`의 `scada-gemini` 항목의 `litellm_params`만 바꾼다. 이름(`model_name: scada-gemini`)은 그대로 둔다(코드가 이 이름을 부름).
```yaml
  - model_name: scada-gemini
    litellm_params:
      model: openai/<사내 모델명>            # vLLM·Ollama 등 OpenAI 호환 서버
      api_base: http://<사내LLM주소>/v1
      api_key: os.environ/INTERNAL_LLM_KEY
```
**도구 호출(function calling)을 지원하는 모델이어야 한다.** 지원 안 하면 에이전트가 도구를 못 불러 진단이 비게 된다.

## 5. 상시 운영 (systemd)

`/etc/systemd/system/scada-demo.service` (사용자명·경로를 실제 값으로):
```ini
[Unit]
Description=SCADA demo (web + diagnosis agent)
After=network-online.target

[Service]
User=<사용자>
WorkingDirectory=/home/<사용자>/SCADA
Environment=HOST=0.0.0.0
Environment=AGENT_MODE=direct
# Environment=HTTPS_PROXY=http://proxy:port
# Environment=NO_PROXY=127.0.0.1,localhost
ExecStart=/usr/bin/zsh demo/run.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now scada-demo
journalctl -u scada-demo -f
```
`run.sh`는 종료 시 LiteLLM도 함께 정리한다(trap). 재시작하면 시뮬레이터는 10/7 08:00부터 다시 시작한다.

## 6. 함정 (실제로 겪은 것)

- **시뮬레이터는 학습 데이터와 같은 시나리오여야 한다** (seed 7, 42일, v2 — `demo/engine.py`). 바꾸면 경량 모델이 오경보를 낸다.
  42일 끝에 닿으면 1주 되감아 무한 진행한다(`Engine._rewind`). 예전에는 여기서 멈춰 "차단기 조작이 안 먹는" 증상이 났다.
- 측정값은 학습 때와 같은 기록 방식(소수 자릿수 반올림 + 데드밴드 + 1분 평균)으로 만든다. 이걸 빼면 정상인데도 경보가 뜬다.
- 진단 채팅이 "응답 없음"이면: `curl 127.0.0.1:4000/health/liveliness` → LiteLLM 로그 `~/agents/litellm/litellm.log` → 키·프록시·NO_PROXY 순으로 본다.
  Gemini 503(과부하)은 대체 모델로 자동 전환되지만 둘 다 막히면 실패한다.
- 접속자 전원이 **같은 시뮬레이션 상태를 공유**한다(한 사람이 차단기를 열면 모두에게 열림). 로그인·조작 권한은 아직 없다
  → 사내 공개 전에 사용자에게 알리고, 필요하면 조작 권한 기능을 먼저 만든다(`CLAUDE.md` 다음 할 일).
- goclaw를 쓸 경우(라이선스 확인 후): `agent/install.sh`를 SKIP_GOCLAW 없이 실행(Go 1.26+ 필요). DB 등록·SQLite 패치·도구 9종 제한 등은 `CLAUDE.md` 함정 절 참고.
- 맥 전용 명령은 없다(`open`은 실패해도 무시). 스크립트는 zsh 기준이라 `zsh`를 설치해야 한다.

## 7. 사내 Claude가 지킬 것

- `.env`·API 키·사내 서버 주소·사용자 계정 정보를 커밋하거나 외부로 보내지 않는다.
- 외부 공개(인터넷)는 하지 않는다. 사내망 공개도 사용자 확인 후.
- 코드나 설정을 바꾸면 `CLAUDE.md`의 "현재 상태/다음 할 일"과 이 문서를 같이 갱신해서 커밋한다.
