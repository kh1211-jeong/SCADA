#!/bin/zsh
# SCADA 진단 에이전트 실행: LiteLLM 프록시(4000) → goclaw 게이트웨이(18790)
#   zsh ~/agents/goclaw-scada/start.sh      종료: Ctrl+C
cd "$(dirname $0)"
set -a; source .env; set +a
zsh ~/agents/litellm/start.sh > litellm.log 2>&1 &
LPID=$!; trap "kill $LPID 2>/dev/null" EXIT
for i in {1..30}; do curl -s -o /dev/null http://127.0.0.1:4000/health/liveliness && break; sleep 1; done
echo "LiteLLM: http://127.0.0.1:4000  (로그 litellm.log)"
~/agents/goclaw/goclaw
