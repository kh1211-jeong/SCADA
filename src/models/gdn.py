# -*- coding: utf-8 -*-
"""GDN (Graph Deviation Network, Deng & Hooi, AAAI 2021) 경량 구현 — torch만 사용.

센서 i마다 임베딩 v_i를 학습하고, 이웃 센서들의 과거 w-1 시점을 그래프 어텐션으로 모아
현재 시점 x_i(t)를 예측한다. 이상 스코어 = 예측 오차(센서별) → AE와 같은 스코어링 파이프라인 사용.

그래프 구성
- learned : 임베딩 코사인 유사도 상위 k 이웃 (원 논문)
- prior   : 계통 토폴로지(같은 설비 내부 + 상하류 설비) 이웃을 고정 사용 → 위상 prior 주입
- hybrid  : prior ∪ 학습 상위 k (위상으로 보장된 관계 + 데이터가 찾은 원거리 상관)
- gate    : 이웃 설비의 STATUS가 개방(<0.5)이면 어텐션에서 제외 → 결선 변화에 따라 그래프가 바뀜(동적 prior)

인터페이스: 입력 (B, W, D) → 출력 (B, W, D). 출력의 마지막 시점만 예측값, 나머지는 입력 복사
(ae.fit / ae.per_sensor_error를 그대로 재사용하기 위함).
"""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class GDN(nn.Module):
    def __init__(self, d, w, hid=64, k=15, neighbors=None, hybrid=False, status_idx=None):
        super().__init__()
        self.d, self.k = d, k
        self.emb = nn.Embedding(d, hid)                 # 원 논문: 임베딩 차원 = 은닉 차원
        self.lin = nn.Linear(w - 1, hid, bias=False)
        self.att_i = nn.Parameter(torch.randn(2 * hid) * 0.1)
        self.att_j = nn.Parameter(torch.randn(2 * hid) * 0.1)
        self.bn = nn.BatchNorm1d(hid)
        self.out = nn.Sequential(nn.Linear(hid, hid), nn.ReLU(), nn.Linear(hid, 1))
        if neighbors is not None:                       # prior: (D, K) 인덱스, -1 = padding
            nb = torch.as_tensor(neighbors, dtype=torch.long)
            self.register_buffer('nb_mask', nb >= 0)
            self.register_buffer('nb_idx', nb.clamp(min=0))
        else:
            self.nb_idx = None
        self.hybrid = hybrid and neighbors is not None
        if status_idx is not None:                      # (D, K_prior) 이웃 설비 STATUS 열 인덱스, -1 = 없음
            si = torch.as_tensor(status_idx, dtype=torch.long)
            self.register_buffer('st_has', si >= 0); self.register_buffer('st_idx', si.clamp(min=0))
        else:
            self.st_idx = None

    def learned(self):
        v = F.normalize(self.emb.weight, dim=1)
        sim = v @ v.T
        sim.fill_diagonal_(-1e9)
        return sim.topk(self.k, dim=1).indices

    def neighbors(self):
        if self.nb_idx is not None:
            if self.hybrid:
                li = self.learned()
                return torch.cat([self.nb_idx, li], 1), torch.cat([self.nb_mask, torch.ones_like(li, dtype=torch.bool)], 1)
            return self.nb_idx, self.nb_mask
        idx = self.learned()
        self_idx = torch.arange(self.d, device=idx.device)[:, None]
        idx = torch.cat([self_idx, idx], 1)            # 자기 자신 포함
        return idx, torch.ones_like(idx, dtype=torch.bool)

    def forward(self, x):                               # x: (B, W, D)
        B, W, D = x.shape
        hist = x[:, :-1].transpose(1, 2)                # (B, D, W-1)
        h = self.lin(hist)                              # (B, D, hid)
        v = self.emb.weight                             # (D, emb)
        idx, mask = self.neighbors()                    # (D, K)
        g = torch.cat([h, v.expand(B, -1, -1)], -1)     # (B, D, 2*hid)
        gi = (g * self.att_i).sum(-1)                   # (B, D)
        gj = (g * self.att_j).sum(-1)                   # (B, D)
        e = F.leaky_relu(gi[:, :, None] + gj[:, idx], 0.2)          # (B, D, K)
        e = e.masked_fill(~mask[None], -1e9)
        if self.st_idx is not None:                     # 직전 시점 STATUS 개방 이웃 제외 (자기 자신 열 0은 유지)
            st = x[:, -2][:, self.st_idx]                               # (B, D, K_prior)
            off = self.st_has[None] & (st < 0.5)
            off[:, :, 0] = False
            pad = e.shape[-1] - off.shape[-1]
            if pad: off = torch.cat([off, torch.zeros_like(off[..., :1]).expand(-1, -1, pad)], -1)
            e = e.masked_fill(off, -1e9)
        a = torch.softmax(e, -1)
        z = (a[..., None] * h[:, idx]).sum(2)                        # (B, D, hid)
        z = F.relu(self.bn(z.transpose(1, 2)).transpose(1, 2))
        pred = self.out(z * v[None]).squeeze(-1)                    # (B, D)
        return torch.cat([x[:, :-1], pred[:, None]], 1)


def status_index(cols, nb, tag_table):
    """이웃 인덱스 (D, K) → 각 이웃 피처가 속한 설비의 STATUS 열 인덱스 (D, K), 없으면 -1."""
    node_of = dict(zip(tag_table.EQP_NAME, tag_table.NODE))
    pos = {c: i for i, c in enumerate(cols)}
    col_node = [node_of.get(c, c.rsplit('_', 1)[0]) for c in cols]
    st_of = np.array([pos.get(f'{n}_STATUS', -1) for n in col_node])
    return np.where(nb >= 0, st_of[np.clip(nb, 0, None)], -1)


def topology_neighbors(cols, tag_table, edges, k_max=24):
    """FMCS 태그 열 → 이웃 인덱스 (D, K). 이웃 = 같은 설비(NODE) 태그 + 토폴로지 인접 설비의 태그.
    물리 잔차 열('<NODE>_RESID')은 해당 NODE에 속한 것으로 본다."""
    node_of = dict(zip(tag_table.EQP_NAME, tag_table.NODE))
    col_node = [node_of.get(c, c.rsplit('_', 1)[0] if c.endswith(('_RESID', '_KCL')) else None) for c in cols]
    adj = {}
    for s, t in zip(edges.src, edges.dst):
        adj.setdefault(s, set()).add(t); adj.setdefault(t, set()).add(s)
    by_node = {}
    for i, n in enumerate(col_node):
        by_node.setdefault(n, []).append(i)
    out = np.full((len(cols), k_max), -1, dtype=np.int64)
    for i, n in enumerate(col_node):
        nb = [i] + [j for j in by_node.get(n, []) if j != i]
        for m in sorted(adj.get(n, ())):
            nb += by_node.get(m, [])
        nb = list(dict.fromkeys(nb))[:k_max]
        out[i, :len(nb)] = nb
    return out
