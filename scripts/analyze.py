# -*- coding: utf-8 -*-
"""공통 분석: 결과 캐시(errors_*.npz) → 지표 표 + 국소화 + (FMCS) 운전 이벤트 오경보율.

사용: python -m scripts.analyze {wadi/drift_filtered|wadi/all_sensors|epic|fmcs/raw|fmcs/physics}
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
from src.eval import to_ts, normalize_errors, metrics
from scripts.analyze_wadi import SCORINGS, score

RES = Path(__file__).resolve().parents[1] / 'results'
ORDER = ['IF', 'PCA', 'MLP-AE', 'Window-AE', 'Conv-AE', 'LSTM-AE', 'GDN', 'GDN-prior', 'GDN-hybrid', 'GDN-dyn']


def runs_of(out):
    r = {}
    for m in ORDER:
        fs = sorted(out.glob(f'errors_{m}_s*.npz'))
        if fs: r[m] = [(np.load(f)['E_te'], np.load(f)['E_val']) for f in fs]
    return r


def fmcs_tags():
    from src.data.fmcs import tag_table
    return tag_table()


def event_table(name, out, meta, cols):
    """[(a, b, [원인 센서열])]"""
    if name.startswith('wadi'):
        from src.data.wadi import attack_table
        return attack_table(meta['y'], to_ts(meta['ts']))
    if name == 'epic':
        return [(s, e, [c], t) for s, e, t, c in json.load(open(out / 'events.json'))]
    if name.startswith('fmcs'):
        from src.data.fmcs import events
        ts = to_ts(meta['ts']); ev = events()
        ev = ev[(ev.kind == 'anomaly') & (ev.start >= ts[0]) & (ev.start <= ts[-1])]
        out_ = []
        for _, r in ev.iterrows():
            a = int(ts.searchsorted(r.start)); b = int(ts.searchsorted(r.end)) + 1
            tg = str(r.affected_tags).split(';')
            node_of = dict(zip(*[fmcs_tags()[k] for k in ('EQP_NAME', 'NODE')]))
            pts = [t for t in tg if t in cols] + [f'{node_of[t]}_RESID' for t in tg if t in node_of and f'{node_of[t]}_RESID' in cols]
            out_.append((a, max(b, a + 1), pts, r.type))
        return out_
    return []


def localize(E_te, E_val, table, cols):
    Z = normalize_errors(E_te, E_val); ranks = []
    for row in table:
        a, b, pts = row[:3]
        pts = [p for p in pts if p in cols]
        if not pts: continue
        order = np.argsort(-Z[a:b].mean(0))
        pos = {cols[j]: r + 1 for r, j in enumerate(order)}
        ranks.append(min(pos[p] for p in pts))
    return np.array(ranks)


def main(name):
    out = RES / name
    meta = np.load(out / 'meta.npz', allow_pickle=True)
    y = meta['y']; cols = list(meta['cols'])
    runs = runs_of(out); table = event_table(name, out, meta, cols)
    op = meta['op'] if 'op' in meta else None
    cfg = None
    if name.startswith('fmcs'):                     # STATUS 구성 인지 임계용 마스크
        from src.data import fmcs
        from src.models.ae import ok_windows
        Wd = fmcs.load_wide(); lab = fmcs.labels(index=Wd.index).fillna(0)
        tr, va, _ = fmcs.split_masks(Wd.index)
        off = fmcs.off_normal_config(Wd, fmcs.tag_table(), tr)
        cfg = dict(off_val=off[va], ok_val=~lab['anomaly'].values[va].astype(bool))
    rep, lines = {}, []
    for sname in ['raw-mean', 'norm-top5+smooth']:
        for m, rr in runs.items():
            sc = SCORINGS[sname] if m != 'IF' else dict(SCORINGS[sname], norm=False)
            rows = []
            for Et, Ev in rr:
                s, sv = score(Et, Ev, **sc)
                r = metrics(y, s, sv)
                if cfg is not None:         # 평상 개폐 구성 시점의 검증 스코어로 임계 산정
                    w = 1 if m in ('IF', 'PCA', 'MLP-AE') else 15
                    keep = ~cfg['off_val'][ok_windows(cfg['ok_val'], w)]
                    keep = keep[-len(sv):] if len(keep) >= len(sv) else np.ones(len(sv), bool)
                    from src.eval import prf
                    r['F1@qS'] = prf(y, (s > np.quantile(sv[keep], 0.99)).astype(int))[2]
                if op is not None:          # 운전 이벤트(정상 절체/트립) 중 오경보율 @정상 99% 임계
                    nm = (op == 1) & (y == 0)
                    r['FAR_op'] = float((s[nm] > np.quantile(sv, 0.99)).mean())
                    r['FAR_norm'] = float((s[(op == 0) & (y == 0)] > np.quantile(sv, 0.99)).mean())
                rows.append(r)
            df = pd.DataFrame(rows); num = df.select_dtypes('number')
            mu, sd = num.mean(), num.std().fillna(0)
            rep.setdefault(sname, {})[m] = {k: [round(float(mu[k]), 4), round(float(sd[k]), 4)] for k in mu.index}
            rep[sname][m]['events'] = list(df['events'])
            line = [sname, m, len(rr)] + [f'{mu[k]:.3f}±{sd[k]:.3f}' for k in ['ROC-AUC', 'PR-AUC', 'F1@q', 'F1*', 'F1-PA*']]
            line += [df['events'][0]] + ([f"{mu['FAR_op']:.3f}", f"{mu['FAR_norm']:.3f}", f"{mu['F1@qS']:.3f}"] if op is not None else [])
            lines.append(line)
    hdr = ['scoring', 'model', 'n', 'ROC-AUC', 'PR-AUC', 'F1@q99', 'F1*', 'F1-PA*', 'events'] + (['FAR_op', 'FAR_norm', 'F1@qS'] if op is not None else [])
    tab = pd.DataFrame(lines, columns=hdr)
    print(f'===== {name}  (test N={len(y)}, anomaly={y.mean():.3f}, D={len(cols)})')
    print(tab.to_string(index=False))
    tab.to_csv(out / 'table.csv', index=False)
    loc = {}
    for m, rr in runs.items():
        if rr[0][0].shape[1] == 1: continue
        R = np.array([localize(Et, Ev, table, cols) for Et, Ev in rr])
        if R.size == 0: continue
        loc[m] = {'n_events': int(R.shape[1]), 'top1': float((R <= 1).mean()), 'top3': float((R <= 3).mean()),
                  'top5': float((R <= 5).mean()), 'median_rank': float(np.median(R))}
        print(f"[loc] {m:10s} n={R.shape[1]} top1={loc[m]['top1']:.2f} top3={loc[m]['top3']:.2f} "
              f"top5={loc[m]['top5']:.2f} median_rank={loc[m]['median_rank']:.0f} / {len(cols)}")
    rep['localization'] = loc
    rep['info'] = {'D': len(cols), 'N': int(len(y)), 'n_events': len(table), 'anomaly_ratio': float(y.mean())}
    json.dump(rep, open(out / 'metrics.json', 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    for n in sys.argv[1:]:
        main(n)
