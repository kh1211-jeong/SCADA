#!/bin/zsh
cd "$(dirname $0)/.."
P=.venv/bin/python
while pgrep -f src.data.synth_fmcs >/dev/null; do sleep 5; done
$P -m src.data.fmcs > results/fmcs_load.log 2>&1
$P -m scripts.run_fmcs --models IF PCA MLP-AE Window-AE Conv-AE LSTM-AE GDN GDN-prior > results/fmcs_raw.log 2>&1
$P -m scripts.run_fmcs --physics --models IF PCA MLP-AE Window-AE Conv-AE LSTM-AE GDN GDN-prior > results/fmcs_physics.log 2>&1
$P -m scripts.run_epic --models GDN > results/epic_gdn.log 2>&1
$P -m scripts.run_wadi --drop-drift --models GDN > results/wadi/train_gdn.log 2>&1
echo ALL_DONE
