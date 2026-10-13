"""Generate a FULL interactive single-line-diagram .pnl for one BTR bank:
SVG background (visual, via gen_svg_diagram's exact coordinate math) +
one clickable switch_1.pnl reference per STATUS-bearing breaker, each wired
to its real DPE (<tag>_STATUS.value), positioned to match the SVG glyph.

Reuses:
  - The proven "RECTANGLE1 with SVG fill" panel skeleton (byte-identical to
    the shipped panels/about.pnl, only the size/svg filename differ).
  - The proven panel-REFERENCE block syntax (copied verbatim in structure
    from panels/objects/STD_SWITCHES/switch_1.pnl's own embedding of
    switch_1_main.pnl), reused once per breaker here.

Usage:
  python gen_interactive_panel.py --bank 3F11 \
      --svg-out "C:\\WinCC_OA_Proj\\CLI_TEST\\pictures" \
      --pnl-out "C:\\WinCC_OA_Proj\\CLI_TEST\\panels"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.topology.equipment_catalog import K_SPAN, Q_SPAN, FEEDER_BANKS, FEEDER_INDEX_RANGE  # noqa: E402
from gen_svg_diagram import build as build_svg, W  # noqa: E402

SWITCH_W, SWITCH_H = 40, 60  # switch_1.pnl's own native footprint we place at


def switch_ref(name: str, x: float, y: float, dpe: str) -> str:
    """One interactive breaker: switch_1.pnl reference wired to dpe (bool)."""
    return (
        f'3 1 "{name}" -1\n'
        f'"" ""\n'
        f'"objects/STD_SWITCHES/switch_1.pnl" {x:.0f} {y:.0f} T 1 U \n'
        f'5\n'
        f'"$b_IBit""FALSE"\n'
        f'"$b_Toggle""TRUE"\n'
        f'"$dpe_value_Off""{dpe}"\n'
        f'"$dpe_value_On""{dpe}"\n'
        f'"$dpe_value_Rm""{dpe}"\n'
        f'0\n'
    )


def collect_breakers(bank_root: str) -> list[tuple[str, float, float, str]]:
    """Returns (name, cx, cy, dpe) for every STATUS-bearing breaker, in the
    exact coordinate system gen_svg_diagram.build() draws in."""
    out: list[tuple[str, float, float, str]] = []

    xa, xb = W * 0.28, W * 0.72
    y_main = 140
    out.append(("sw_MAIN_A", xa, y_main + 22, f"VCB_{bank_root}A_STATUS.value"))
    out.append(("sw_MAIN_B", xb, y_main + 22, f"VCB_{bank_root}B_STATUS.value"))

    y_k = 230
    k_letters = K_SPAN.get(bank_root, {}).get("letters", [])
    if k_letters:
        kx0 = W * 0.5 - (len(k_letters) - 1) * 70 / 2
        for i, letter in enumerate(k_letters):
            kx = kx0 + i * 70
            out.append((f"sw_K_{letter}", kx, y_k + 22, f"VCB_{bank_root}{letter}K_STATUS.value"))

    y_q = 320
    q_letters = Q_SPAN.get(bank_root, {}).get("letters", [])
    if q_letters:
        qx0 = W * 0.5 - (len(q_letters) - 1) * 70 / 2
        for i, letter in enumerate(q_letters):
            qx = qx0 + i * 70
            out.append((f"sw_Q_{letter}", qx, y_q + 22, f"VCB_{bank_root}{letter}Q_STATUS.value"))

    y_feed_bus = 420
    branches = FEEDER_BANKS.get(bank_root, {}).get("branches", [])
    y_row_h = 220
    FEEDER_STEP = 130
    FEEDER_X0 = 140
    for bi, branch in enumerate(branches):
        y_bus = y_feed_bus + bi * y_row_h
        for idx in FEEDER_INDEX_RANGE:
            fx = FEEDER_X0 + (idx - 1) * FEEDER_STEP
            suffix = f"{bank_root}{branch}{idx}"
            out.append((f"sw_F_{suffix}", fx, y_bus + 30 + 22, f"VCB_{suffix}_STATUS.value"))
            out.append((f"sw_A_{suffix}", fx, y_bus + 165 + 10, f"ACB_{suffix}_STATUS.value"))

    return out


def build_pnl(bank_root: str, svg_filename: str) -> str:
    breakers = collect_breakers(bank_root)
    refs = "".join(
        switch_ref(name, cx - SWITCH_W / 2, cy - SWITCH_H / 2, dpe)
        for name, cx, cy, dpe in breakers
    )

    header = f"""V 14
3
LANG:10001 8 bank3F11
LANG:10000 8 bank3F11
LANG:10027 8 bank3F11
PANEL,-1 -1 {W} 950 N "_3DFace" 0
E E "main(int x, int y, mapping event)
{{
  PanelOff();
}}" 0
 E E 1 -1 -1 0  55 20
"refFileName"0  1
E E 4
"CBRef" "0"
"EClose" E
"dpi" "96"
"pdpi" "96"
0 0 0
""
NC
DISPLAY_LAYER, 1 0 1 0 1 0 1 0 1 0 1 0 1 0 1 0
LAYER, 0 
1
LANG:10001 0 
6 26
"RECTANGLE1"
""
1 0 0 E E E 1 E 1 E N {{14,32,100}} E N {{40,86,141,59}} E E
 E E
26 0 0 0 0 0
E E E
0
3
LANG:10001 0 
LANG:10000 0 
LANG:10027 0 

4
"transparentForMouse" ""
"layoutAlignment" "AlignNone"
"dashclr"N "_Transparent"
"antiAliased" "0"
E E -1 3 3 2 1 E 1 0 1 -1 0 2  1 0  "pictures/{svg_filename}" 4294967295 E 0 0 {W} 950
0
"""

    layers_1_to_7 = "".join(
        f"LAYER, {n} \n1\nLANG:10001 0 \n0\n" for n in range(1, 8)
    )

    return header + layers_1_to_7 + refs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="3F11")
    ap.add_argument("--svg-out", type=Path, required=True)
    ap.add_argument("--pnl-out", type=Path, required=True)
    args = ap.parse_args()

    bank_root = args.bank
    svg = build_svg(f"{bank_root}A", f"{bank_root}B")
    args.svg_out.mkdir(parents=True, exist_ok=True)
    svg_path = args.svg_out / f"bank_{bank_root}.svg"
    svg_path.write_text(svg, encoding="utf-8")

    pnl = build_pnl(bank_root, svg_path.name)
    args.pnl_out.mkdir(parents=True, exist_ok=True)
    pnl_path = args.pnl_out / f"bank_{bank_root}.pnl"
    pnl_path.write_text(pnl, encoding="utf-8")

    n_breakers = len(collect_breakers(bank_root))
    print(f"wrote {svg_path}")
    print(f"wrote {pnl_path} with {n_breakers} interactive switch references")


if __name__ == "__main__":
    main()
