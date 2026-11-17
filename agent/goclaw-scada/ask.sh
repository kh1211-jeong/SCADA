#!/bin/zsh
# 터미널에서 에이전트에 질문: zsh ask.sh "AL005 경보 원인 진단해줘"
cd "$(dirname $0)"; set -a; source .env; set +a
curl -s http://127.0.0.1:18790/v1/chat/completions \
  -H "Authorization: Bearer $GOCLAW_GATEWAY_TOKEN" -H "X-GoClaw-User-Id: operator" -H "Content-Type: application/json" \
  -d "$(python3 -c 'import json,sys; print(json.dumps({"model":"goclaw:scada-diag","messages":[{"role":"user","content":sys.argv[1]}]}))' "$1")" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["choices"][0]["message"]["content"] if "choices" in d else d)'
