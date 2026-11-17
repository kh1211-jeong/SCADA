# 학습 이력

학습 1회 단위의 상세 기록(모델·시드·소요 시간·종료 시각·결과 폴더)은 `results/training_history_study3.csv`에 있다.
이 문서는 그 요약과 재현 방법이다.

## #3 개선 모델 성능 분석 (2026-10-21)

### 환경
- 장비: MacBook, Apple M2 (CPU 8코어 / GPU 10코어), 통합 메모리 16GB. 외부 서버·클라우드 미사용
- 연산: PyTorch 2.14.1 + MPS(Apple GPU). IF·PCA는 scikit-learn(CPU)
- 데이터: FMCS 합성 v2(`fmcs_synth_v2/`, 42일, 1분 간격, 피처 1,077개)
  - 학습 26일(37,440행) / 검증 4일(5,760행) / 평가 12일(17,280행), 평가 구간 이상 비율 29.2%
- 설정: 윈도우 15분, AE 최대 60 epoch(조기 종료 patience 5), AE 시드 3회 / GDN 변형 시드 1회
  - GDN-prior·hybrid·dyn은 최대 25 epoch

### 소요 시간 (로그 기준)

| 단계 (결과 폴더) | 모델 | 소요 |
|---|---|---|
| 태그만 (`fmcs_v2/raw`) | IF·PCA·MLP/Window/Conv/LSTM-AE × 시드 3 | 16분 |
| + 물리 잔차 (`fmcs_v2/physics`) | PCA·AE 4종 × 시드 3 | 17분 |
| + KCL 잔차 (`fmcs_v2/kcl`) | PCA·AE 4종 × 시드 3 | 17분 |
| + 강건 스케일 (`fmcs_v2/kcl_rs`) | IF·PCA·AE 4종 × 시드 3 | 11분 |
| 〃 | GDN (학습 그래프) | 35분 |
| 〃 | GDN-prior (토폴로지 고정) | 47분 |
| 〃 | GDN-hybrid (토폴로지 + 학습 top-k) | 140분* |
| 〃 | GDN-dyn (STATUS 게이팅) | 90분 |
| **합계** | 62회 | **약 6시간 10분** (실연산 약 4.5~5시간) |

\* 덮개 닫힘 잠자기(08:38~10:29) 시간이 포함됨. 실연산은 50~60분으로 추정한다.

- AE 1회 학습은 0.5~3분, GDN 1회 학습은 35~90분으로 AE의 10~30배 걸린다.
- 2026-10-21 03:34 이후 덮개가 닫혀 GDN-hybrid가 멈췄다. 08:15에 GDN-hybrid·dyn만 다시 학습했다(`scripts/run_study3_resume.sh`).

### 실행 순서 (재현)
```
export FMCS_DATA=fmcs_synth_v2
zsh scripts/run_study3.sh           # raw/physics 이후: kcl, kcl_rs(AE + GDN)
zsh scripts/run_study3_gdn.sh       # GDN-prior/hybrid/dyn (시드 0, 25 epoch) → analyze, analyze3
python -m scripts.report_figs3      # results/report3/fig*.png
python -m scripts.build_report3     # 개선모델성능분석_보고서.docx
zsh scripts/progress.sh             # 학습 중 진행률 확인 (GDN은 epoch 로그도 출력)
```
- `raw`와 `physics`는 `python -m scripts.run_fmcs --feat raw|physics`로 학습한다(Min-Max 스케일).

### 주요 결과 (`results/report3/analysis.json`)
- 운영 임계 F1(기초 AE → 최종): WADI 0.465 → 0.611 (+31%), EPIC 0.164 → 0.249 (+52%), FMCS 0.135 → 0.600 (+345%, GDN-prior)
- FMCS GDN 변형별 F1(최적/운영): 학습 그래프 0.629/0.571, 토폴로지 고정 0.709/0.600, 혼합 0.679/0.594, 동적 0.702/0.604
- 학습 그래프 이웃 중 토폴로지 2단계 이내 설비는 3.5%로, 무작위 기대치 3.5%와 같다.

### 주의
- 장시간 학습 전에는 덮개를 열어 두거나 `sudo pmset -a disablesleep 1`을 설정한다(끝나면 0으로 되돌림). `caffeinate -i`로는 덮개 닫힘 잠자기를 막지 못한다.
- `errors_*.npz` 캐시(1개 약 96MB)가 있으면 analyze·report 단계는 재학습 없이 다시 돌릴 수 있다.

## 이전 기록
- #2(2026-10-13~14): WADI·EPIC·FMCS v1 학습 로그는 `results/*.log`, 결과는 `results/{wadi,epic,fmcs}/`에 있다(1회별 시간은 각 로그의 `done Ns` 줄).

## #4 경량화 (2026-11-17~18, M2 MPS/CPU)
| 모델 (`results/fmcs_v2/lite`) | 설정 | 소요 |
|---|---|---|
| GDN-prior (교사) | 은닉 64·이웃 24, 25 epoch, MPS | 96분(CPU 병행 학습과 경합) |
| GDN-lite | 은닉 16·이웃 12, 20 epoch, CPU 5스레드 | 19분 |
| GDN-lite-KD | 은닉 16·이웃 12, 지식 증류(α=0.5), 20 epoch, MPS | 38분 |
| -int8 / -fp16 | 학습 후 변환(동적 8비트 양자화 / 16비트 실수+16비트 이웃 인덱스 저장) | 1분 |

- 결과(`eval.json`): 운영 F1 교사 0.516 → lite 0.629 → KD 0.582(-fp16 동일), 원인 설비 상위3 86 → 89 → 91%, 크기 523 → 188 → 78KB(fp16).
- 8비트 양자화는 이득 없음(크기 동일, 추론 느려짐): 저장 공간 대부분이 int64 이웃 인덱스 버퍼. 맥(ARM)은 `torch.backends.quantized.engine='qnnpack'` 필요.
- 재현: `FMCS_DATA=fmcs_synth_v2 python -m scripts.run_light --models GDN-prior GDN-lite GDN-lite-KD` → `python -m scripts.export_lite` (데모 번들 = GDN-lite-KD-fp16).
- 주의: run_light를 병행 실행하면 lite.json을 서로 덮어쓸 수 있음(지금은 쓰기 직전에 다시 읽도록 수정).
