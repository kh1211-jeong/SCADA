#!/bin/zsh
# #3 연구: FMCS v2(합성, 42일) 학습 체인 → 분석. 사용: zsh scripts/run_study3.sh
# (raw, physics는 Min-Max로 이미 학습됨: --feat raw / --feat physics 같은 형식)
set -e
cd "$(dirname $0)/.."
source .venv/bin/activate
export FMCS_DATA=fmcs_synth_v2
python -m scripts.run_fmcs --feat kcl --models PCA MLP-AE Window-AE Conv-AE LSTM-AE > results/fmcs_v2_kcl.log 2>&1
python -m scripts.run_fmcs --feat kcl --scale robust --models IF PCA MLP-AE Window-AE Conv-AE LSTM-AE GDN GDN-prior GDN-hybrid GDN-dyn > results/fmcs_v2_kcl_rs.log 2>&1
python -m scripts.analyze fmcs_v2/raw fmcs_v2/physics fmcs_v2/kcl fmcs_v2/kcl_rs > results/fmcs_v2_analyze.log 2>&1
echo done
