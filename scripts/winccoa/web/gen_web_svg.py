"""Generate the web-interactive single-line-diagram SVG for one BTR bank, v3:
real topology-driven rendering (see topology.py) instead of independently
positioned symbols.

Fixes vs v2, per direct user feedback on v2's screenshot:
  1. line/symbol junctions were sloppy -> lines now route via topology.py's
     node graph and terminate exactly at each symbol's anchor point.
  2. lines drew OVER symbols -> lines group is emitted before the symbols
     group in the SVG, so opaque symbols correctly occlude the line ends.
  3. lines didn't change with breaker state -> every line segment carries
     data-edge-id; the client (server.js/index page JS) recolors each
     edge live/dead every poll based on server-computed graph reachability
     (see topology.py's Topology + server.js's energization walk).
  4. MAIN/K/Q/Feeder breakers weren't actually connected -> they now are,
     via topology.py's real parent/child edges (MAIN bus -> K/Q taps ->
     feeder bus -> feeder VCB -> LTR -> ACB).
  5. turning a breaker off deenergizes everything downstream -> that's
     exactly what the graph-reachability walk in server.js computes; this
     file just needs to expose the same node/edge ids the topology graph
     uses so client-side coloring can key off them.

Usage:
  python gen_web_svg.py --bank 3F11 --out "C:\\WinCC_OA_Proj\\SVR_TEST\\javascript\\web\\diagram.svg"
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.topology.equipment_catalog import K_SPAN, Q_SPAN, FEEDER_BANKS, FEEDER_INDEX_RANGE  # noqa: E402
import topology  # noqa: E402

BG = "#0b0e14"
LIVE = "#4a9dff"
LIVE_GLOW = "#4a9dff55"
DEAD = "#2a3040"
CLOSED = "#33d17a"
OPEN = "#e6553a"
TIE = "#f2c14e"
LABEL = "#dfe7f5"
DIM = "#6b7690"
BOX_BG = "#1a2130"
BOX_BORDER = "#3a4560"
BOX_TEXT = "#9fd8ff"
TRANSFORMER = "#dfe7f5"
HEADER_BG = "#141824"

W = topology.W
H = 1020


def defs() -> str:
    return """
<defs>
  <linearGradient id="brkGrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.25"/>
    <stop offset="0.5" stop-color="#ffffff" stop-opacity="0"/>
  </linearGradient>
  <pattern id="dots" width="28" height="28" patternUnits="userSpaceOnUse">
    <circle cx="1" cy="1" r="1" fill="#1c2333"/>
  </pattern>
</defs>
"""


def header(bank_root: str) -> str:
    return f"""
<rect x="0" y="0" width="{W}" height="46" fill="{HEADER_BG}"/>
<rect x="0" y="45" width="{W}" height="1" fill="{BOX_BORDER}"/>
<text x="24" y="30" fill="{LABEL}" font-size="20" font-weight="700" font-family="Segoe UI,Consolas,sans-serif">{bank_root} BANK - SINGLE LINE DIAGRAM</text>
<g font-family="Consolas,monospace" font-size="12">
  <line x1="1440" y1="23" x2="1470" y2="23" stroke="{LIVE}" stroke-width="4"/>
  <text x="1478" y="27" fill="{DIM}">ENERGIZED</text>
  <line x1="1590" y1="23" x2="1620" y2="23" stroke="{DEAD}" stroke-width="4"/>
  <text x="1628" y="27" fill="{DIM}">DE-ENERGIZED</text>
  <rect x="1770" y="16" width="14" height="14" fill="{CLOSED}" rx="2"/>
  <text x="1790" y="27" fill="{DIM}">CLOSED</text>
  <rect x="1880" y="16" width="14" height="14" fill="{OPEN}" rx="2"/>
  <text x="1900" y="27" fill="{DIM}">OPEN</text>
</g>
<text x="{W - 24}" y="30" fill="{DIM}" font-size="12" text-anchor="end" font-family="Consolas,monospace" id="clock">--:--:--</text>
"""


def breaker_symbol(x: float, y: float, tag: str, label: str, w: float = 28, h: float = 46) -> str:
    x0, y0 = x - w / 2, y - h / 2
    return f"""
<g class="sym">
  <rect class="brk" data-tag="{tag}" x="{x0:.1f}" y="{y0:.1f}" width="{w}" height="{h}" rx="4"
        fill="{CLOSED}" stroke="#00000080" stroke-width="1.5"/>
  <rect x="{x0:.1f}" y="{y0:.1f}" width="{w}" height="{h/2:.1f}" rx="4" fill="url(#brkGrad)" pointer-events="none"/>
  <line x1="{x0+4:.1f}" y1="{y0+h-4:.1f}" x2="{x0+w-4:.1f}" y2="{y0+4:.1f}" stroke="#00000060" stroke-width="2" pointer-events="none"/>
  <text x="{x:.1f}" y="{y0 + h + 15:.1f}" fill="{LABEL}" font-size="11" text-anchor="middle" font-family="Consolas,monospace">{label}</text>
