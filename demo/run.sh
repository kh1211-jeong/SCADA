#!/bin/zsh
# 데모 일괄 실행: LiteLLM(:4000) + goclaw(:18790) + 데모 서버(웹 :8765, 도구 :8766)
#   zsh ~/SCADA/demo/run.sh      → 브라우저 http://127.0.0.1:8765      종료: Ctrl+C
cd "$(dirname $0)/.."
pgrep -f "agents/goclaw/goclaw" >/dev/null || { zsh ~/agents/goclaw-scada/start.sh > ~/agents/goclaw-scada/goclaw.log 2>&1 & ; GPID=$!; }
trap '[[ -n $GPID ]] && kill $GPID 2>/dev/null; pkill -f "agents/goclaw/goclaw"; pkill -f "litellm --config"' EXIT
.venv/bin/python -m demo.server &
DPID=$!
for i in {1..40}; do curl -s -o /dev/null http://127.0.0.1:18790/health && curl -s -o /dev/null http://127.0.0.1:8765/api/agent && break; sleep 1; done
zsh ~/agents/goclaw-scada/setup_agent.sh > /dev/null 2>&1 && echo "진단 에이전트 도구 연결 완료"
echo "데모: http://127.0.0.1:8765"
open http://127.0.0.1:8765 2>/dev/null
wait $DPID
