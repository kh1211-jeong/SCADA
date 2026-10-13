"""Auto X/Y layout for an arbitrary EGMS build_topology.py graph, ported
from EGMS's own static/js/sld_renderer.js computeLayout() (same algorithm,
Python instead of JS, so gen_full_web.py can compute positions once and
bake them into the generated SVG - see CLAUDE.md: reuse, don't reimplement,
the algorithm; only the language changed to fit this generator).
"""
from __future__ import annotations

import re

COL = 130
ROW = 170
SYS_GAP = 3


def _sys_of(node_id: str) -> str:
    m = re.search(r"3[FU]\d{2}", node_id)
    return m.group(0) if m else "ZZZ"


def compute_layout(nodes: list[dict], edges: list[dict]) -> dict[str, tuple[float, float]]:
    tree_edges = [e for e in edges if e["etype"] in ("power", "return")]
    children: dict[str, list[str]] = {}
    for e in tree_edges:
        children.setdefault(e["src"], []).append(e["dst"])

    lv = {n["id"]: n.get("level", 0) for n in nodes}
    systems = sorted({_sys_of(n["id"]) for n in nodes} - {"ZZZ"})
    sys_index = {s: i for i, s in enumerate(systems)}

    bus_node = next((n for n in nodes if n.get("level") == 0), nodes[0])
    bus_id = bus_node["id"]

    top_children = sorted(
        children.get(bus_id, []),
        key=lambda a: (sys_index.get(_sys_of(a), 99), a),
    )

    X: dict[str, float] = {}
    state = {"slot": 0, "last_sys": None}
    LINE_NUM_RE = re.compile(r"(?:^|[^A-Z])([A-Z])(\d+)X?$")

    def order(node_id: str) -> None:
        s = _sys_of(node_id)
        kids = list(children.get(node_id, []))

        def sort_key(a: str):
            m = LINE_NUM_RE.search(a)
            return (int(m.group(2)), m.group(1)) if m else (10**9, a)

        kids_with_pat = [k for k in kids if LINE_NUM_RE.search(k)]
        if len(kids_with_pat) == len(kids) and kids:
            kids.sort(key=sort_key)
        else:
            kids.sort()

        if not kids:
            if state["last_sys"] is not None and s != state["last_sys"]:
                state["slot"] += SYS_GAP
            state["last_sys"] = s
            X[node_id] = state["slot"] * COL
            state["slot"] += 1
            return
        for k in kids:
            order(k)
        xs = [X[k] for k in kids if k in X]
        X[node_id] = sum(xs) / len(xs) if xs else 0.0

    X[bus_id] = 0.0
    for c in top_children:
        order(c)
    xs = [X[c] for c in top_children if c in X]
    if xs:
        X[bus_id] = sum(xs) / len(xs)

    neighbor: dict[str, list[str]] = {}
    for e in edges:
        neighbor.setdefault(e["src"], []).append(e["dst"])
        neighbor.setdefault(e["dst"], []).append(e["src"])

    undecided = [n["id"] for n in nodes if n["id"] not in X]
    for nid in undecided:
        X[nid] = None  # type: ignore[assignment]

    for _ in range(8):
        changed = False
        for nid in undecided:
            nb = [X[n] for n in neighbor.get(nid, []) if X.get(n) is not None]
            if not nb:
                continue
            avg = sum(nb) / len(nb)
            if X[nid] != avg:
                X[nid] = avg
                changed = True
        if not changed:
            break
    for nid in undecided:
        if X[nid] is None:
            X[nid] = 0.0

    for nid in undecided:
        h = 0
        for ch in nid:
            h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        X[nid] += (h % 13) - 6

    return {n["id"]: (X.get(n["id"], 0.0), lv.get(n["id"], 0) * ROW) for n in nodes}
