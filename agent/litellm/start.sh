#!/bin/zsh
# LiteLLM 프록시 실행: http://127.0.0.1:4000  (zsh ~/agents/litellm/start.sh)
cd "$(dirname $0)"
set -a; source .env; set +a
[[ -z $GEMINI_API_KEY ]] && echo "⚠ GEMINI_API_KEY가 비어 있음 — .env에 키를 넣어야 Gemini 호출이 됨"
exec .venv/bin/litellm --config config.yaml --host 127.0.0.1 --port 4000
