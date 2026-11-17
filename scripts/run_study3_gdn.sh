#!/bin/zsh
# #3 GDN 변형(시간 제약: 시드 1회, 최대 25 epoch) → 분석
set -e
cd "$(dirname $0)/.."
source .venv/bin/activate
export FMCS_DATA=fmcs_synth_v2
python -m scripts.run_fmcs --feat kcl --scale robust --models GDN-prior GDN-hybrid GDN-dyn --seeds 0 --epochs 25 > results/fmcs_v2_kcl_rs_gdn.log 2>&1
python -m scripts.analyze fmcs_v2/raw fmcs_v2/physics fmcs_v2/kcl fmcs_v2/kcl_rs > results/fmcs_v2_analyze.log 2>&1
python -m scripts.analyze3 > results/analyze3.log 2>&1
echo done
