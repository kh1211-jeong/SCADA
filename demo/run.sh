#!/bin/zsh
# 데모 일괄 실행: LiteLLM(:4000) + goclaw(:18790) + 데모 서버(웹 :8765, 도구 :8766)
#   zsh ~/SCADA/demo/run.sh      → 브라우저 http://127.0.0.1:8765      종료: Ctrl+C
#   AGENT_MODE=direct  : goclaw 없이 LiteLLM만 (사내 서버 등. goclaw는 비상업 라이선스)
#   SCADA_HOST=0.0.0.0 : 웹을 사내망에 공개
# 이미 떠 있는 LiteLLM·goclaw는 그대로 쓰고, 이 스크립트가 새로 띄운 것만 Ctrl+C 때 정리한다.
cd "$(dirname $0)/.."
A=~/agents
alive() { curl -s -o /dev/null --max-time 2 "$1"; }

if ! alive http://127.0.0.1:4000/health/liveliness; then
  zsh $A/litellm/start.sh > $A/litellm/litellm.log 2>&1 &      # start.sh가 exec 하므로 PID = LiteLLM
  LPID=$!
fi
if [[ $AGENT_MODE != direct ]] && ! alive http://127.0.0.1:18790/health; then
  for i in {1..30}; do alive http://127.0.0.1:4000/health/liveliness && break; sleep 1; done
  ( cd $A/goclaw-scada; set -a; source .env; set +a; exec $A/goclaw/goclaw ) > $A/goclaw-scada/goclaw.log 2>&1 &
  GOCLAW_STARTED=1
fi
# Ctrl+C(또는 kill) 때만 정리. 데모 서버만 죽고 재시작할 때는 에이전트를 그대로 둔다.
cleanup() { [[ -n $GOCLAW_STARTED ]] && pkill -f "[a]gents/goclaw/goclaw"; [[ -n $LPID ]] && kill $LPID 2>/dev/null; kill $DPID 2>/dev/null; exit; }
trap cleanup INT TERM

.venv/bin/python -m demo.server &
DPID=$!
HP=http://127.0.0.1:18790/health; [[ $AGENT_MODE == direct ]] && HP=http://127.0.0.1:4000/health/liveliness
for i in {1..60}; do alive $HP && alive http://127.0.0.1:${PORT:-8765}/api/agent && break; sleep 1; done
[[ $AGENT_MODE == direct ]] || { zsh $A/goclaw-scada/setup_agent.sh > /dev/null 2>&1 && echo "진단 에이전트 도구 연결 완료"; }
echo "데모: http://${SCADA_HOST:-127.0.0.1}:${PORT:-8765}"
open http://127.0.0.1:${PORT:-8765} 2>/dev/null
wait $DPID
