"""계획 기반 FMCS 트렌드 합성 데이터 생성기.

설비/연결 규칙은 EGMS `build_topology.gen_grid()`를 그대로 import해서 쓴다(재구현 금지,
EGMS/CLAUDE.md 8절). 출력 포맷은 README.md 3.1의 Oracle 추출 형식을 그대로 따른다.

  - 태그명: EQP_NAME = <설비>_<물리량> (예: VCB_3F11A1_CURRENT), PARAM_CODE = 'PVLAST'
  - TRND_DATE: 'YY/MM/DD HH:MM:SS', 한 행 = 1분
  - TAG_COMPRS_VAL: '초offset:값;...' (3초 간격, offset 0은 항상 기록, 이후는
    deadband를 넘는 변화만 기록 = exception 압축 -> 불규칙 샘플링)

물리 일관성(정상 구간에서 성립하도록 생성):
  - 부하는 ACB(말단 모선)에 붙고, 상위 설비 유효/무효전력은 전원 트리를 따라 하위 합 +
    변압기 손실(BTR/LTR)로 계산한다 (KCL).
  - P = sqrt(3) * V * I * (PF/100). PF는 부호 있음(지상 +, 진상 -). STR 역송 구간은
    P, Q 모두 음수라 PF도 음수가 되어 위 식이 부호 그대로 성립한다.
  - 차단기가 열리면 하위 구간은 BFS 도달 불가 -> 전압/전류/전력 0.
  - 피더 트립 시 이중화(TIE_..AC{n}) 또는 비상(XCB) 절체, MAIN 트립 시 TIE_..BA로 ATS 절체.
  - BTR OLTC는 2차 전압 6.6kV를 deadband 1%, 지연 60초로 조정한다.
  - 온도는 부하율 제곱에 비례하는 1차 지연 열모델.

정상 패턴 위에 라벨이 붙은 이벤트를 주입한다(events.csv, labels_1min.csv).
  operational : feeder_trip, planned_maintenance, main_trip_ats
  anomaly     : ct_drift, sensor_stuck, spike_burst, pf_sign_flip, meter_offset,
                ltr_overheat, oltc_hunting, voltage_sag
  data_quality: comm_loss

사용:
  python -m src.data.synth_fmcs --days 7 --seed 0
  python -m src.data.synth_fmcs --days 1 --out-dir fmcs_synth_small --write-truth
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import lfilter

ROOT = Path(__file__).resolve().parents[2]

SEC_STEP = 3
SPM = 60 // SEC_STEP          # 1분당 샘플 수 (20)
SPD = 24 * 60 * SPM           # 1일당 샘플 수 (28800)
SQRT3 = float(np.sqrt(3.0))

# ---------------------------------------------------------------------------
# 설비 타입 규칙
# ---------------------------------------------------------------------------
SWITCH_TYPES = {"GCB", "MAIN", "VCB_K", "VCB_Q", "VCB_FEEDER", "VCB_STR", "VCB_CAP",
                "VCS_CAP", "ACB", "ACB_MAIN_EMG", "XCB", "TIE", "DIS"}
NORMALLY_OPEN_TYPES = {"TIE", "XCB"}
TIE_EDGE_TYPES = {"tie", "xtie", "xtie_cross"}
# TIE 경로로 들어올 때 자기 차단기 상태와 무관하게 모선이 가압되는 타입
# (TIE는 차단기 하류 모선에 물려 있다)
BUS_SIDE_TYPES = {"MAIN", "ACB", "ACB_MAIN_EMG"}
TIE_PATH_SWITCHES = {"TIE", "DIS", "XCB"}

# 태그 규칙: scripts/winccoa/web/gen_full_topology.py(8090 화면 태그)와 동일
# + BTR TAP(OLTC) + LTR 온도 2점(C/W, sample image/6.6_3.png 확인)
ANALOG_TYPES = {"BTR", "MAIN", "VCB_FEEDER", "ACB", "ACB_MAIN_EMG", "GCB"}
NO_STATUS_TYPES = {"BUS", "RETURN"}

UNIT = {"CURRENT": "A", "POWER": "kW", "PF": "%", "TEMP": "C", "TEMP_C": "C", "TEMP_W": "C",
        "LOAD": "%", "TAP": "step", "STATUS": "0/1"}
DECIMALS = {"CURRENT": 1, "POWER": 1, "PF": 2, "TEMP": 1, "TEMP_C": 1, "TEMP_W": 1,
            "LOAD": 1, "TAP": 0, "STATUS": 0}

V_HV = 154.0       # kV
V_MV = 6.6         # kV
V_LV = 220.0       # V (ACB 화면 단위)
TAP_NOM, TAP_MIN, TAP_MAX, TAP_STEP = 9, 1, 17, 0.0125
STD_MVA = [5.0, 7.5, 10.0, 15.0, 20.0, 30.0]
STD_KVA = [500.0, 750.0, 1000.0, 1500.0, 2000.0, 2500.0, 3000.0]
CAP_STEP_KVAR = 75.0


def _std_rating(need: float, table: list[float]) -> float:
    for r in table:
        if r >= need:
            return r
    return table[-1]


def _voltage_meta(etype: str) -> tuple[str, int]:
    """(단위, 소수 자리)"""
    if etype in ("ACB", "ACB_MAIN_EMG"):
        return "V", 1
    if etype == "GCB":
        return "kV", 2
    return "kV", 3


# ---------------------------------------------------------------------------
# EGMS 토폴로지 로드
# ---------------------------------------------------------------------------
def load_egms_grid(egms_path: str | Path | None = None):
    candidates = [egms_path, os.environ.get("EGMS_PATH"), ROOT / "EGMS", ROOT.parent / "EGMS"]
    for c in candidates:
        if c and (Path(c) / "build_topology.py").exists():
            sys.path.insert(0, str(Path(c).resolve()))
            import build_topology as bt  # EGMS 원본 모듈
            return bt.gen_grid(), Path(c).resolve()
    raise SystemExit(
        "EGMS build_topology.py를 찾지 못했습니다. --egms-path 또는 EGMS_PATH 환경변수로 "
        "github.com/kh1211-jeong/EGMS 클론 경로를 지정하세요."
    )


@dataclass
class Plant:
    names: list[str]
    etype: dict[str, str]
    meta: dict[str, dict]
    edges: list[dict]
    power_children: dict[str, list[str]]
    tie_adj: dict[str, list[str]]
    switches: list[str]
    sw_idx: dict[str, int]
    normal_state: np.ndarray
    root: str

    @classmethod
    def from_grid(cls, g) -> "Plant":
        names = [e["name"] for e in g.equipment]
        etype = {e["name"]: e["etype"] for e in g.equipment}
        meta = {e["name"]: dict(e["meta"]) for e in g.equipment}
        power_children: dict[str, list[str]] = defaultdict(list)
        tie_adj: dict[str, list[str]] = defaultdict(list)
        for e in g.edges:
            if e["etype"] in TIE_EDGE_TYPES:
                tie_adj[e["src"]].append(e["dst"])
                tie_adj[e["dst"]].append(e["src"])
            else:  # power / return
                power_children[e["src"]].append(e["dst"])
        switches = [n for n in names if etype[n] in SWITCH_TYPES]
        sw_idx = {n: i for i, n in enumerate(switches)}
        normal = np.array([0 if etype[n] in NORMALLY_OPEN_TYPES else 1 for n in switches], dtype=np.int8)
        root = next(n for n in names if etype[n] == "BUS")
        return cls(names, etype, meta, list(g.edges), power_children, tie_adj, switches, sw_idx, normal, root)

    def system_of(self, name: str) -> str | None:
        return self.meta[name].get("system")

    def solve(self, closed: np.ndarray):
        """BFS로 가압 트리 계산. 반환: (BFS 순서, parent, via_tie)"""
        parent = {self.root: None}
        via_tie = {self.root: False}
        order = [self.root]
        q = deque([self.root])
        is_closed = lambda n: closed[self.sw_idx[n]] == 1  # noqa: E731
        while q:
            u = q.popleft()
            for v in self.power_children.get(u, ()):
                if v in parent:
                    continue
                if v in self.sw_idx and not is_closed(v):
                    continue
                parent[v], via_tie[v] = u, False
                order.append(v)
                q.append(v)
            for v in self.tie_adj.get(u, ()):
                if v in parent:
                    continue
                t = self.etype[v]
                if t in TIE_PATH_SWITCHES and not is_closed(v):
                    continue
                if t not in TIE_PATH_SWITCHES and t not in BUS_SIDE_TYPES:
                    continue
                parent[v], via_tie[v] = u, True
                order.append(v)
                q.append(v)
        return order, parent, via_tie


# ---------------------------------------------------------------------------
# 태그 목록
# ---------------------------------------------------------------------------
def build_tag_table(plant: Plant) -> pd.DataFrame:
    rows = []

    def add(node: str, qty: str, unit: str, dec: int):
        rows.append({"EQP_NAME": f"{node}_{qty}", "NODE": node, "ETYPE": plant.etype[node],
                     "QUANTITY": qty, "UNIT": unit, "DECIMALS": dec,
                     "SYSTEM": plant.system_of(node) or ""})

    for n in plant.names:
        t = plant.etype[n]
        if t not in NO_STATUS_TYPES:
            add(n, "STATUS", UNIT["STATUS"], 0)
        if t in ANALOG_TYPES:
            vu, vd = _voltage_meta(t)
            add(n, "POWER", "kW", DECIMALS["POWER"])
            add(n, "VOLTAGE", vu, vd)
            add(n, "CURRENT", "A", DECIMALS["CURRENT"])
            add(n, "PF", "%", DECIMALS["PF"])
        if t == "BTR":
            add(n, "TEMP", "C", 1)
            add(n, "LOAD", "%", 1)
            add(n, "TAP", "step", 0)
        if t == "LTR":
            add(n, "TEMP_C", "C", 1)
            add(n, "TEMP_W", "C", 1)
            add(n, "LOAD", "%", 1)
    df = pd.DataFrame(rows)
    df.insert(0, "EQP_NO", np.arange(100001, 100001 + len(df)))
    df.insert(2, "USE_YN", "Y")
    return df


# ---------------------------------------------------------------------------
# 시나리오(부하/정격/이벤트) 설계
# ---------------------------------------------------------------------------
@dataclass
class LoadSpec:
    node: str
    base_kw: float
    pf: float               # 부하 역률(크기)
    daily_amp: float
    phase_h: float
    sign: float = 1.0        # STR 역송 = -1


@dataclass
class Scenario:
    days: int
    start: pd.Timestamp
    loads: list[LoadSpec]
    steps: dict[str, list[tuple[int, int, float]]]   # node -> [(t0, t1, frac)]
    ltr_kva: dict[str, float]
    btr_kva: dict[str, float]
    events: list[dict]
    sw_changes: list[tuple[int, str, int]]          # (t, switch, closed)
    cap_groups: dict[str, list[str]] = field(default_factory=dict)


def design_scenario(plant: Plant, days: int, start: pd.Timestamp, rng: np.random.Generator,
                    anomalies_per_day: float) -> Scenario:
    n_total = days * SPD
    loads: list[LoadSpec] = []
    for n in plant.names:
        t = plant.etype[n]
        m = plant.meta[n]
        if t == "ACB":
            base = rng.uniform(400, 900) if m.get("ftype") == "dual" else rng.uniform(150, 400)
            loads.append(LoadSpec(n, base, rng.uniform(0.86, 0.95), rng.uniform(0.03, 0.08), rng.uniform(12, 17)))
        elif t == "ACB_MAIN_EMG":
            loads.append(LoadSpec(n, rng.uniform(100, 300), rng.uniform(0.88, 0.95), 0.03, 14.0))
        elif t == "STR":
            loads.append(LoadSpec(n, rng.uniform(100, 250), rng.uniform(0.92, 0.97), 0.10, 13.0, sign=-1.0))

    # 공정 스텝 변화(장비 on/off): 말단 부하마다 Poisson
    steps: dict[str, list[tuple[int, int, float]]] = defaultdict(list)
    for ls in loads:
        if ls.sign < 0:
            continue
        k = rng.poisson(3.0 * days)
        for _ in range(k):
            t0 = int(rng.integers(0, n_total))
            dur = int(np.clip(rng.lognormal(np.log(90), 0.6), 15, 400) * SPM)
            steps[ls.node].append((t0, min(n_total, t0 + dur), float(np.clip(rng.normal(0, 0.10), -0.25, 0.25))))

    # 정격: LTR은 자기 부하 기준, BTR은 A/B 상호 백업(N-1) 기준
    base_by_node = {ls.node: ls.base_kw / ls.pf for ls in loads if ls.sign > 0}
    ltr_kva = {}
    for n in plant.names:
        if plant.etype[n] == "LTR":
            acbs = [c for c in plant.power_children.get(n, []) if c in base_by_node]
            ltr_kva[n] = _std_rating(1.6 * sum(base_by_node[c] for c in acbs) + 1.0, STD_KVA)

    def subtree_kva(node: str) -> float:
        tot, stack = 0.0, [node]
        while stack:
            u = stack.pop()
            tot += base_by_node.get(u, 0.0)
            stack.extend(plant.power_children.get(u, []))
        return tot

    btr_kva = {}
    by_sys = defaultdict(list)
    for n in plant.names:
        if plant.etype[n] == "BTR":
            by_sys[plant.system_of(n)].append(n)
    for sysn, btrs in by_sys.items():
        need = sum(subtree_kva(b) for b in btrs) * 1.3 / 1000.0
        r = _std_rating(max(need, 5.0), STD_MVA) * 1000.0
        for b in btrs:
            btr_kva[b] = r

    cap_groups = defaultdict(list)
    for n in plant.names:
        if plant.etype[n] == "VCS_CAP":
            cap_groups[plant.system_of(n)].append(n)

    events, sw_changes = _design_events(plant, days, rng, anomalies_per_day, n_total)
    return Scenario(days, start, loads, dict(steps), ltr_kva, btr_kva, events, sw_changes, dict(cap_groups))


def _design_events(plant: Plant, days: int, rng: np.random.Generator, anomalies_per_day: float,
                   n_total: int) -> tuple[list[dict], list[tuple[int, str, int]]]:
    events: list[dict] = []
    sw_changes: list[tuple[int, str, int]] = []
    busy: dict[str, list[tuple[int, int]]] = defaultdict(list)   # 계통별 스위칭 점유 구간
    margin = 10 * SPM

    def free(sysn: str, a: int, b: int) -> bool:
        return all(b + margin <= x or a - margin >= y for x, y in busy[sysn])

    def switching(sysn, a, b):
        busy[sysn].append((a, b))

    feeders = [n for n in plant.names if plant.etype[n] == "VCB_FEEDER"
               and plant.meta[n].get("ftype") in ("dual", "emg")]

    def feeder_event(kind_type: str, daytime: bool, dur_min: tuple[float, float]):
        for _ in range(50):
            f = feeders[int(rng.integers(len(feeders)))]
            m = plant.meta[f]
            sysn = m["system"]
            if daytime:
                d = int(rng.integers(days))
                t0 = d * SPD + int(rng.uniform(9, 15) * 60 * SPM)
            else:
                t0 = int(rng.integers(SPM * 30, n_total - SPM * 30))
            t1 = min(n_total - 1, t0 + int(rng.uniform(*dur_min) * SPM))
            if not free(sysn, t0, t1):
                continue
            switching(sysn, t0, t1)
            tr = t0 + int(rng.integers(4, 11))     # 절체 지연 12~30초
            if m["ftype"] == "dual":
                partner = f"TIE_{sysn}AC{m['num']}"
            else:
                partner = f"ACB_{sysn}A{m['num']}X"
            sw_changes.extend([(t0, f, 0), (t1, f, 1), (tr, partner, 1), (t1, partner, 0)])
            acb = f"ACB_{sysn}{m['line']}{m['num']}"
            events.append({"kind": "operational", "type": kind_type, "start": t0, "end": t1,
                           "target": f, "detail": f"{f} 개방 -> {partner} 투입 절체({(tr - t0) * SEC_STEP}s), "
                                                 f"{acb} 부하 이전"})
            return

    for _ in range(rng.poisson(1.0 * days)):
        feeder_event("feeder_trip", False, (10, 90))
    for _ in range(rng.poisson(0.5 * days)):
        feeder_event("planned_maintenance", True, (120, 240))

    systems = sorted({plant.system_of(n) for n in plant.names if plant.etype[n] == "MAIN"})
    for _ in range(rng.poisson(0.15 * days)):
        for _try in range(50):
            sysn = systems[int(rng.integers(len(systems)))]
            bank = "A" if rng.random() < 0.6 else "B"
            t0 = int(rng.integers(SPM * 60, n_total - SPM * 180))
            t1 = t0 + int(rng.uniform(20, 120) * SPM)
            if not free(sysn, t0, t1):
                continue
            switching(sysn, t0, t1)
            main, tie = f"MAIN_{sysn}{bank}", f"TIE_{sysn}BA"
            tr = t0 + int(rng.integers(2, 6))
            sw_changes.extend([(t0, main, 0), (t1, main, 1), (tr, tie, 1), (t1, tie, 0)])
            events.append({"kind": "operational", "type": "main_trip_ats", "start": t0, "end": t1,
                           "target": main, "detail": f"{main} 트립 -> {tie} ATS 투입, 뱅크 부하 반대 BTR로 이전"})
            break

    # --- 이상(anomaly) / 데이터 품질 ---
    analog_nodes = [n for n in plant.names if plant.etype[n] in ANALOG_TYPES]
    current_nodes = [n for n in analog_nodes if plant.etype[n] in ("VCB_FEEDER", "ACB", "MAIN")]
    ltrs = [n for n in plant.names if plant.etype[n] == "LTR"]
    btrs = [n for n in plant.names if plant.etype[n] == "BTR" and plant.meta[n].get("bank") == "A"]
    a_types = ["ct_drift", "sensor_stuck", "spike_burst", "pf_sign_flip", "meter_offset",
               "ltr_overheat", "oltc_hunting", "voltage_sag", "comm_loss"]
    for _ in range(rng.poisson(anomalies_per_day * days)):
        typ = a_types[int(rng.integers(len(a_types)))]
        t0 = int(rng.integers(SPM * 60, n_total - SPM * 60))
        ev = {"kind": "anomaly", "type": typ, "start": t0}
        if typ == "ct_drift":
            node = current_nodes[int(rng.integers(len(current_nodes)))]
            ramp = int(rng.uniform(120, 480) * SPM)
            ev.update(end=min(n_total - 1, t0 + ramp + int(rng.uniform(60, 240) * SPM)), target=f"{node}_CURRENT",
                      params={"gain": float(rng.uniform(1.06, 1.20)), "ramp": ramp},
                      detail="CT 비율 드리프트: 전류만 서서히 증가, P/V/PF 불변 -> 물리 잔차 증가")
        elif typ == "sensor_stuck":
            node = analog_nodes[int(rng.integers(len(analog_nodes)))]
            q = ["POWER", "CURRENT", "VOLTAGE", "PF"][int(rng.integers(4))]
            ev.update(end=min(n_total - 1, t0 + int(rng.uniform(30, 240) * SPM)), target=f"{node}_{q}",
                      detail="값 고착(flatline): exception 압축으로 offset 0만 기록됨")
        elif typ == "spike_burst":
            node = current_nodes[int(rng.integers(len(current_nodes)))]
            ev.update(end=min(n_total - 1, t0 + int(rng.uniform(1, 10) * SPM)), target=f"{node}_CURRENT",
                      params={"mult": float(rng.uniform(2.5, 6.0))}, detail="전류 순간 스파이크 다발")
        elif typ == "pf_sign_flip":
            node = analog_nodes[int(rng.integers(len(analog_nodes)))]
            ev.update(end=min(n_total - 1, t0 + int(rng.uniform(60, 360) * SPM)), target=f"{node}_PF",
                      detail="PF 부호 반전(결선/설정 오류): P = sqrt3*V*I*PF 부호 불일치")
        elif typ == "meter_offset":
            node = [n for n in current_nodes if plant.etype[n] == "ACB"]
            node = node[int(rng.integers(len(node)))]
            ev.update(end=min(n_total - 1, t0 + int(rng.uniform(60, 480) * SPM)), target=f"{node}_POWER",
                      params={"offset_frac": float(rng.choice([-1, 1]) * rng.uniform(0.15, 0.35))},
                      detail="전력계 오프셋: 하위 합(KCL)과 상위 측정 불일치")
        elif typ == "ltr_overheat":
            node = ltrs[int(rng.integers(len(ltrs)))]
            ev.update(end=min(n_total - 1, t0 + int(rng.uniform(90, 300) * SPM)), target=node,
                      params={"delta_c": float(rng.uniform(15, 30))},
                      detail="몰드변압기 냉각팬 고장: 부하와 무관한 권선온도 상승")
        elif typ == "oltc_hunting":
            node = btrs[int(rng.integers(len(btrs)))]
            ev.update(end=min(n_total - 1, t0 + int(rng.uniform(60, 180) * SPM)), target=node,
                      params={"period_min": float(rng.uniform(2, 6))},
                      detail="OLTC 헌팅: 탭 반복 왕복 -> 6.6kV 하위 전체 전압 진동")
        elif typ == "voltage_sag":
            ev.update(end=t0 + int(rng.integers(1, 10)), target="BUS_154kV",
                      params={"depth": float(rng.uniform(0.10, 0.25))},
                      detail="154kV 계통 순간전압강하(3~30초): 전 설비 전압 동시 하락")
        elif typ == "comm_loss":
            node = analog_nodes[int(rng.integers(len(analog_nodes)))]
            ev.update(kind="data_quality", end=min(n_total - 1, t0 + int(rng.uniform(10, 120) * SPM)),
                      target=node, detail="통신 두절: 해당 설비 전체 태그 행 누락")
        events.append(ev)

    events.sort(key=lambda e: e["start"])
    for i, e in enumerate(events):
        e["event_id"] = f"EV{i + 1:04d}"
        e.setdefault("params", {})
    sw_changes.sort()
    return events, sw_changes


# ---------------------------------------------------------------------------
# 시뮬레이터 (일 단위 청크, 상태 이월)
# ---------------------------------------------------------------------------
class Simulator:
    def __init__(self, plant: Plant, sc: Scenario, tags: pd.DataFrame, rng: np.random.Generator):
        self.p, self.sc, self.tags, self.rng = plant, sc, tags, rng
        self.n_total = sc.days * SPD
        self.load_nodes = [ls.node for ls in sc.loads]
        self.ar_state = np.zeros(len(sc.loads))
        self.pf_state = np.zeros(len(sc.loads))
        self.v154_state = 0.0
        self.btrs = [n for n in plant.names if plant.etype[n] == "BTR"]
        self.ltrs = [n for n in plant.names if plant.etype[n] == "LTR"]
        self.tap = np.full(len(self.btrs), TAP_NOM, dtype=float)
        self.tap_timer = np.zeros(len(self.btrs))
        self.temp_state: dict[str, float] = {}
        self.cap_on: dict[str, int] = {s: 0 for s in sc.cap_groups}
        self.state = plant.normal_state.copy()
        self.sw_ptr = 0
        self.topo_cache: dict[bytes, tuple] = {}
        self.hunt_hold: dict[str, float] = {}
        self.sensor_noise_seed = int(rng.integers(1 << 31))

    # --- 부하 --------------------------------------------------------------
    def _loads(self, t_abs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        sc, n = self.sc, len(t_abs)
        hours = ((t_abs * SEC_STEP) / 3600.0 + sc.start.hour) % 24
        day_idx = ((t_abs * SEC_STEP + sc.start.hour * 3600) // 86400).astype(int)
        weekday = ((sc.start.dayofweek + day_idx) % 7) < 5
        P = np.empty((len(sc.loads), n))
        Q = np.empty_like(P)
        phi, sd = 0.995, 0.015
        b = [np.sqrt(1 - phi ** 2) * sd]
        for i, ls in enumerate(sc.loads):
            daily = 1 + ls.daily_amp * np.sin(2 * np.pi * (hours - ls.phase_h + 6) / 24)
            week = np.where(weekday, 1.0, 0.96)
            step = np.zeros(n)
            for a, bb, frac in sc.steps.get(ls.node, ()):
                lo, hi = max(a, t_abs[0]), min(bb, t_abs[-1] + 1)
                if lo < hi:
                    step[lo - t_abs[0]:hi - t_abs[0]] += frac
            w = self.rng.standard_normal(n)
            ar, zf = lfilter(b, [1, -phi], w, zi=[phi * self.ar_state[i]])
            self.ar_state[i] = ar[-1]
            pfw = self.rng.standard_normal(n)
            pfd, _ = lfilter([np.sqrt(1 - 0.999 ** 2) * 0.01], [1, -0.999], pfw, zi=[0.999 * self.pf_state[i]])
            self.pf_state[i] = pfd[-1]
            pkw = ls.base_kw * daily * week * (1 + step) * (1 + ar) * (1 + 0.003 * self.rng.standard_normal(n))
            pkw = np.maximum(pkw, 0.05 * ls.base_kw)
            pf = np.clip(ls.pf + pfd, 0.75, 0.995)
            P[i] = ls.sign * pkw
            Q[i] = ls.sign * pkw * np.tan(np.arccos(pf))
        return P, Q

    # --- 스위치 타임라인 + 콘덴서 자동 제어 ---------------------------------
    def _switch_matrix(self, t0: int, n: int, P_load, Q_load) -> np.ndarray:
        S = np.empty((n, len(self.p.switches)), dtype=np.int8)
        chg = self.sc.sw_changes
        cap_q = {}
        for sysn in self.sc.cap_groups:
            idx = [i for i, ls in enumerate(self.sc.loads) if self.p.system_of(ls.node) == sysn]
            cap_q[sysn] = Q_load[idx].sum(axis=0)
        for k in range(n):
            t = t0 + k
            while self.sw_ptr < len(chg) and chg[self.sw_ptr][0] <= t:
                _, sw, val = chg[self.sw_ptr]
                self.state[self.p.sw_idx[sw]] = val
                self.sw_ptr += 1
            if k % (5 * SPM) == 0:   # 5분 주기 역률 제어, 목표 Q 잔여 >= 15%
                for sysn, caps in self.sc.cap_groups.items():
                    want = int(np.clip(np.floor((cap_q[sysn][k] * 0.85) / CAP_STEP_KVAR), 0, len(caps)))
                    cur = self.cap_on[sysn]
                    if want > cur:
                        cur += 1
                    elif want < cur - 1:
                        cur -= 1
                    self.cap_on[sysn] = cur
                    for j, c in enumerate(sorted(caps)):
                        self.state[self.p.sw_idx[c]] = 1 if j < cur else 0
            S[k] = self.state
        return S

    def _topology(self, closed: np.ndarray):
        key = closed.tobytes()
        if key not in self.topo_cache:
            self.topo_cache[key] = self.p.solve(closed)
        return self.topo_cache[key]

    # --- 하루 시뮬레이션 ------------------------------------------------------
    def run_day(self, d: int) -> dict[str, np.ndarray]:
        p, sc = self.p, self.sc
        t0 = d * SPD
        n = SPD
        t_abs = np.arange(t0, t0 + n)
        P_load, Q_load = self._loads(t_abs)
        S = self._switch_matrix(t0, n, P_load, Q_load)

        evs = [e for e in sc.events if e["start"] < t0 + n and e["end"] >= t0]

        # 154kV 모선 전압: 느린 랜덤워크 + 일중 변동 + 순간전압강하
        w = self.rng.standard_normal(n)
        rw, _ = lfilter([np.sqrt(1 - 0.9995 ** 2) * 0.004], [1, -0.9995], w, zi=[0.9995 * self.v154_state])
        self.v154_state = rw[-1]
        hours = ((t_abs * SEC_STEP) / 3600.0 + sc.start.hour) % 24
        v154 = V_HV * (1.005 + rw - 0.004 * np.sin(2 * np.pi * (hours - 8) / 24))
        for e in evs:
            if e["type"] == "voltage_sag":
                a, b = max(e["start"], t0) - t0, min(e["end"] + 1, t0 + n) - t0
                v154[a:b] *= 1 - e["params"]["depth"]

        # 세그먼트별 전력 흐름 (스위치 상태가 같은 구간 묶음)
        names = p.names
        node_i = {nm: i for i, nm in enumerate(names)}
        Pm = np.zeros((len(names), n))
        Qm = np.zeros((len(names), n))
        Sthru = np.zeros((len(names), n))     # 변압기 2차측 피상전력 (부하율용)
        energized = np.zeros((len(names), n), dtype=bool)
        load_idx = {ls.node: i for i, ls in enumerate(sc.loads)}

        change = np.any(S[1:] != S[:-1], axis=1)
        bounds = [0] + list(np.nonzero(change)[0] + 1) + [n]
        segments = []
        for a, b in zip(bounds[:-1], bounds[1:]):
            order, parent, via_tie = self._topology(S[a])
            segments.append((a, b, order, parent))
            sl = slice(a, b)
            m = b - a
            Pt = {v: np.zeros(m) for v in order}
            Qt = {v: np.zeros(m) for v in order}
            for v in order:
                if v in load_idx:
                    Pt[v] += P_load[load_idx[v], sl]
                    Qt[v] += Q_load[load_idx[v], sl]
                elif p.etype[v] == "VCS_CAP":
                    Qt[v] -= CAP_STEP_KVAR
                    Pt[v] += 0.003 * CAP_STEP_KVAR
            for v in reversed(order):
                t = p.etype[v]
                if t in ("BTR", "LTR"):
                    sr = sc.btr_kva[v] if t == "BTR" else sc.ltr_kva.get(v, 1000.0)
                    s_out = np.hypot(Pt[v], Qt[v])
                    Sthru[node_i[v], sl] = s_out
                    k2 = (s_out / sr) ** 2
                    Pt[v] = Pt[v] + sr * (0.0015 + 0.008 * k2)
                    Qt[v] = Qt[v] + sr * (0.005 + 0.06 * k2)
                pv = parent[v]
                if pv is not None:
                    Pt[pv] += Pt[v]
                    Qt[pv] += Qt[v]
            for v in order:
                i = node_i[v]
                energized[i, sl] = True
                if not via_tie[v]:   # TIE로 들어온 MAIN/ACB는 자기 차단기 통과 전류 0
                    Pm[i, sl] = Pt[v]
                    Qm[i, sl] = Qt[v]

        # OLTC 제어 (BTR 2차 전압)
        bi = [node_i[b] for b in self.btrs]
        hunting = {}
        for e in evs:
            if e["type"] == "oltc_hunting":
                hunting[self.btrs.index(e["target"])] = e
        drop = np.zeros((len(bi), n))
        for k, b in enumerate(self.btrs):
            sr = sc.btr_kva[b]
            drop[k] = 0.008 * Pm[bi[k]] / sr + 0.08 * Qm[bi[k]] / sr
        v_unt = (v154 / V_HV)[None, :] * (1 - drop)      # pu, 탭 1.0 기준
        taps = np.empty((len(bi), n))
        tap, timer = self.tap, self.tap_timer
        for k in range(n):
            vpu = v_unt[:, k] * (1 + TAP_STEP * (tap - TAP_NOM))
            dev = vpu - 1.0
            out = np.abs(dev) > 0.01
            timer = np.where(out, timer + 1, 0)
            move = timer >= SPM            # 60초 지연
            tap = np.where(move, np.clip(tap - np.sign(dev), TAP_MIN, TAP_MAX), tap)
            timer = np.where(move, 0, timer)
            tt = t0 + k
            for j, e in hunting.items():
                if e["start"] <= tt <= e["end"]:
                    held = self.hunt_hold.setdefault(e["event_id"], float(tap[j]))
                    per = max(1, int(e["params"]["period_min"] * SPM))
                    tap[j] = np.clip(held + (1 if ((tt - e["start"]) // per) % 2 else -1), TAP_MIN, TAP_MAX)
                    timer[j] = 0
            taps[:, k] = tap
        self.tap, self.tap_timer = tap, timer
        v2 = V_MV * v_unt * (1 + TAP_STEP * (taps - TAP_NOM))     # kV

        # 전압 하향 전파 (세그먼트별 BFS 순서 = 부모가 항상 먼저):
        # 노드 측정 전압 = 부모의 하류 전압, BTR/LTR에서 변환
        Vdown = np.zeros((len(names), n))
        Vmeas = np.zeros((len(names), n))
        btr_k = {b: k for k, b in enumerate(self.btrs)}
        for a, b, order, parent in segments:
            sl = slice(a, b)
            for v in order:
                i = node_i[v]
                t = p.etype[v]
                pv = Vdown[node_i[parent[v]], sl] if parent[v] is not None else None
                if t in ("BUS", "GCB"):
                    Vmeas[i, sl] = v154[sl]
                    Vdown[i, sl] = v154[sl]
                elif t == "BTR":
                    Vmeas[i, sl] = v2[btr_k[v], sl]
                    Vdown[i, sl] = v2[btr_k[v], sl]
                elif t == "LTR":
                    sr = sc.ltr_kva.get(v, 1000.0)
                    dlv = 0.01 * Pm[i, sl] / sr + 0.05 * Qm[i, sl] / sr
                    Vmeas[i, sl] = pv
                    Vdown[i, sl] = 225.0 * (pv / V_MV) * (1 - dlv)
                else:
                    Vmeas[i, sl] = pv
                    Vdown[i, sl] = pv

        # 온도
        hours_amb = 24 + 3 * np.sin(2 * np.pi * (hours - 9) / 24)
        out: dict[str, np.ndarray] = {}
        for b in self.btrs:
            i = node_i[b]
            K = Sthru[i] / sc.btr_kva[b]
            tgt = hours_amb + 12 + 45 * K ** 2
            out[f"{b}_TEMP"] = self._thermal(b, tgt, 120)
            out[f"{b}_LOAD"] = 100 * K
            out[f"{b}_TAP"] = taps[btr_k[b]]
        over = defaultdict(lambda: np.zeros(n))
        for e in evs:
            if e["type"] == "ltr_overheat":
                a, b2 = max(e["start"], t0) - t0, min(e["end"] + 1, t0 + n) - t0
                ramp = np.clip((np.arange(a, b2) + t0 - e["start"]) / (45 * SPM), 0, 1)
                over[e["target"]][a:b2] += e["params"]["delta_c"] * ramp
        for l in self.ltrs:
            i = node_i[l]
            K = Sthru[i] / sc.ltr_kva.get(l, 1000.0)
            out[f"{l}_TEMP_W"] = self._thermal(l + "_W", hours_amb + 15 + 70 * K ** 2 + over[l], 25)
            out[f"{l}_TEMP_C"] = self._thermal(l + "_C", hours_amb + 8 + 40 * K ** 2 + 0.5 * over[l], 60)
            out[f"{l}_LOAD"] = 100 * K

        # 전기량
        for nm in names:
            t = p.etype[nm]
            i = node_i[nm]
            if t not in NO_STATUS_TYPES:
                if nm in p.sw_idx:
                    out[f"{nm}_STATUS"] = S[:, p.sw_idx[nm]].astype(float)
                else:
                    out[f"{nm}_STATUS"] = energized[i].astype(float)
            if t in ANALOG_TYPES:
                Pk, Qk, V = Pm[i], Qm[i], Vmeas[i]
                Sk = np.hypot(Pk, Qk)
                vkv = V / 1000.0 if t in ("ACB", "ACB_MAIN_EMG") else V
                with np.errstate(divide="ignore", invalid="ignore"):
                    I = np.where(vkv > 1e-6, Sk / (SQRT3 * vkv), 0.0)
                    pf = np.where(Sk > 1e-6, np.sign(Qk + 1e-12) * np.abs(Pk) / Sk * 100.0, 0.0)
                out[f"{nm}_POWER"] = Pk
                out[f"{nm}_VOLTAGE"] = V
                out[f"{nm}_CURRENT"] = I
                out[f"{nm}_PF"] = pf
        return out

    def _thermal(self, key: str, target: np.ndarray, tau_min: float) -> np.ndarray:
        a = 1 - np.exp(-SEC_STEP / (tau_min * 60))
        y0 = self.temp_state.get(key, float(target[0]))
        y, _ = lfilter([a], [1, -(1 - a)], target, zi=[(1 - a) * y0])
        self.temp_state[key] = float(y[-1])
        return y


# ---------------------------------------------------------------------------
# 센서 계층 (잡음, 계측 이상) + exception 압축 + 직렬화
# ---------------------------------------------------------------------------
NOISE_REL = {"POWER": 0.002, "CURRENT": 0.002, "VOLTAGE": 0.0003}
NOISE_ABS = {"PF": 0.03, "TEMP": 0.05, "TEMP_C": 0.05, "TEMP_W": 0.05, "LOAD": 0.05}


def apply_sensor(truth: dict[str, np.ndarray], tags: pd.DataFrame, events: list[dict], t0: int,
                 rng: np.random.Generator) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """반환: (측정값, 행 누락 마스크(분 단위, True=누락))"""
    n = next(iter(truth.values())).shape[0]
    meas: dict[str, np.ndarray] = {}
    for row in tags.itertuples(index=False):
        x = truth[row.EQP_NAME].copy()
        q = row.QUANTITY
        if q in NOISE_REL:
            x = x * (1 + NOISE_REL[q] * rng.standard_normal(n))
        elif q in NOISE_ABS:
            x = x + NOISE_ABS[q] * rng.standard_normal(n) * (np.abs(x) > 1e-9)
        meas[row.EQP_NAME] = x
    missing: dict[str, np.ndarray] = {}
    tags_by_node = tags.groupby("NODE")["EQP_NAME"].apply(list).to_dict()
    for e in events:
        a = max(e["start"], t0) - t0
        b = min(e["end"] + 1, t0 + n) - t0
        if a >= b:
            continue
        typ, tgt = e["type"], e["target"]
        if typ == "ct_drift":
            k = np.arange(a, b) + t0 - e["start"]
            meas[tgt][a:b] *= 1 + (e["params"]["gain"] - 1) * np.clip(k / e["params"]["ramp"], 0, 1)
        elif typ == "sensor_stuck":
            meas[tgt][a:b] = meas[tgt][a]
        elif typ == "spike_burst":
            idx = rng.choice(np.arange(a, b), size=max(1, (b - a) // 15), replace=False)
            meas[tgt][idx] *= e["params"]["mult"]
        elif typ == "pf_sign_flip":
            meas[tgt][a:b] *= -1
        elif typ == "meter_offset":
            meas[tgt][a:b] += e["params"]["offset_frac"] * np.abs(meas[tgt][a:b]).mean()
        elif typ == "comm_loss":
            for tg in tags_by_node.get(tgt, []):
                mm = missing.setdefault(tg, np.zeros(n // SPM, dtype=bool))
                mm[a // SPM:(b + SPM - 1) // SPM] = True
    return meas, missing


def _deadband(q: str, unit: str, x: np.ndarray) -> float:
    if q in ("STATUS", "TAP"):
        return 0.5
    if q == "VOLTAGE":
        return {"kV": 0.0005, "V": 0.0005}[unit] * max(np.abs(x).max(), 1e-6)
    if q in ("POWER", "CURRENT"):
        return 0.002 * max(np.abs(x).mean(), 1e-6) + 0.05
    if q == "PF":
        return 0.05
    return 0.1


def _fmt(v: float, dec: int) -> str:
    s = f"{v:.{dec}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def compress_rows(meas: dict[str, np.ndarray], missing: dict[str, np.ndarray], tags: pd.DataFrame,
                  minute_index: pd.DatetimeIndex) -> list[tuple[str, str, str, str]]:
    trnd = minute_index.strftime("%y/%m/%d %H:%M:%S").tolist()
    offsets = [str(o) for o in range(0, 60, SEC_STEP)]
    rows: list[tuple[str, str, str, str]] = []
    n_min = len(minute_index)
    for row in tags.itertuples(index=False):
        x = np.round(meas[row.EQP_NAME], int(row.DECIMALS)).reshape(n_min, SPM)
        db = _deadband(row.QUANTITY, row.UNIT, x)
        rec = np.zeros_like(x, dtype=bool)
        rec[:, 0] = True
        last = x[:, 0].copy()
        for j in range(1, SPM):
            mj = np.abs(x[:, j] - last) > db
            rec[:, j] = mj
            last = np.where(mj, x[:, j], last)
        miss = missing.get(row.EQP_NAME)
        dec = int(row.DECIMALS)
        name = row.EQP_NAME
        for mi in range(n_min):
            if miss is not None and miss[mi]:
                continue
            cols = np.nonzero(rec[mi])[0]
            xv = x[mi]
            val = ";".join(f"{offsets[c]}:{_fmt(xv[c], dec)}" for c in cols)
            rows.append((name, "PVLAST", trnd[mi], val))
    return rows


# ---------------------------------------------------------------------------
# 라벨
# ---------------------------------------------------------------------------
def build_labels(events: list[dict], start: pd.Timestamp, days: int, tags: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    n_min = days * 1440
    idx = pd.date_range(start, periods=n_min, freq="min")
    flags = {k: np.zeros(n_min, dtype=np.int8) for k in ("anomaly", "operational", "data_quality")}
    types = [set() for _ in range(n_min)]
    tags_by_node = tags.groupby("NODE")["EQP_NAME"].apply(list).to_dict()
    ev_rows = []
    for e in events:
        a, b = e["start"] // SPM, e["end"] // SPM + 1
        flags[e["kind"]][a:b] = 1
        for m in range(a, min(b, n_min)):
            types[m].add(e["type"])
        tgt = e["target"]
        if tgt in tags_by_node:
            affected = tags_by_node[tgt]
        elif e["type"] == "voltage_sag":
            affected = tags.loc[tags["QUANTITY"] == "VOLTAGE", "EQP_NAME"].tolist()
        elif e["type"] in ("ltr_overheat",):
            affected = [f"{tgt}_TEMP_W", f"{tgt}_TEMP_C"]
        elif e["type"] == "oltc_hunting":
            affected = [f"{tgt}_TAP", f"{tgt}_VOLTAGE"]
        else:
            affected = [tgt]
        ev_rows.append({
            "event_id": e["event_id"], "kind": e["kind"], "type": e["type"],
            "start": start + pd.Timedelta(seconds=e["start"] * SEC_STEP),
            "end": start + pd.Timedelta(seconds=e["end"] * SEC_STEP),
            "target": tgt, "affected_tags": ";".join(affected),
            "params": json.dumps(e.get("params", {}), ensure_ascii=False), "detail": e.get("detail", ""),
        })
    lab = pd.DataFrame({"timestamp": idx, **flags, "types": [";".join(sorted(s)) for s in types]})
    return pd.DataFrame(ev_rows), lab


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def generate(out_dir: Path, days: int, seed: int, start: str, anomalies_per_day: float,
             egms_path: str | None, write_truth: bool) -> None:
    rng = np.random.default_rng(seed)
    g, egms_dir = load_egms_grid(egms_path)
    plant = Plant.from_grid(g)
    start_ts = pd.Timestamp(start)
    sc = design_scenario(plant, days, start_ts, rng, anomalies_per_day)
    tags = build_tag_table(plant)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(exist_ok=True)
    tags.to_csv(out_dir / "TN_CM_EQP.csv", index=False, encoding="utf-8")
    pd.DataFrame([{"node": n, "etype": plant.etype[n], "system": plant.system_of(n) or "",
                   "normal_closed": int(plant.normal_state[plant.sw_idx[n]]) if n in plant.sw_idx else "",
                   "rating_kva": sc.btr_kva.get(n, sc.ltr_kva.get(n, "")),
                   "meta": json.dumps(plant.meta[n], ensure_ascii=False)} for n in plant.names]
                 ).to_csv(out_dir / "topology_nodes.csv", index=False, encoding="utf-8")
    pd.DataFrame(plant.edges).to_csv(out_dir / "topology_edges.csv", index=False, encoding="utf-8")
    events_df, labels_df = build_labels(sc.events, start_ts, days, tags)
    events_df.to_csv(out_dir / "events.csv", index=False, encoding="utf-8")
    labels_df.to_csv(out_dir / "labels_1min.csv", index=False, encoding="utf-8")

    sim = Simulator(plant, sc, tags, rng)
    sensor_rng = np.random.default_rng(seed + 1)
    for d in range(days):
        truth = sim.run_day(d)
        meas, missing = apply_sensor(truth, tags, sc.events, d * SPD, sensor_rng)
        day = start_ts + pd.Timedelta(days=d)
        minute_index = pd.date_range(day, periods=1440, freq="min")
        rows = compress_rows(meas, missing, tags, minute_index)
        fn = out_dir / "raw" / f"TH_CM_FMCS_TRND_{day:%Y%m%d}.csv.gz"
        with gzip.open(fn, "wt", encoding="utf-8", newline="") as f:
            f.write("EQP_NAME,PARAM_CODE,TRND_DATE,TAG_COMPRS_VAL\n")
            f.writelines(f'{a},{b},{c},"{v}"\n' for a, b, c, v in rows)
        if write_truth:
            (out_dir / "truth").mkdir(exist_ok=True)
            tidx = pd.date_range(day, periods=SPD, freq=f"{SEC_STEP}s")
            pd.DataFrame({k: truth[k].astype(np.float32) for k in tags["EQP_NAME"]}, index=tidx).rename_axis(
                "timestamp").to_parquet(out_dir / "truth" / f"truth_{day:%Y%m%d}.parquet")
        print(f"[{d + 1}/{days}] {fn.name}: {len(rows):,} rows")

    meta = {
        "generator": "src/data/synth_fmcs.py", "seed": seed, "days": days, "start": str(start_ts),
        "egms_build_topology": str(egms_dir / "build_topology.py"),
        "n_nodes": len(plant.names), "n_edges": len(plant.edges), "n_tags": len(tags),
        "n_events": {k: int((events_df["kind"] == k).sum()) for k in ("operational", "anomaly", "data_quality")},
        "conventions": {
            "row": "1 row = 1 tag x 1 minute, TAG_COMPRS_VAL='sec:val;...' 3s grid, offset 0 always recorded, "
                   "later offsets only if |change| > deadband (exception compression)",
            "TRND_DATE": "%y/%m/%d %H:%M:%S",
            "units": {"POWER": "kW", "CURRENT": "A", "VOLTAGE": "kV (GCB/BTR/MAIN/VCB), V (ACB/ACB_MAIN_EMG)",
                      "PF": "% signed (lagging +, leading -; P=sqrt3*V*I*PF/100 holds with sign)",
                      "TEMP": "C", "LOAD": "% of transformer rating", "TAP": "OLTC step 1..17, nominal 9",
                      "STATUS": "switch: 1 closed/0 open; non-switch (BTR/LTR/STR): 1 energized"},
            "normally_open": sorted(NORMALLY_OPEN_TYPES),
        },
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"tags {len(tags)}, events {meta['n_events']} -> {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--start", default="2026-09-21 00:00:00")
    ap.add_argument("--anomalies-per-day", type=float, default=3.0)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "fmcs_synth")
    ap.add_argument("--egms-path", default=None)
    ap.add_argument("--write-truth", action="store_true", help="잡음/계측이상 전 3초 참값 parquet도 저장")
    a = ap.parse_args()
    generate(a.out_dir, a.days, a.seed, a.start, a.anomalies_per_day, a.egms_path, a.write_truth)


if __name__ == "__main__":
    main()