</g>"""


def bus_tap_symbol(x: float, y: float) -> str:
    """Small solid dot marking a pure bus-tap node (no breaker of its own)."""
    return f'<circle class="sym" cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{LIVE}"/>'


def transformer_symbol(x: float, y: float, label: str, r: float = 20) -> str:
    return f"""
<g class="sym">
  <circle cx="{x:.1f}" cy="{y - r*0.5:.1f}" r="{r}" fill="{BG}" stroke="{TRANSFORMER}" stroke-width="2"/>
  <circle cx="{x:.1f}" cy="{y + r*0.5:.1f}" r="{r}" fill="{BG}" stroke="{TRANSFORMER}" stroke-width="2"/>
  <text x="{x:.1f}" y="{y + r*1.9:.1f}" fill="{LABEL}" font-size="11" text-anchor="middle" font-family="Consolas,monospace">{label}</text>
</g>"""


def instrument_box(x: float, y: float, tags: dict[str, str], compact: bool = False) -> str:
    rows = list(tags.items())
    row_h = 13 if compact else 15
    w = 92 if compact else 108
    h = row_h * len(rows) + 6
    x0 = x - w / 2
    out = [f'<rect class="sym" x="{x0:.1f}" y="{y:.1f}" width="{w}" height="{h}" rx="3" fill="{BOX_BG}" stroke="{BOX_BORDER}"/>']
    for i, (unit, tag) in enumerate(rows):
        ry = y + 12 + i * row_h
        out.append(f'<text class="sym val" data-tag="{tag}" data-unit="{unit}" x="{x0+6:.1f}" y="{ry:.1f}" fill="{BOX_TEXT}" '
                    f'font-size="{11 if compact else 12}" font-family="Consolas,monospace" style="cursor:pointer">--</text>')
        out.append(f'<text class="sym" x="{x0+w-6:.1f}" y="{ry:.1f}" fill="{DIM}" font-size="{9 if compact else 10}" '
                    f'text-anchor="end" font-family="Consolas,monospace">{unit}</text>')
    return "".join(out)


def edge_line(edge: "topology.Edge", nodes: dict[str, "topology.Node"]) -> str:
    """Right-angle route from parent to child, tagged with the edge id so
    the client can recolor it live/dead. Occluded cleanly at both ends by
    the opaque symbols drawn afterwards, since endpoints sit at node centers."""
    a, b = nodes[edge.frm], nodes[edge.to]
    path = f"M {a.x:.1f} {a.y:.1f}"
    if abs(a.x - b.x) > 1:
        mid_y = a.y + (b.y - a.y) * 0.5
        path += f" L {a.x:.1f} {mid_y:.1f} L {b.x:.1f} {mid_y:.1f} L {b.x:.1f} {b.y:.1f}"
    else:
        path += f" L {b.x:.1f} {b.y:.1f}"
    return (f'<path class="edge" data-edge="{edge.id}" d="{path}" fill="none" '
            f'stroke="{DEAD}" stroke-width="5" stroke-linejoin="round"/>')


def build(bank_root: str) -> tuple[str, list[str], "topology.Topology"]:
    topo = topology.build(bank_root)
    bank_a, bank_b = f"{bank_root}A", f"{bank_root}B"
    status_tags: list[str] = []
    value_tags: list[str] = []

    lines: list[str] = [edge_line(e, topo.nodes) for e in topo.edges]
    symbols: list[str] = []

    for bx, name in ((topo.nodes[f"src_{bank_a}"].x, bank_a), (topo.nodes[f"src_{bank_b}"].x, bank_b)):
        n = topo.nodes[f"src_{bank_a}" if name == bank_a else f"src_{bank_b}"]
        symbols.append(transformer_symbol(n.x, n.y, f"BTR_{name} OLTC"))

    for name in (bank_a, bank_b):
        n = topo.nodes[f"mainbus_{name}"]
        tag = f"VCB_{name}_STATUS.value"
        symbols.append(breaker_symbol(n.x, n.y, tag, f"VCB_{name}"))
        symbols.append(instrument_box(n.x, n.y - 105, {
            "kW": f"VCB_{name}_POWER.value", "V": f"VCB_{name}_VOLTAGE.value",
            "A": f"VCB_{name}_CURRENT.value", "PF": f"VCB_{name}_PF.value",
        }))
        status_tags.append(tag)
        value_tags += [f"VCB_{name}_POWER.value", f"VCB_{name}_VOLTAGE.value", f"VCB_{name}_CURRENT.value", f"VCB_{name}_PF.value"]

    tie_n_a = topo.nodes[f"mainbus_{bank_a}"]
    tie_n_b = topo.nodes[f"mainbus_{bank_b}"]
    tie_tag = f"TIE_{bank_root}BA_STATUS.value"
    symbols.append(f'<g class="sym"><rect class="tie" data-tag="{tie_tag}" x="{(tie_n_a.x+tie_n_b.x)/2-9:.1f}" '
                    f'y="{tie_n_a.y-9:.1f}" width="18" height="18" rx="3" fill="{TIE}" stroke="#00000080"/></g>')
    status_tags.append(tie_tag)

    k_letters = K_SPAN.get(bank_root, {}).get("letters", [])
    for letter in k_letters:
        n = topo.nodes[f"k_{letter}"]
        tag = f"VCB_{bank_root}{letter}K_STATUS.value"
        symbols.append(breaker_symbol(n.x, n.y, tag, f"{bank_root}{letter}K", w=24, h=38))
        status_tags.append(tag)

    q_letters = Q_SPAN.get(bank_root, {}).get("letters", [])
    for letter in q_letters:
        n = topo.nodes[f"q_{letter}"]
        tag = f"VCB_{bank_root}{letter}Q_STATUS.value"
        symbols.append(breaker_symbol(n.x, n.y, tag, f"{bank_root}{letter}Q", w=24, h=38))
        status_tags.append(tag)

    branches = FEEDER_BANKS.get(bank_root, {}).get("branches", [])
    for branch in branches:
        fb = topo.nodes[f"feedbus_{bank_root}{branch}"]
        symbols.append(bus_tap_symbol(fb.x, fb.y))
        lines.append(f'<path class="edge" data-edge="feedbus_label_{branch}" d="M {fb.x-300:.1f} {fb.y:.1f} L {fb.x+300:.1f} {fb.y:.1f}" '
                      f'fill="none" stroke="{DEAD}" stroke-width="5"/>')
        symbols.append(f'<text x="30" y="{fb.y+5:.1f}" fill="{LIVE}" font-size="15" font-weight="700" '
                        f'text-anchor="start" font-family="Consolas,monospace">{bank_root}{branch}</text>')

        for idx in FEEDER_INDEX_RANGE:
            suffix = f"{bank_root}{branch}{idx}"
            vn = topo.nodes[f"vcb_{suffix}"]
            vcb_tag = f"VCB_{suffix}_STATUS.value"
            cur_tag = f"VCB_{suffix}_CURRENT.value"
            pow_tag = f"VCB_{suffix}_POWER.value"
            symbols.append(breaker_symbol(vn.x, vn.y, vcb_tag, f"F{idx}", w=20, h=28))
            symbols.append(instrument_box(vn.x, vn.y - 55, {"kW": pow_tag, "A": cur_tag}, compact=True))
            status_tags.append(vcb_tag)
            value_tags += [cur_tag, pow_tag]

            ln = topo.nodes[f"ltr_{suffix}"]
            symbols.append(transformer_symbol(ln.x, ln.y, f"LTR{idx}", r=13))

            an = topo.nodes[f"acb_{suffix}"]
            acb_tag = f"ACB_{suffix}_STATUS.value"
            symbols.append(breaker_symbol(an.x, an.y, acb_tag, f"ACB{idx}", w=16, h=20))
            status_tags.append(acb_tag)

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Consolas,monospace">']
    svg.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="{BG}"/>')
    svg.append(f'<rect x="0" y="46" width="{W}" height="{H-46}" fill="url(#dots)"/>')
    svg.append(defs())
    svg.append(header(bank_root))
    svg.append('<g id="lines">' + "".join(lines) + "</g>")
    svg.append('<g id="symbols">' + "".join(symbols) + "</g>")
    svg.append(f'<text x="{W/2:.1f}" y="{H-14}" fill="{DIM}" font-size="11" text-anchor="middle" '
                f'font-family="Consolas,monospace">SYNTHETIC LAYOUT - src/topology/equipment_catalog.py - {bank_root} - not a surveyed drawing</text>')
    svg.append("</svg>")
    return "\n".join(svg), status_tags + value_tags, topo


def topology_to_json(topo: "topology.Topology") -> dict:
    return {
        "nodes": {nid: {"x": n.x, "y": n.y} for nid, n in topo.nodes.items()},
        "edges": [asdict(e) for e in topo.edges],
        "sources": topo.sources,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="3F11")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    svg, tags, topo = build(args.bank)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(svg, encoding="utf-8")
    args.out.with_suffix(".tags.json").write_text(json.dumps(sorted(set(tags)), indent=2), encoding="utf-8")
    args.out.with_name("topology.json").write_text(json.dumps(topology_to_json(topo), indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    print(f"wrote {args.out.with_suffix('.tags.json')} ({len(set(tags))} tags)")
    print(f"wrote {args.out.with_name('topology.json')} ({len(topo.nodes)} nodes, {len(topo.edges)} edges)")


if __name__ == "__main__":
    main()
