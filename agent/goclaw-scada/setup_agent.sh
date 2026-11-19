#!/bin/zsh
# goclaw에 진단 에이전트(scada-diag)와 실시간 도구 서버(MCP, 데모 서버 :8766)를 등록한다. 여러 번 실행해도 됨.
#   선행: zsh start.sh (goclaw 기동), cd ~/SCADA && .venv/bin/python -m demo.server (도구 서버 기동)
cd "$(dirname $0)"; set -a; source .env; set +a
B=http://127.0.0.1:18790
H=(-H "Authorization: Bearer $GOCLAW_GATEWAY_TOKEN" -H "X-GoClaw-User-Id: operator" -H "Content-Type: application/json")
J() { python3 -c "import json,sys; d=json.load(sys.stdin); $1"; }

AID=$(curl -s "${H[@]}" $B/v1/agents | J "print(next((a['id'] for a in d.get('agents',[]) if a['agent_key']=='scada-diag'),''))")
if [[ -z $AID ]]; then
  AID=$(curl -s "${H[@]}" -X POST $B/v1/agents -d '{"agent_key":"scada-diag","display_name":"수배전 진단 에이전트","provider":"openai","model":"scada-gemini","workspace":"'$PWD'/workspace","agent_type":"predefined","is_default":true,"emoji":"⚡","max_tokens":4096,"max_tool_iterations":12,"summon":false,"memory_config":{"enabled":false}}' | J "print(d['id'])")
fi
echo "agent scada-diag = $AID"

SID=$(sqlite3 data/goclaw.db "select id from mcp_servers where name='scada'")   # 목록 API는 SQLite 빌드 버그로 비어 나옴
if [[ -z $SID ]]; then
  SID=$(curl -s "${H[@]}" -X POST $B/v1/mcp/servers -d '{"name":"scada","display_name":"수배전 실시간 진단 도구","transport":"streamable-http","url":"http://127.0.0.1:8766/mcp","tool_prefix":"scada","timeout_sec":60,"enabled":true}' | J "print(d.get('id') or d)")
fi
echo "mcp scada = $SID"
curl -s "${H[@]}" -X POST $B/v1/mcp/servers/$SID/grants/agent -d '{"agent_id":"'$AID'","enabled":true}'; echo
curl -s "${H[@]}" -X POST $B/v1/mcp/servers/$SID/reconnect; echo
curl -s "${H[@]}" $B/v1/mcp/servers/$SID/tools | head -c 600; echo

# 도구 범위: 실시간 진단 도구 9종만 노출 (기본 내장 도구 49개를 다 주면 입력이 1.8만 토큰으로 커지고 느려짐)
TOOLS='["mcp_scada__get_grid_rules","mcp_scada__get_overview","mcp_scada__list_alarms","mcp_scada__get_alarm","mcp_scada__get_switching","mcp_scada__get_topology","mcp_scada__find_equipment","mcp_scada__get_trend","mcp_scada__check_physics","mcp_scada__get_live_values"]'
curl -s "${H[@]}" -X PUT $B/v1/agents/$AID -d '{"tools_config":{"allow":'$TOOLS'},"max_tool_iterations":8}' | head -c 200; echo
