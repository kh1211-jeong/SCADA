#!/bin/zsh
# 데모 일괄 실행: LiteLLM(:4000) + goclaw(:18790) + 데모 서버(웹 :8765, 도구 :8766)
#   zsh ~/SCADA/demo/run.sh      → 브라우저 http://127.0.0.1:8765      종료: Ctrl+C
cd "$(dirname $0)/.."
# AGENT_MODE=direct: goclaw 없이 LiteLLM만 (사내 서버 등. goclaw는 비상업 라이선스)
if [[ $AGENT_MODE == direct ]]; then
  curl -s -o /dev/null http://127.0.0.1:4000/health/liveliness || { zsh ~/agents/litellm/start.sh > ~/agents/litellm/litellm.log 2>&1 & ; GPID=$!; }
else
  pgrep -f "agents/goclaw/goclaw" >/dev/null || { zsh ~/agents/goclaw-scada/start.sh > ~/agents/goclaw-scada/goclaw.log 2>&1 & ; GPID=$!; }
fi
trap '[[ -n $GPID ]] && kill $GPID 2>/dev/null; pkill -f "agents/goclaw/goclaw"; pkill -f "litellm --config"' EXIT
.venv/bin/python -m demo.server &
DPID=$!
HP=http://127.0.0.1:18790/health; [[ $AGENT_MODE == direct ]] && HP=http://127.0.0.1:4000/health/liveliness
for i in {1..40}; do curl -s -o /dev/null $HP && curl -s -o /dev/null http://127.0.0.1:${PORT:-8765}/api/agent && break; sleep 1; done
[[ $AGENT_MODE == direct ]] || zsh ~/agents/goclaw-scada/setup_agent.sh > /dev/null 2>&1 && echo "진단 에이전트 도구 연결 완료"
echo "데모: http://${SCADA_HOST:-127.0.0.1}:${PORT:-8765}"
open http://127.0.0.1:8765 2>/dev/null
wait $DPID
