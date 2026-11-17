#!/bin/zsh
# 진단 에이전트 실행 환경(~/agents)을 이 저장소의 설정으로 새로 구성한다. 새 PC에서 한 번만 실행.
#   필요: go 1.26+, python3.12+, git      사용: zsh agent/install.sh
#   끝나면 ~/agents/litellm/.env 의 GEMINI_API_KEY 만 직접 채운다 (https://aistudio.google.com/apikey)
set -e
REPO=$(cd "$(dirname $0)/.." && pwd); A=~/agents
mkdir -p $A/goclaw-scada/workspace $A/goclaw-scada/data $A/litellm

# 1) goclaw: 검증한 커밋 + SQLite 버그 패치 + SQLite 전용 빌드 (비상업 라이선스 CC BY-NC 4.0)
[[ -d $A/goclaw ]] || git clone https://github.com/nextlevelbuilder/goclaw $A/goclaw
git -C $A/goclaw checkout -q $(cat $REPO/agent/GOCLAW_COMMIT)
git -C $A/goclaw apply --check $REPO/agent/goclaw-sqlite-scan.patch 2>/dev/null && git -C $A/goclaw apply $REPO/agent/goclaw-sqlite-scan.patch || echo "패치 이미 적용됨"
(cd $A/goclaw && CGO_ENABLED=0 go build -tags sqliteonly -o goclaw .)

# 2) LiteLLM 프록시 (전용 가상환경)
[[ -d $A/litellm/.venv ]] || python3 -m venv $A/litellm/.venv
$A/litellm/.venv/bin/pip install -q 'litellm[proxy]'
cp $REPO/agent/litellm/{config.yaml,start.sh} $A/litellm/

# 3) 설정·지침 복사, 비밀값 생성 (이미 있으면 유지)
cp $REPO/agent/goclaw-scada/{config.json,start.sh,setup_agent.sh,sync_context.py,ask.sh} $A/goclaw-scada/
cp $REPO/agent/goclaw-scada/workspace/*.md $A/goclaw-scada/workspace/
sed -i '' "s#/Users/keeheunjeong#$HOME#g" $A/goclaw-scada/config.json 2>/dev/null || sed -i "s#/Users/keeheunjeong#$HOME#g" $A/goclaw-scada/config.json
if [[ ! -f $A/litellm/.env ]]; then
  MK=sk-$(openssl rand -hex 16)
  printf "GEMINI_API_KEY=\nLITELLM_MASTER_KEY=$MK\n" > $A/litellm/.env
  printf "GOCLAW_CONFIG=$A/goclaw-scada/config.json\nGOCLAW_DATA_DIR=$A/goclaw-scada/data\nGOCLAW_STORAGE_BACKEND=sqlite\nGOCLAW_GATEWAY_TOKEN=$(openssl rand -hex 24)\nGOCLAW_ENCRYPTION_KEY=$(openssl rand -hex 32)\nGOCLAW_OPENAI_API_KEY=$MK\n" > $A/goclaw-scada/.env
  chmod 600 $A/litellm/.env $A/goclaw-scada/.env
fi
echo "완료. 다음: ~/agents/litellm/.env 에 GEMINI_API_KEY 입력 → zsh $REPO/demo/run.sh"
echo "(첫 기동 후 에이전트 지침 반영: python3 ~/agents/goclaw-scada/sync_context.py 후 goclaw 재시작)"
