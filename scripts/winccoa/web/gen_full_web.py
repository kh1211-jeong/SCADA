"""Full-plant SLD: EGMS's build_topology.py graph (connectivity ONLY, reused
verbatim - 277 nodes/317 edges) laid out with EGMS's own auto-layout
algorithm (layout.py, ported from sld_renderer.js), but drawn with the
breaker/transformer/instrument-box symbol language from the 8090 single-bank
screen (gen_web_svg.py v3) - NOT EGMS's generic circle nodes. Z-order and
energized/de-energized propagation follow the same rules as 8090:
  - lines drawn before symbols (clean junctions)
  - blue=energized / dark-gray=de-energized line color
  - breaker fill: green=closed+fed, gray=closed+no-feed, red=open
  - propagation = graph reachability from BUS_154kV through closed breakers
    only (server.js walks this every poll - see server_full2.js)

Usage:
  python gen_full_web.py --egms-path "..\\..\\..\\EGMS" \
      --out-dir "C:\\WinCC_OA_Proj\\SVR_TEST\\javascript\\web"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as layout_mod  # noqa: E402

BG = "#0b0e14"
LIVE = "#4a9dff"
DEAD = "#2a3040"
CLOSED = "#33d17a"
OPEN = "#e6553a"
NOPOWER = "#5a6478"
TIE_COLOR = "#f2c14e"
LABEL = "#dfe7f5"
DIM = "#6b7690"
BOX_BG = "#1a2130"
BOX_BORDER = "#3a4560"
BOX_TEXT = "#9fd8ff"
TRANSFORMER = "#dfe7f5"

BREAKER_TYPES = {"GCB", "MAIN", "VCB_K", "VCB_Q", "VCB_FEEDER", "VCB_STR", "VCB_CAP",
                  "ACB", "ACB_MAIN_EMG", "STR", "XCB"}
TRANSFORMER_TYPES = {"BTR", "LTR"}
TIE_TYPES = {"TIE", "DIS"}
DOT_TYPES = {"BUS", "RETURN", "VCS_CAP"}
ANALOG_TYPES = {"BTR", "MAIN", "VCB_FEEDER", "ACB", "ACB_MAIN_EMG", "GCB"}


def breaker_symbol(x: float, y: float, tag: str, node_id: str, label: str, w: float = 26, h: float = 40) -> str:
    x0, y0 = x - w / 2, y - h / 2
    return (
        f'<g class="sym" data-node="{node_id}">'
        f'<rect class="brk" data-tag="{tag}" data-node="{node_id}" x="{x0:.1f}" y="{y0:.1f}" width="{w}" height="{h}" rx="4" '
        f'fill="{OPEN}" stroke="#00000080" stroke-width="1.3"/>'
        f'<line x1="{x0+4:.1f}" y1="{y0+h-4:.1f}" x2="{x0+w-4:.1f}" y2="{y0+4:.1f}" stroke="#00000060" stroke-width="1.6" pointer-events="none"/>'
        f'<text x="{x:.1f}" y="{y0+h+12:.1f}" fill="{LABEL}" font-size="9" text-anchor="middle" font-family="Consolas,monospace">{label}</text>'
        f'</g>'
    )


def transformer_symbol(x: float, y: float, label: str, r: float = 14) -> str:
    return (
        f'<g class="sym">'
        f'<circle cx="{x:.1f}" cy="{y-r*0.5:.1f}" r="{r}" fill="{BG}" stroke="{TRANSFORMER}" stroke-width="1.6"/>'
        f'<circle cx="{x:.1f}" cy="{y+r*0.5:.1f}" r="{r}" fill="{BG}" stroke="{TRANSFORMER}" stroke-width="1.6"/>'
        f'<text x="{x:.1f}" y="{y+r*1.9:.1f}" fill="{LABEL}" font-size="9" text-anchor="middle" font-family="Consolas,monospace">{label}</text>'
        f'</g>'
    )


def tie_symbol(x: float, y: float, tag: str, node_id: str, label: str, w: float = 14, h: float = 14) -> str:
    return (
        f'<g class="sym" data-node="{node_id}">'
        f'<rect class="tie" data-tag="{tag}" data-node="{node_id}" x="{x-w/2:.1f}" y="{y-h/2:.1f}" width="{w}" height="{h}" rx="3" '
        f'fill="{OPEN}" stroke="#00000080"/>'
        f'<text x="{x:.1f}" y="{y-h/2-4:.1f}" fill="{DIM}" font-size="8" text-anchor="middle" font-family="Consolas,monospace">{label}</text>'
        f'</g>'
    )


def dot_symbol(x: float, y: float, label: str) -> str:
    return (f'<g class="sym"><circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{LIVE}"/>'
            f'<text x="{x:.1f}" y="{y-9:.1f}" fill="{DIM}" font-size="9" text-anchor="middle" font-family="Consolas,monospace">{label}</text></g>')


def instrument_box(x: float, y: float, node_id: str, tags: dict[str, str]) -> str:
    rows = list(tags.items())
    row_h = 11
    w = 74
    h = row_h * len(rows) + 4
    x0 = x - w / 2
    out = [f'<rect class="sym" x="{x0:.1f}" y="{y:.1f}" width="{w}" height="{h}" rx="2" fill="{BOX_BG}" stroke="{BOX_BORDER}"/>']
    for i, (unit, tag) in enumerate(rows):
        ry = y + 9 + i * row_h
        out.append(f'<text class="sym val" data-tag="{tag}" data-node="{node_id}" data-unit="{unit}" x="{x0+4:.1f}" y="{ry:.1f}" fill="{BOX_TEXT}" '
                    f'font-size="9" font-family="Consolas,monospace" style="cursor:pointer">--</text>')
        out.append(f'<text class="sym" x="{x0+w-4:.1f}" y="{ry:.1f}" fill="{DIM}" font-size="8" '
                    f'text-anchor="end" font-family="Consolas,monospace">{unit}</text>')
    return "".join(out)


def elbow_path(x1: float, y1: float, x2: float, y2: float) -> str:
    if abs(x1 - x2) < 1:
        return f"M {x1:.1f} {y1:.1f} L {x2:.1f} {y2:.1f}"
    mid_y = (y1 + y2) / 2
    return f"M {x1:.1f} {y1:.1f} L {x1:.1f} {mid_y:.1f} L {x2:.1f} {mid_y:.1f} L {x2:.1f} {y2:.1f}"


def build(egms_path: Path) -> tuple[str, dict, list[str], dict]:
    sys.path.insert(0, str(egms_path.resolve()))
    import build_topology as bt

    g = bt.gen_grid()
    node_by_id = {}
    nodes_json = []
    for e in g.equipment:
        level = bt.tie_level(e["name"]) if e["etype"] in ("TIE", "DIS") else bt.LEVEL.get(e["etype"], 10)
        n = {"id": e["name"], "etype": e["etype"], "level": level, "meta": e["meta"]}
        node_by_id[e["name"]] = n
        nodes_json.append(n)
    edges_json = [{"src": e["src"], "dst": e["dst"], "etype": e["etype"]} for e in g.edges]

    positions = layout_mod.compute_layout(nodes_json, edges_json)
    xs = [p[0] for p in positions.values()]
    ys = [p[1] for p in positions.values()]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    pad = 120
    W = maxx - minx + pad * 2
    H = maxy - miny + pad * 2

    def px(nid):
        x, y = positions[nid]
        return x - minx + pad, y - miny + pad

    status_tags: list[str] = []
    value_tags: list[str] = []
    lines: list[str] = []
    symbols: list[str] = []

    for e in edges_json:
        if e["src"] not in positions or e["dst"] not in positions:
            continue
        x1, y1 = px(e["src"])
        x2, y2 = px(e["dst"])
        dash = ' stroke-dasharray="4,3"' if e["etype"] in ("tie", "xtie", "xtie_cross") else ""
        lines.append(f'<path class="edge" data-edge-src="{e["src"]}" data-edge-dst="{e["dst"]}" '
                      f'd="{elbow_path(x1, y1, x2, y2)}" fill="none" stroke="{DEAD}" stroke-width="3"{dash}/>')

    for n in nodes_json:
        nid, etype = n["id"], n["etype"]
        x, y = px(nid)
        if etype in BREAKER_TYPES:
            tag = f"{nid}_STATUS.value"
            breaker_w = 22 if etype in ("XCB",) else 26
            symbols.append(breaker_symbol(x, y, tag, nid, nid, w=breaker_w))
            status_tags.append(tag)
            if etype in ANALOG_TYPES:
                symbols.append(instrument_box(x, y - 46, nid, {
                    "kW": f"{nid}_POWER.value", "A": f"{nid}_CURRENT.value",
                }))
                value_tags += [f"{nid}_POWER.value", f"{nid}_CURRENT.value"]
        elif etype in TRANSFORMER_TYPES:
            symbols.append(transformer_symbol(x, y, nid))
            if etype == "BTR":
                symbols.append(instrument_box(x, y - 46, nid, {"T": f"{nid}_TEMP.value", "L": f"{nid}_LOAD.value"}))
                value_tags += [f"{nid}_TEMP.value", f"{nid}_LOAD.value"]
        elif etype in TIE_TYPES:
            tag = f"{nid}_STATUS.value"
            symbols.append(tie_symbol(x, y, tag, nid, nid))
            status_tags.append(tag)
        else:
            symbols.append(dot_symbol(x, y, nid))

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" font-family="Consolas,monospace">']
    svg.append(f'<rect x="0" y="0" width="{W:.0f}" height="{H:.0f}" fill="{BG}"/>')
    svg.append('<g id="lines">' + "".join(lines) + "</g>")
    svg.append('<g id="symbols">' + "".join(symbols) + "</g>")
    svg.append("</svg>")

    import re as _re

    def _sys_of(nid: str) -> str:
        m = _re.search(r"3[FU]\d{2}", nid)
        return m.group(0) if m else ""

    pos_export = {n["id"]: list(px(n["id"])) for n in nodes_json if n["id"] in positions}
    systems = sorted({s for n in nodes_json if (s := _sys_of(n["id"]))})

    topo_export = {
        "canvas": {"w": W, "h": H},
        "positions": pos_export,
        "systems": systems,
        "nodes": [{"id": n["id"], "etype": n["etype"], "level": n["level"], "system": _sys_of(n["id"])} for n in nodes_json],
        "edges": edges_json,
        "root": next(n["id"] for n in nodes_json if n["level"] == 0),
    }
    return "\n".join(svg), topo_export, sorted(set(status_tags + value_tags)), node_by_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--egms-path", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    svg, topo, tags, _ = build(args.egms_path)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "full_diagram.svg").write_text(svg, encoding="utf-8")
    (args.out_dir / "full_topology.json").write_text(json.dumps(topo, indent=2), encoding="utf-8")
    (args.out_dir / "full_diagram.tags.json").write_text(json.dumps(tags, indent=2), encoding="utf-8")
    print(f"wrote full_diagram.svg ({len(svg)} bytes)")
    print(f"wrote full_topology.json ({len(topo['nodes'])} nodes, {len(topo['edges'])} edges)")
    print(f"wrote full_diagram.tags.json ({len(tags)} tags)")


if __name__ == "__main__":
    main()
