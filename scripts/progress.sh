#!/bin/zsh
# #3 학습 진행 확인: zsh scripts/progress.sh
cd "$(dirname $0)/.."
LOG=results/fmcs_v2_kcl_rs_gdn2.log
typeset -A REF; REF=(GDN-hybrid 2791 GDN-dyn 2791)      # 참고 소요시간(초) = GDN-prior 실측
pid=$(pgrep -f "scripts.run_fmcs" | head -1)
[[ -z $pid ]] && { echo "학습 프로세스 없음"; tail -3 $LOG; tail -2 results/study3_chain.log; exit; }
done_n=$(grep -c " done " $LOG)
cur=$( (( done_n == 0 )) && echo GDN-hybrid || echo GDN-dyn )
grep " ep" $LOG | tail -1                                         # epoch 로그가 있으면(다음 실행부터) 그대로 표시
start=$(stat -f %m $LOG)                                  # 로그 마지막 기록 = 현재 모델 시작 시각
now=$(date +%s); el=$(( now - start ))
pct=$(( el * 100 / REF[$cur] )); (( pct > 99 )) && pct=99
echo "완료 ${done_n}/2 | 현재 ${cur} 경과 $((el/60))분 / 예상 $((REF[$cur]/60))분 (시간 기준 추정 ~${pct}%)"
