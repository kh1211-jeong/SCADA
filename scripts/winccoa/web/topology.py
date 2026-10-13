"""Electrical topology graph for one BTR bank - nodes (bus segments) + edges
(breakers). Built as an actual tree so energized/de-energized state can be
computed by reachability from the always-on source, and propagates downward
when any ancestor breaker opens - this is the model gen_web_svg.py draws
from and server.js walks at runtime.

Simplification (documented, not hidden): K/Q-span and feeder branch letters
are treated as directly tied to the matching-letter MAIN side (letter "A"
traces to VCB_<bank>A, letter "C" to the shared main bus reachable via the
bank-internal TIE) - this matches the confirmed screen evidence (K-span
letters share the feeder-branch letters) but the exact bus-sectionalizing
detail per letter was not itself surveyed. See SKILL_winccoa.md 4.5/4.6.

A "node" is a bus segment with an SVG anchor point (x, y) used both to draw
the node's own stub and as the line endpoint for every edge touching it.
An "edge" is either:
  - a breaker edge: gated by one DPE tag (STATUS.value) - energized only if
    its parent node is energized AND this tag is currently true.
  - a fixed edge (tag=None): always conducts if its parent node is energized
    (e.g. BTR secondary - no modeled breaker between source and BTR output).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.topology.equipment_catalog import K_SPAN, Q_SPAN, FEEDER_BANKS, FEEDER_INDEX_RANGE  # noqa: E402

W = 2200


@dataclass
class Node:
    id: str
    x: float
    y: float


@dataclass
class Edge:
    id: str
    frm: str
    to: str
    tag: str | None  # STATUS.value DPE gating this edge; None = always conducts


@dataclass
class Topology:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def add_node(self, id: str, x: float, y: float) -> Node:
        n = Node(id, x, y)
        self.nodes[id] = n
        return n

    def add_edge(self, frm: str, to: str, tag: str | None) -> Edge:
        e = Edge(f"e_{len(self.edges)}_{to}", frm, to, tag)
        self.edges.append(e)
        return e


def build(bank_root: str) -> Topology:
    t = Topology()
    bank_a, bank_b = f"{bank_root}A", f"{bank_root}B"
    xa, xb = W * 0.28, W * 0.72
    y_btr_out = 120
    y_main = 210
    y_main_bus = y_main + 23
    xtie = (xa + xb) / 2

    # sources: BTR secondaries, always energized (no modeled 154kV-side breaker)
    t.add_node(f"src_{bank_a}", xa, y_btr_out)
    t.add_node(f"src_{bank_b}", xb, y_btr_out)
    t.sources = [f"src_{bank_a}", f"src_{bank_b}"]

    t.add_node(f"mainbus_{bank_a}", xa, y_main_bus)
    t.add_node(f"mainbus_{bank_b}", xb, y_main_bus)
    t.add_edge(f"src_{bank_a}", f"mainbus_{bank_a}", f"VCB_{bank_a}_STATUS.value")
    t.add_edge(f"src_{bank_b}", f"mainbus_{bank_b}", f"VCB_{bank_b}_STATUS.value")

    # bank-internal tie: bidirectional, so model as two directed edges
    t.add_edge(f"mainbus_{bank_a}", f"mainbus_{bank_b}", f"TIE_{bank_root}BA_STATUS.value")
    t.add_edge(f"mainbus_{bank_b}", f"mainbus_{bank_a}", f"TIE_{bank_root}BA_STATUS.value")

    y_k = 300
    k_letters = K_SPAN.get(bank_root, {}).get("letters", [])
    letter_side = {"A": bank_a, "B": bank_b, "C": bank_a, "D": bank_b}  # A/C off main-A side, B/D off main-B side
    if k_letters:
        kx0 = W * 0.5 - (len(k_letters) - 1) * 72 / 2
        for i, letter in enumerate(k_letters):
            kx = kx0 + i * 72
            parent_bus = f"mainbus_{letter_side.get(letter, bank_a)}"
            node_id = f"k_{letter}"
            t.add_node(node_id, kx, y_k)
            t.add_edge(parent_bus, node_id, f"VCB_{bank_root}{letter}K_STATUS.value")

    y_q = 380
    q_letters = Q_SPAN.get(bank_root, {}).get("letters", [])
    if q_letters:
        qx0 = W * 0.5 - (len(q_letters) - 1) * 72 / 2
        for i, letter in enumerate(q_letters):
            qx = qx0 + i * 72
            parent_bus = f"mainbus_{letter_side.get(letter, bank_a)}"
            node_id = f"q_{letter}"
            t.add_node(node_id, qx, y_q)
            t.add_edge(parent_bus, node_id, f"VCB_{bank_root}{letter}Q_STATUS.value")

    # feeder buses: fed from whichever K/Q node shares the branch letter
    y_feed_bus = 470
    y_row_h = 250
    branches = FEEDER_BANKS.get(bank_root, {}).get("branches", [])
    FEEDER_STEP = 130
    FEEDER_X0 = 140
    for bi, branch in enumerate(branches):
        y_bus = y_feed_bus + bi * y_row_h
        x_start = FEEDER_X0
        x_end = FEEDER_X0 + (len(list(FEEDER_INDEX_RANGE)) - 1) * FEEDER_STEP
        feedbus_id = f"feedbus_{bank_root}{branch}"
        t.add_node(feedbus_id, (x_start + x_end) / 2, y_bus)
        # feed this bus from the matching-letter K node if present, else the matching Q node,
        # else fall back to the branch-letter's own main bus (best-effort, documented above)
        parent = None
        if f"k_{branch}" in t.nodes:
            parent = f"k_{branch}"
        elif f"q_{branch}" in t.nodes:
            parent = f"q_{branch}"
        else:
            parent = f"mainbus_{letter_side.get(branch, bank_a)}"
        t.add_edge(parent, feedbus_id, None)  # bus tap - no separate breaker modeled here

        for idx in FEEDER_INDEX_RANGE:
            fx = FEEDER_X0 + (idx - 1) * FEEDER_STEP
            suffix = f"{bank_root}{branch}{idx}"
            vcb_node = f"vcb_{suffix}"
            t.add_node(vcb_node, fx, y_bus + 26)
            t.add_edge(feedbus_id, vcb_node, f"VCB_{suffix}_STATUS.value")

            ltr_node = f"ltr_{suffix}"
            t.add_node(ltr_node, fx, y_bus + 102)
            t.add_edge(vcb_node, ltr_node, None)

            acb_node = f"acb_{suffix}"
            t.add_node(acb_node, fx, y_bus + 155)
            t.add_edge(ltr_node, acb_node, f"ACB_{suffix}_STATUS.value")

    return t
