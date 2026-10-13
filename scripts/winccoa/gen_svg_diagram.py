"""Generate a single-line-diagram SVG for one BTR bank, matching the visual
style of sample image/6.6_1.png (dark background, thick horizontal bus bars,
right-angle-only branch lines, red rectangle = breaker/CB glyph, green box =
TIE/bus-section, transformer = two overlapping circles labeled Y/D).

SVG is plain XML - this is the "XML panel content" route: a WinCC OA .pnl
wraps this file as a RECTANGLE fill pattern (the same mechanism already used
by the product's own panels/about.pnl -> pictures/about.svg), so we get a
real, correctly-rendered diagram without hand-serializing dozens of GEDI
objects in the fragile positional .pnl grammar.

Usage:
  python gen_svg_diagram.py --bank 3F11 --out-dir "C:\\WinCC_OA_Proj\\CLI_TEST\\pictures"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.topology.equipment_catalog import K_SPAN, Q_SPAN, FEEDER_BANKS, FEEDER_INDEX_RANGE  # noqa: E402

BG = "#12141a"
BUS_COLOR = "#3a6fd8"
BREAKER = "#d83a3a"
TIE_GREEN = "#3ad86a"
LABEL = "#c9d3e0"
DIM = "#5a6478"
TRANSFORMER_STROKE = "#c9d3e0"

W = 2200
FEEDER_STEP = 130
FEEDER_X0 = 140


def breaker(x: float, y: float, label: str, w: float = 26, h: float = 44) -> str:
    return (
        f'<rect x="{x - w/2:.1f}" y="{y:.1f}" width="{w}" height="{h}" fill="{BREAKER}" stroke="#000" stroke-width="1"/>'
        f'<text x="{x:.1f}" y="{y + h + 14:.1f}" fill="{LABEL}" font-size="11" text-anchor="middle" font-family="Consolas,monospace">{label}</text>'
    )


def tie_box(x: float, y: float, label: str, w: float = 16, h: float = 16) -> str:
    return (
        f'<rect x="{x - w/2:.1f}" y="{y:.1f}" width="{w}" height="{h}" fill="{TIE_GREEN}" stroke="#000" stroke-width="1"/>'
        f'<text x="{x:.1f}" y="{y - 6:.1f}" fill="{DIM}" font-size="9" text-anchor="middle" font-family="Consolas,monospace">{label}</text>'
    )


def transformer(x: float, y: float, label: str, r: float = 20) -> str:
    return (
        f'<circle cx="{x:.1f}" cy="{y - r*0.5:.1f}" r="{r}" fill="none" stroke="{TRANSFORMER_STROKE}" stroke-width="2"/>'
        f'<circle cx="{x:.1f}" cy="{y + r*0.5:.1f}" r="{r}" fill="none" stroke="{TRANSFORMER_STROKE}" stroke-width="2"/>'
        f'<text x="{x:.1f}" y="{y + r*1.8:.1f}" fill="{LABEL}" font-size="11" text-anchor="middle" font-family="Consolas,monospace">{label}</text>'
    )


def vline(x: float, y1: float, y2: float) -> str:
    return f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}" stroke="{BUS_COLOR}" stroke-width="2"/>'


def hbus(x1: float, x2: float, y: float, w: float = 6) -> str:
    return f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" stroke="{BUS_COLOR}" stroke-width="{w}"/>'


def text(x: float, y: float, s: str, size: int = 13, anchor: str = "middle", color: str = LABEL) -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}" font-size="{size}" text-anchor="{anchor}" font-family="Consolas,monospace">{s}</text>'


def build(bank_a: str, bank_b: str) -> str:
    """bank_a/bank_b: e.g. '3F11A','3F11B' - the two BTR halves of one bank."""
    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} 950" font-family="Consolas,monospace">')
    parts.append(f'<rect x="0" y="0" width="{W}" height="950" fill="{BG}"/>')

    # -- Row 1: BTR (bank transformers) --
    y_btr = 40
    for bx, name in ((W * 0.28, bank_a), (W * 0.72, bank_b)):
        parts.append(transformer(bx, y_btr, f"BTR_{name} OLTC"))
        parts.append(vline(bx, y_btr + 45, 120))

    # -- Row 2: MAIN VCB + bank tie --
    y_main = 140
    xa, xb = W * 0.28, W * 0.72
    parts.append(breaker(xa, y_main, f"VCB_{bank_a}"))
    parts.append(breaker(xb, y_main, f"VCB_{bank_b}"))
    parts.append(hbus(xa, xb, y_main + 22))
    xtie = (xa + xb) / 2
    parts.append(tie_box(xtie, y_main + 14, f"TIE_{bank_a}{bank_b[-1]}A"))
    parts.append(vline(xa, y_main + 44, 230))
    parts.append(vline(xb, y_main + 44, 230))

    # -- Row 3: K-span --
    bank_root = bank_a[:-1]  # e.g. "3F11"
    y_k = 230
    k_letters = K_SPAN.get(bank_root, {}).get("letters", [])
    if k_letters:
        kx0 = W * 0.5 - (len(k_letters) - 1) * 70 / 2
        prev_x = None
        for i, letter in enumerate(k_letters):
            kx = kx0 + i * 70
            parts.append(breaker(kx, y_k, f"VCB_{bank_root}{letter}K"))
            if prev_x is not None:
                parts.append(hbus(prev_x, kx, y_k - 10, w=3))
            prev_x = kx
        parts.append(vline(W * 0.5, y_k + 44, 320))

    # -- Row 4: Q-span --
    y_q = 320
    q_letters = Q_SPAN.get(bank_root, {}).get("letters", [])
    if q_letters:
        qx0 = W * 0.5 - (len(q_letters) - 1) * 70 / 2
        for i, letter in enumerate(q_letters):
            qx = qx0 + i * 70
            parts.append(breaker(qx, y_q, f"VCB_{bank_root}{letter}Q"))

    # -- Row 5+: Feeders, one horizontal strip per branch, each with LTR + ACB below --
    y_feed_bus = 420
    branches = FEEDER_BANKS.get(bank_root, {}).get("branches", [])
    y_row_h = 220
    for bi, branch in enumerate(branches):
        y_bus = y_feed_bus + bi * y_row_h
        x_start = FEEDER_X0
        x_end = FEEDER_X0 + (len(list(FEEDER_INDEX_RANGE)) - 1) * FEEDER_STEP
        parts.append(hbus(x_start, x_end, y_bus))
        parts.append(text(30, y_bus + 5, f"{bank_root}{branch}", anchor="start", size=14, color=BUS_COLOR))
        for idx in FEEDER_INDEX_RANGE:
            fx = FEEDER_X0 + (idx - 1) * FEEDER_STEP
            suffix = f"{bank_root}{branch}{idx}"
            parts.append(vline(fx, y_bus, y_bus + 30))
            parts.append(breaker(fx, y_bus + 30, f"VCB_{suffix}", w=20, h=30))
            parts.append(vline(fx, y_bus + 60, y_bus + 90))
            parts.append(transformer(fx, y_bus + 110, f"LTR_{suffix}", r=14))
            parts.append(vline(fx, y_bus + 145, y_bus + 165))
            parts.append(breaker(fx, y_bus + 165, f"ACB_{suffix}", w=16, h=20))

    parts.append(
        text(W / 2, 920, "SYNTHETIC LAYOUT - generated from src/topology/equipment_catalog.py - not a surveyed drawing", size=11, color=DIM)
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="3F11", help="bank root, e.g. 3F11")
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()

    svg = build(f"{args.bank}A", f"{args.bank}B")
    out = args.out_dir / f"bank_{args.bank}.svg"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
