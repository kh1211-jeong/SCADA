# -*- coding: utf-8 -*-
"""오토인코더 계열 이상탐지 모델 (정상만 학습, 재구성 오차 = 이상 스코어).

- MLPAE    : 시점 단위(point-wise). 1차 발표 baseline과 같은 구조.
- WinAE    : 슬라이딩 윈도우를 펼쳐 MLP로 재구성 (시간 맥락 도입).
- ConvAE   : 1D-Conv 인코더/디코더 (국소 시간 패턴).
- LSTMAE   : LSTM 인코더 → 잠재벡터 → LSTM 디코더 (seq2seq 재구성).

모든 모델은 입력 (B, W, D)를 받아 (B, W, D)를 재구성한다. 스코어는 윈도우의 마지막 시점
오차를 쓴다(온라인/인과적 탐지: 현재 시점까지만 보고 판정).
"""
import time
import numpy as np
import torch
import torch.nn as nn


class MLPAE(nn.Module):
    def __init__(self, d, w=1, h=64, z=16):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(d, h), nn.ReLU(), nn.Linear(h, z), nn.ReLU(),
                                 nn.Linear(z, h), nn.ReLU(), nn.Linear(h, d))

    def forward(self, x):
        return self.net(x)


class WinAE(nn.Module):
    def __init__(self, d, w, h=256, z=32):
        super().__init__()
        n = d * w
        self.net = nn.Sequential(nn.Flatten(), nn.Linear(n, h), nn.ReLU(), nn.Linear(h, z), nn.ReLU(),
                                 nn.Linear(z, h), nn.ReLU(), nn.Linear(h, n), nn.Unflatten(1, (w, d)))

    def forward(self, x):
        return self.net(x)


class ConvAE(nn.Module):
    def __init__(self, d, w, h=64, z=16):
        super().__init__()
        self.enc = nn.Sequential(nn.Conv1d(d, h, 5, padding=2), nn.ReLU(),
                                 nn.Conv1d(h, z, 5, padding=2, stride=2), nn.ReLU())
        self.dec = nn.Sequential(nn.ConvTranspose1d(z, h, 4, stride=2, padding=1), nn.ReLU(),
                                 nn.Conv1d(h, d, 5, padding=2))

    def forward(self, x):                      # (B,W,D)
        return self.dec(self.enc(x.transpose(1, 2))).transpose(1, 2)[:, :x.shape[1]]


class LSTMAE(nn.Module):
    def __init__(self, d, w, h=64, z=32):
        super().__init__()
        self.w = w
        self.enc = nn.LSTM(d, h, batch_first=True)
        self.to_z = nn.Linear(h, z)
        self.dec = nn.LSTM(z, h, batch_first=True)
        self.out = nn.Linear(h, d)

    def forward(self, x):
        _, (hn, _) = self.enc(x)
        z = self.to_z(hn[-1]).unsqueeze(1).repeat(1, self.w, 1)
        o, _ = self.dec(z)
        return self.out(o)


MODELS = {'MLP-AE': MLPAE, 'Window-AE': WinAE, 'Conv-AE': ConvAE, 'LSTM-AE': LSTMAE}


def build(name, d, w, **kw):
    if name.startswith('GDN'):
        from src.models.gdn import GDN
        return GDN(d, w, **kw)
    return MODELS[name](d, w)


def _windows(X, idx, w):
    # idx: 윈도우 마지막 시점 인덱스. X[i-w+1 .. i]
    off = np.arange(-w + 1, 1)
    return X[idx[:, None] + off]


def ok_windows(ok, w):
    """ok(bool, 시점별 정상 여부) → 윈도우 전체가 정상인 마지막 시점 인덱스."""
    if ok is None: return None
    c = np.cumsum(np.r_[0, ~ok])
    i = np.arange(w - 1, len(ok))
    return i[(c[i + 1] - c[i + 1 - w]) == 0]


def fit(name, Xtr, Xval, w, epochs=40, bs=256, lr=1e-3, seed=0, patience=5, device='cpu', verbose=False,
        ok_tr=None, ok_val=None, model_kw=None):
    torch.manual_seed(seed); np.random.seed(seed)
    d = Xtr.shape[1]
    m = build(name, d, w, **(model_kw or {})).to(device)
    opt = torch.optim.Adam(m.parameters(), lr=lr)
    tri = np.arange(w - 1, len(Xtr)) if ok_tr is None else ok_windows(ok_tr, w)
    vai = np.arange(w - 1, len(Xval)) if ok_val is None else ok_windows(ok_val, w)
    best, bad, state = np.inf, 0, None
    t0 = time.time()
    for ep in range(epochs):
        m.train(); np.random.shuffle(tri)
        for s in range(0, len(tri), bs):
            xb = torch.from_numpy(_windows(Xtr, tri[s:s + bs], w)).to(device)
            loss = ((m(xb) - xb) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step()
        v = per_sensor_error(m, Xval, w, device, idx=vai).mean()
        if verbose:
            el = time.time() - t0
            print(f'  {name} ep{ep + 1}/{epochs} val={v:.5f} best={min(best, v):.5f} 경과 {el / 60:.1f}분 '
                  f'남은 최대 {el / (ep + 1) * (epochs - ep - 1) / 60:.0f}분 (조기종료 대기 {bad}/{patience})', flush=True)
        if v < best - 1e-6:
            best, bad, state = v, 0, {k: t.detach().clone() for k, t in m.state_dict().items()}
        else:
            bad += 1
            if bad >= patience: break
    m.load_state_dict(state)
    return m


@torch.no_grad()
def per_sensor_error(m, X, w, device='cpu', idx=None, bs=2048):
    """윈도우 마지막 시점의 센서별 제곱오차 (N, D). 앞쪽 w-1 시점은 첫 윈도우 값으로 채움."""
    m.eval()
    if type(m).__name__ == 'GDN': bs = min(bs, 128)          # (B, D, K, hid) 텐서 메모리 제한
    full = idx is None
    if full: idx = np.arange(w - 1, len(X))
    out = []
    for s in range(0, len(idx), bs):
        xb = torch.from_numpy(_windows(X, idx[s:s + bs], w)).to(device)
        out.append(((m(xb)[:, -1] - xb[:, -1]) ** 2).cpu().numpy())
    E = np.concatenate(out)
    if full and w > 1:
        E = np.vstack([np.repeat(E[:1], w - 1, 0), E])
    return E
