# -*- coding: utf-8 -*-
"""#3 개선 모델 성능 분석: 기초 모델 대비 향상 비율과 그 이유.

  (1) 데이터셋별 기초(1차 AE) vs 개선 AE vs GDN 계열 vs 앙상블(AE+GDN) — AUC / F1(최적·운영) / 오경보 / 탐지 지연
  (2) FMCS v2 단계별 ablation(한 번에 한 요소씩 추가) — 향상분이 어디서 오는지
  (3) 이상 유형별 이벤트 탐지율·지연 — 왜 좋아졌는지(어떤 유형을 새로 잡는지)
  (4) GDN 학습 그래프와 계통 토폴로지의 일치도

사용: FMCS_DATA=fmcs_synth_v2 python -m scripts.analyze3   → results/report3/analysis.json
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.eval import to_ts, normalize_errors, aggregate, smooth, metrics, prf
from scripts.analyze import runs_of, event_table
from src.models.ae import ok_windows

RES = Path(__file__).resolve().parents[1] / 'results'
OUT = RES / 'report3'
AE = ['MLP-AE', 'Window-AE', 'Conv-AE', 'LSTM-AE']
GDNS = ['GDN', 'GDN-prior', 'GDN-hybrid', 'GDN-dyn']
WIN = {'IF': 1, 'PCA': 1, 'MLP-AE': 1}
STEP = {'wadi': 10, 'epic': 2, 'fmcs': 60}       # 샘플 간격(초)
SM = {'wadi': 6, 'epic': 6, 'fmcs': 6}


class DS:
    """데이터셋 하나의 캐시 + 운영 임계/컨텍스트 마스크."""

    def __init__(self, name, key):
        self.name, self.key, self.out = name, key, RES / name
        m = np.load(self.out / 'meta.npz', allow_pickle=True)
        self.y, self.cols = m['y'], list(m['cols'])
        self.op = m['op'] if 'op' in m else None
        self.ts = to_ts(m['ts']) if 'ts' in m else None
        self.runs = runs_of(self.out)
        self.table = event_table(name, self.out, m, self.cols)
        self.keep_val, self.ctx_te, self.ctx_val = {}, None, {}
        if key == 'fmcs':
            self._fmcs_context()

    def _fmcs_context(self):
        from src.data import fmcs
        Wd = fmcs.load_wide(); tags = fmcs.tag_table(); lab = fmcs.labels(index=Wd.index).fillna(0)
        tr, va, te = fmcs.split_masks(Wd.index)
        off = fmcs.off_normal_config(Wd, tags, tr)
        ok_val = ~lab['anomaly'].values[va].astype(bool)
        M = fmcs.switching_context(Wd.ffill().bfill(), tags, self.cols, tr)
        self.ctx_te = M[te]
        for w in (1, 15):
            idx = ok_windows(ok_val, w)
            self.keep_val[w] = ~off[va][idx]
            self.ctx_val[w] = M[va][idx]

    def w(self, m): return WIN.get(m, 15)

    def score(self, m, seed=0, norm=True, k=5, sm=None, ctx=False):
        Et, Ev = self.runs[m][min(seed, len(self.runs[m]) - 1)]
        sm = SM[self.key] if sm is None else sm
        if Et.shape[1] == 1:
            return smooth(Et[:, 0], sm), smooth(Ev[:, 0], sm)
        if not norm:
            return smooth(Et.mean(1), sm), smooth(Ev.mean(1), sm)
        Zt, Zv = normalize_errors(Et, Ev), normalize_errors(Ev, Ev)
        if ctx and self.ctx_te is not None:
            Zt = np.where(self.ctx_te, 0.0, Zt); Zv = np.where(self.ctx_val[self.w(m)], 0.0, Zv)
        return smooth(aggregate(Zt, 'topk', k), sm), smooth(aggregate(Zv, 'topk', k), sm)

    def thr(self, sv, m):
        """운영 임계: 정상 검증 99% 분위 (FMCS는 평상 개폐 구성 시점만)."""
        if self.key == 'fmcs':
            kp = self.keep_val[self.w(m)]
            if len(kp) == len(sv): sv = sv[kp]
        return np.quantile(sv, 0.99)

    def evaluate(self, s, sv, m):
        r = metrics(self.y, s, sv)
        t = self.thr(sv, m); pred = s > t
        r['F1op'] = prf(self.y, pred.astype(int))[2]
        r['FAR'] = float(pred[self.y == 0].mean())
        if self.op is not None:
            nm = (self.op == 1) & (self.y == 0)
            r['FAR_op'] = float(pred[nm].mean()) if nm.any() else 0.0
        det, dl = [], []
        for row in self.table:
            a, b = row[0], row[1]
            hit = np.nonzero(pred[a:b])[0]
            det.append(len(hit) > 0)
            if len(hit): dl.append(hit[0] * STEP[self.key] / 60.0)
        r['event_recall'] = float(np.mean(det)); r['delay_min'] = float(np.median(dl)) if dl else np.nan
        r['_det'] = det
        return r


def ens(ds, models, seed=0, ctx=False):
    """앙상블: 각 모델 스코어를 검증 분포로 표준화((s − median)/IQR) 후 평균."""
    S, V = [], []
    for m in models:
        s, sv = ds.score(m, seed, ctx=ctx)
        med, iqr = np.median(sv), np.subtract(*np.quantile(sv, [0.75, 0.25])) + 1e-9
        S.append((s - med) / iqr); V.append((sv - med) / iqr)
    n = min(len(v) for v in V)
    return np.mean(S, 0), np.mean([v[-n:] for v in V], 0)


def avg(rs):
    keys = [k for k in rs[0] if not k.startswith('_') and isinstance(rs[0][k], (int, float, np.floating))]
    out = {k: float(np.nanmean([r[k] for r in rs])) for k in keys}
    out['_det'] = np.mean([r['_det'] for r in rs], 0).tolist()
    return out


def run_cfg(ds, kind, m, **kw):
    seeds = range(len(ds.runs[m if isinstance(m, str) else m[0]]))
    rs = []
    for sd in seeds:
        if kind == 'ens':
            s, sv = ens(ds, m, sd, ctx=kw.get('ctx', False)); mm = m[0]
        else:
            s, sv = ds.score(m, sd, **kw); mm = m
        rs.append(ds.evaluate(s, sv, mm))
    return avg(rs)


def best(ds, models, **kw):
    ms = [m for m in models if m in ds.runs]
    res = {m: run_cfg(ds, 'single', m, **kw) for m in ms}
    b = max(res, key=lambda m: res[m]['F1*'])
    return b, res


def graph_overlap(ds, m='GDN', hops=2):
    """GDN 학습 이웃 중 토폴로지 hops 이내 설비 비율 vs 무작위 기대치."""
    import torch
    from src.data import fmcs
    from src.models.gdn import GDN
    tags = fmcs.tag_table(); e = pd.read_csv(fmcs.ROOT / 'topology_edges.csv')
    adj = {}
    for a, b in zip(e.src, e.dst):
        adj.setdefault(a, set()).add(b); adj.setdefault(b, set()).add(a)
    node_of = dict(zip(tags.EQP_NAME, tags.NODE))
    cn = [node_of.get(c, c.rsplit('_', 1)[0]) for c in ds.cols]
    def ball(n):
        fr, seen = {n}, {n}
        for _ in range(hops):
            fr = {x for u in fr for x in adj.get(u, ())} - seen; seen |= fr
        return seen
    B = {n: ball(n) for n in set(cn)}
    p = ds.out / 'gdn_neighbors.npy'
    if not p.exists(): return None
    nb = np.load(p)
    hit = np.mean([[cn[j] in B[cn[i]] for j in nb[i]] for i in range(len(cn))])
    rnd = np.mean([np.mean([cn[j] in B[cn[i]] for j in range(len(cn))]) for i in range(0, len(cn), 7)])
    return {'learned_in_topology': float(hit), 'random_expect': float(rnd)}


def main():
    OUT.mkdir(exist_ok=True)
    rep = {}
    # ---------------- (1) 데이터셋별 요약
    for name, key, base_ds in [('wadi/drift_filtered', 'wadi', None), ('epic', 'epic', None),
                               ('fmcs_v2/kcl_rs', 'fmcs', 'fmcs_v2/raw')]:
        ds = DS(name, key)
        bds = DS(base_ds, key) if base_ds else ds
        r = {'base': run_cfg(bds, 'single', 'MLP-AE', norm=False, sm=1)}
        ba, res = best(ds, AE, ctx=(key == 'fmcs'))
        r['ae'] = res[ba]; r['ae_model'] = ba
        gs = [g for g in GDNS if g in ds.runs]
        bg, gres = best(ds, gs, ctx=(key == 'fmcs'))
        r['gdn'] = gres[bg]; r['gdn_model'] = bg; r['gdn_all'] = {g: {k: v for k, v in x.items() if k != '_det'} for g, x in gres.items()}
        r['ens'] = run_cfg(ds, 'ens', [ba, bg], ctx=(key == 'fmcs')); r['ens_models'] = [ba, bg]
        r['types'] = [row[3] if len(row) > 3 else None for row in ds.table]
        r['n_events'] = len(ds.table); r['D'] = len(ds.cols)
        rep[key] = r
        print(f'== {name}: base F1* {r["base"]["F1*"]:.3f}  AE({ba}) {r["ae"]["F1*"]:.3f}  GDN({bg}) {r["gdn"]["F1*"]:.3f}  '
              f'ENS {r["ens"]["F1*"]:.3f} | F1op {r["base"]["F1op"]:.3f}->{r["ae"]["F1op"]:.3f}/{r["ens"]["F1op"]:.3f}', flush=True)
        if key == 'fmcs':
            ov = graph_overlap(ds)
            if ov: r['graph'] = ov
    # ---------------- (2) FMCS v2 단계별 ablation
    raw, phy, kcl = DS('fmcs_v2/raw', 'fmcs'), DS('fmcs_v2/physics', 'fmcs'), DS('fmcs_v2/kcl', 'fmcs')
    krs = DS('fmcs_v2/kcl_rs', 'fmcs')
    wa = rep['fmcs']['ae_model'] if rep['fmcs']['ae_model'] != 'MLP-AE' else 'LSTM-AE'
    steps = [('1차 기초 AE', raw, 'MLP-AE', dict(norm=False, sm=1)),
             ('+시계열 윈도우', raw, wa, dict(norm=False, sm=1)),
             ('+정규화·상위k·평활', raw, wa, dict()),
             ('+물리 잔차', phy, wa, dict()),
             ('+KCL 잔차', kcl, wa, dict()),
             ('+강건 스케일링', krs, wa, dict()),
             ('+운전 컨텍스트', krs, wa, dict(ctx=True))]
    abl = []
    for lab, ds, m, kw in steps:
        r = run_cfg(ds, 'single', m, **kw); abl.append({'step': lab, 'model': m, **{k: v for k, v in r.items() if k != '_det'}})
    r = run_cfg(krs, 'ens', [wa, rep['fmcs']['gdn_model']], ctx=True)
    abl.append({'step': '+GDN 앙상블', 'model': f"{wa}+{rep['fmcs']['gdn_model']}", **{k: v for k, v in r.items() if k != '_det'}})
    rep['ablation'] = abl
    for a in abl: print(f"  {a['step']:14s} {a['model']:22s} AUC {a['ROC-AUC']:.3f} F1* {a['F1*']:.3f} F1op {a['F1op']:.3f} "
                        f"FAR_op {a.get('FAR_op', 0):.3f} recall {a['event_recall']:.2f} delay {a['delay_min']:.1f}")
    # ---------------- (3) 유형별 탐지율 (FMCS v2: 기초 vs 개선 AE vs GDN vs 앙상블, 이벤트 단위)
    f = rep['fmcs']; types = f['types']
    tab = {}
    for col, det in [('base', f['base']['_det']), ('ae', f['ae']['_det']), ('gdn', f['gdn']['_det']), ('ens', f['ens']['_det'])]:
        for t, d in zip(types, det): tab.setdefault(t, {}).setdefault(col, []).append(d)
    rep['fmcs_types'] = {t: {c: float(np.mean(v)) for c, v in d.items()} | {'n': len(d['base'])} for t, d in tab.items()}
    for t, d in sorted(rep['fmcs_types'].items()): print(f'  {t:14s} n={d["n"]} base {d["base"]:.2f} ae {d["ae"]:.2f} gdn {d["gdn"]:.2f} ens {d["ens"]:.2f}')
    e = rep['epic']; tab = {}
    for col in ('base', 'ae', 'gdn', 'ens'):
        for t, d in zip(e['types'], e[col]['_det']): tab.setdefault(t, {}).setdefault(col, []).append(d)
    rep['epic_types'] = {t: {c: float(np.mean(v)) for c, v in d.items()} | {'n': len(d['base'])} for t, d in tab.items()}
    json.dump(rep, open(OUT / 'analysis.json', 'w'), indent=1, ensure_ascii=False, default=float)
    print('saved', OUT / 'analysis.json')


if __name__ == '__main__':
    main()
