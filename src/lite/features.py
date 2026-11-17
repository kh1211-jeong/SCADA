# -*- coding: utf-8 -*-
"""학습·실시간 추론 공용 피처 변환기 (#4 경량화·데모).

입력: 1분 wide 프레임(열 = 태그 EQP_NAME). 출력: 태그 + 설비 내부 물리 잔차(_RESID) + 설비 간 KCL 잔차(_KCL)를
강건 스케일((x − 중앙값) / (99.5% − 0.5% 분위 폭))로 정규화한 float32 배열.
#3의 fmcs.physics_residuals / kcl_residuals / prep(robust)와 같은 식이지만, 정규화 상수를 학습 기간에서만 구해
저장(feat.json)하므로 시뮬레이터 스트림 한 줄에도 같은 변환을 적용할 수 있다.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

SQ3 = float(np.sqrt(3.0))


class FeatureBuilder:
    def __init__(self, tags, edges):
        self.tags = tags
        g = tags.groupby('NODE')
        self.phys = []                                   # (node, P, V, I, PF, v_div)
        for node, d in g:
            q = dict(zip(d.QUANTITY, d.EQP_NAME)); u = dict(zip(d.QUANTITY, d.UNIT))
            if {'POWER', 'VOLTAGE', 'CURRENT', 'PF'} <= q.keys():
                self.phys.append((node, q['POWER'], q['VOLTAGE'], q['CURRENT'], q['PF'], 1000.0 if u['VOLTAGE'] == 'V' else 1.0))
        pe = edges[edges.etype == 'power']
        ch = pe.groupby('src').dst.apply(list).to_dict()
        metered = set(tags.NODE[tags.QUANTITY == 'POWER'])

        def below(n):
            out = []
            for c in ch.get(n, []):
                out += [c] if c in metered else below(c)
            return out
        self.kcl = [(n, below(n)) for n in sorted(metered) if below(n)]
        self.cols = None

    # --- 원시 잔차 (스케일 전) ---------------------------------------------------
    def residuals(self, W):
        R = {}
        for node, P, V, I, PF, dv in self.phys:
            R[f'{node}_RESID'] = W[P].values - SQ3 * (W[V].values / dv) * W[I].values * W[PF].values / 100.0
        for n, d in self.kcl:
            R[f'{n}_KCL'] = W[f'{n}_POWER'].values - W[[f'{c}_POWER' for c in d]].values.sum(1)
        return pd.DataFrame(R, index=W.index)

    def fit(self, W, train_mask, normal_mask=None):
        W = W.ffill().bfill()
        R = self.residuals(W)
        # 잔차 크기 기준 = 해당 설비 P의 95% 분위 (#3과 동일), 학습 기간에서만
        self.r_scale = {}
        for c in R.columns:
            node = c.rsplit('_', 1)[0]
            self.r_scale[c] = float(W[f'{node}_POWER'][train_mask].abs().quantile(0.95) + 1e-3)
        X = pd.concat([W, R / pd.Series(self.r_scale)], axis=1)
        keep = X[train_mask].std() > 0
        X = X.loc[:, keep]
        Xn = X[train_mask & (normal_mask if normal_mask is not None else True)]
        lo, hi, md = Xn.quantile(0.005), Xn.quantile(0.995), Xn.quantile(0.5)
        rng = (hi - lo)
        rng = rng.where(rng > 1e-9, (Xn.max() - Xn.min()).where(Xn.max() > Xn.min(), 1.0))
        st = X.columns.str.endswith('_STATUS')          # 개폐 상태는 0/1 그대로
        md[st], rng[st] = 0.0, 1.0
        self.cols = list(X.columns)
        self.lo = md.values.astype('float64'); self.rng = rng.values.astype('float64')
        return self

    def transform(self, W):
        """W: 1분 wide 프레임(행 여러 개 가능). 반환 (N, D) float32."""
        W = W.ffill().bfill()
        R = self.residuals(W) / pd.Series(self.r_scale)
        X = pd.concat([W, R], axis=1).reindex(columns=self.cols)
        return np.clip((X.values - self.lo) / self.rng, -10, 10).astype('float32')

    def save(self, path):
        json.dump({'cols': self.cols, 'lo': self.lo.tolist(), 'rng': self.rng.tolist(), 'r_scale': self.r_scale},
                  open(path, 'w'), ensure_ascii=False)

    def load(self, path):
        d = json.load(open(path))
        self.cols, self.lo, self.rng, self.r_scale = d['cols'], np.array(d['lo']), np.array(d['rng']), d['r_scale']
        return self

    def col_node(self):
        node_of = dict(zip(self.tags.EQP_NAME, self.tags.NODE))
        return [node_of.get(c, c.rsplit('_', 1)[0]) for c in self.cols]

    def col_kind(self):
        return ['물리 잔차' if c.endswith('_RESID') else 'KCL 잔차' if c.endswith('_KCL') else '태그' for c in self.cols]
