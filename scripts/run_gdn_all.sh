#!/bin/zsh
# GDN 계열 학습 (기존 AE 학습 종료 후 실행)
cd "$(dirname $0)/.."
while pgrep -f "scripts.run_(fmcs|epic)" >/dev/null; do sleep 5; done
P=.venv/bin/python
$P -m scripts.run_fmcs --models GDN GDN-prior > results/fmcs_raw_gdn.log 2>&1
$P -m scripts.run_fmcs --physics --models GDN GDN-prior > results/fmcs_physics_gdn.log 2>&1
$P -m scripts.run_epic --models GDN > results/epic_gdn.log 2>&1
$P -m scripts.run_wadi --drop-drift --models GDN > results/wadi/train_gdn.log 2>&1
echo ALL_GDN_DONE
