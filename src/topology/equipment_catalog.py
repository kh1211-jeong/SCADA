"""Rule-based FMCS equipment/tag catalog.

Source of truth: the naming rule in README.md section 2 + the five SCADA
screen captures in `sample image/` (154k_1.png, 154k_2.png, 6.6_1.png,
6.6_2.png, 6.6_3.png), read 2026-09-28.

This module does NOT invent equipment. Every group below is either:
  - CONFIRMED: the DP/label text is directly legible in one of the five
    screenshots (cited in `source`).
  - INFERRED: not directly legible, but implied with reasonable confidence
    by the plant's own repeating pattern (e.g. every BTR bank must feed a
    MAIN VCB, so if BTR_3F13A/B exist the MAIN VCBs likely do too).

`confidence` on every EquipmentGroup lets downstream code (or a human)
filter to "only what's been visually verified" vs "everything the rule
would predict". Treat this file as a draft topology to be reconciled
against TN_CM_EQP once the real FMCS extract lands - see README.md 3.1.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 3.3 applicable-quantity table (README.md / SKILL_winccoa.md, unchanged)
# ---------------------------------------------------------------------------
# PF is signed: -99..99. Sign encodes leading(진상)/lagging(지상) power
# factor, not just magnitude - confirmed on screen (e.g. "GCB-3A3M ... -99
# PF", "BTR 3F11AQ ... -99 PF"). Any physical-residual feature that uses PF
# must keep the sign (resid = P - sqrt(3)*V*I*(PF/100)), not abs(PF).
QTY_UNIT = {
    "CURRENT": "A",
    "VOLTAGE": "kV_or_V",   # kV at 154kV/6.6kV level, V at 220V level
    "POWER": "kW_or_MW",
    "REACTIVE": "kVAR",
    "PF": "%",              # signed, -99..99: sign = leading/lagging
    "STATUS": "0/1",
    "TAP": "step",
    "TEMP": "C",
    "LOAD": "%",
}

APPLICABLE_QUANTITIES = {
    "GCB": ["CURRENT", "VOLTAGE", "POWER", "PF", "STATUS"],
    "BTR": ["POWER", "VOLTAGE", "CURRENT", "PF", "TAP", "TEMP", "LOAD", "STATUS"],
    "VCB": ["CURRENT", "VOLTAGE", "POWER", "PF", "STATUS"],
    "LTR": ["POWER", "VOLTAGE", "CURRENT", "PF", "TEMP", "LOAD"],
    "ACB": ["CURRENT", "VOLTAGE", "POWER", "PF", "STATUS"],
    "TIE": ["STATUS"],       # TIE may optionally also carry CURRENT
    "DIS": ["STATUS"],
    "ECB": ["STATUS"],       # tie/emergency breaker between feeder branches (6.6_3.png)
    "BUS": [],                # topology node only, no direct tag in these captures


}


@dataclass
class EquipmentGroup:
    prefix: str                 # GCB / BTR / VCB / LTR / ACB / TIE / DIS / ECB / BUS
    name: str                   # DP name, underscore form, e.g. "GCB_3A1A"
    label: str                  # screen label, e.g. "GCB-3A1A"
    level: str                  # "154kV" / "6.6kV" / "220V"
    role: str                   # free-text role for the topology graph
    confidence: str             # "confirmed" | "inferred"
    source: str                 # which screenshot / rule justifies it
    quantities: list[str] = field(default_factory=list)  # override APPLICABLE_QUANTITIES[prefix] if set


def _std_quantities(prefix: str) -> list[str]:
    return list(APPLICABLE_QUANTITIES[prefix])


# ---------------------------------------------------------------------------
# 154kV GIS (GCB) - confirmed bus-group / stage sets from 154k_1.png, 154k_2.png
# ---------------------------------------------------------------------------
# stage set per bus group as actually legible on screen. Gaps (e.g. 3A3/3A4
# missing "B", 3B4 missing entirely) are left as gaps, not filled by symmetry.
GIS_GROUPS: dict[str, dict] = {
    "3A1": {"stages": ["A", "M", "B"], "source": "154k_1.png"},
    "3A2": {"stages": ["A", "M", "B"], "source": "154k_1.png + 154k_2.png"},
    "3A3": {"stages": ["A", "M"], "source": "154k_1.png + 154k_2.png (no B observed)"},
    "3A4": {"stages": ["A", "M"], "source": "154k_2.png (T/L incoming bay, no B observed)"},
    "3A5": {"stages": ["A", "M", "B"], "source": "154k_2.png"},
    "3B1": {"stages": ["M", "B"], "source": "154k_1.png (A not captured in crop, plausible by symmetry but not confirmed)"},
    "3B2": {"stages": ["A", "M", "B"], "source": "154k_2.png"},
    "3B3": {"stages": ["M", "B"], "source": "154k_2.png (A not observed)"},
    "3B5": {"stages": ["A", "M", "B"], "source": "154k_2.png"},
    # 3B4: not observed in any capture - intentionally omitted, not a confirmed gap.
}

GIS_TIES = [
    ("TIE_3ABB1", "TIE-3ABB1", "154k_1.png"),
    ("TIE_3ABA1", "TIE-3ABA1", "154k_1.png"),
]

# External utility transmission-line interconnection flags (P3-P2 EMG T/L,
# P3-V2 EMG T/L, "고덕2-삼성P3#1 T/L", P3P2/P3P4 EMG T/L) are visible on the
# 154kV screens but are upstream-utility permissive/status indicators, not
# plant EQP_NAME-style tags. Deliberately excluded from tag generation.


# ---------------------------------------------------------------------------
# BTR (bank transformers) - all 8 banks confirmed (bottom strip, 154k_1/2 +
# OLTC boxes in 6.6_2/6.6_3 for 3F11B/3F12A/3F12B individually)
# ---------------------------------------------------------------------------
BTR_BANKS = ["3F11A", "3F11B", "3F12A", "3F12B", "3F13A", "3F13B", "3F14A", "3F14B"]

# ---------------------------------------------------------------------------
# 6.6kV MAIN VCB - one per BTR bank. 3F11A/B fully confirmed (6.6_1.png),
# 3F12A/B partially confirmed (6.6_2/6.6_3.png), 3F13/3F14 inferred (every
# BTR bank observed feeds a MAIN VCB elsewhere - not itself photographed).
# ---------------------------------------------------------------------------
MAIN_VCB_CONFIDENCE = {
    "3F11A": "confirmed", "3F11B": "confirmed",
    "3F12A": "confirmed", "3F12B": "confirmed",
    "3F13A": "inferred", "3F13B": "inferred",
    "3F14A": "inferred", "3F14B": "inferred",
}

# Bank-internal bus tie/DIS pairs (confirmed labels)
MAIN_TIES = [
    ("DIS_3F11AB", "DIS 3F11AB", "confirmed", "6.6_1.png"),
    ("TIE_3F11BA", "TIE 3F11BA", "confirmed", "6.6_1.png"),
    ("TIE_3F112", "TIE 3F11'2'", "confirmed", "6.6_2.png (bank-to-bank tie, screen label literally '3F112')"),
    ("DIS_3F12AB", "DIS 3F12AB", "confirmed", "6.6_2.png"),
    ("TIE_3F12BA", "TIE 3F12BA", "confirmed", "6.6_2.png"),
    ("DIS_3F11AD", "DIS 3F11AD", "confirmed", "6.6_1.png (isolated/open disconnector)"),
]

# K-span / Q-span breakers per bank. NOT a uniform A-D rule: 3F11 and 3F12
# use DIFFERENT letter ranges for their K-span (plant-wide sequential
# lettering, not per-bank-reset), confirmed on screen.
K_SPAN = {
    "3F11": {"letters": ["A", "B", "C", "D"], "confidence": "confirmed", "source": "6.6_1.png"},
    "3F12": {"letters": ["C", "D", "E", "F"], "confidence": "confirmed", "source": "6.6_2.png + 6.6_3.png"},
}
Q_SPAN = {
    "3F11": {"letters": ["A", "C"], "confidence": "confirmed", "source": "6.6_1.png (B/D not observed, may exist)"},
    "3F12": {"letters": [], "confidence": "inferred", "source": "pattern implied by 3F11, exact letters unconfirmed"},
}

# Bus-segment nodes at the K-span (topology only, no direct tag)
K_SPAN_BUSES = [
    ("BUS_3US1AK", "3US1AK", "confirmed", "6.6_1.png"),
    ("BUS_3US1CK", "3US1CK", "confirmed", "6.6_1.png"),
]

# Feeders: per-bank branch letters x index 1..15. 3F11's A/C branches fully
# confirmed across 6.6_1/6.6_2/6.6_3 (A1-A15, C1-C15, plus spare AC/CC).
# 3F12's B/D branches follow the SKILL_winccoa.md convention but were not
# themselves captured on screen - inferred.
FEEDER_BANKS = {
    "3F11": {"branches": ["A", "C"], "spare": ["AC", "CC"], "confidence": "confirmed", "source": "6.6_1/6.6_2/6.6_3.png"},
    "3F12": {"branches": ["B", "D"], "spare": [], "confidence": "inferred", "source": "SKILL_winccoa.md convention, not photographed"},
}
FEEDER_INDEX_RANGE = range(1, 16)  # 1..15, confirmed by A15/C15 visible in 6.6_2/6.6_3

# ECB tie breakers between feeder branch groups at 220V (new prefix, not in
# the original SKILL_winccoa.md table - confirmed 6.6_3.png)
ECB_TIES = [
    ("ECB_3F11AC", "ECB-3F11AC(ATO)", "confirmed", "6.6_3.png"),
    ("ECB_3F11BC", "ECB-3F11BC", "confirmed", "6.6_3.png"),
]

# LTR/ACB are 1:1 with each feeder (LTR = feeder's mold transformer, ACB =
# its 220V output breaker). LTR temp: screen shows exactly 2 points, labeled
# (C) and (W) - NOT 3 as SKILL_winccoa.md originally assumed.
LTR_TEMP_POINTS = ["C", "W"]  # was assumed to be 3 points; correct to 2 per 6.6_3.png


def build_equipment() -> list[EquipmentGroup]:
    eqs: list[EquipmentGroup] = []

    # --- 154kV GIS ---
    for bus, info in GIS_GROUPS.items():
        for stage in info["stages"]:
            name = f"GCB_{bus}{stage}"
            label = f"GCB-{bus}{stage}"
            eqs.append(EquipmentGroup(
                "GCB", name, label, "154kV", "gis_breaker",
                "confirmed", info["source"],
            ))
    for name, label, source in GIS_TIES:
        eqs.append(EquipmentGroup("TIE", name, label, "154kV", "gis_bus_tie", "confirmed", source))

    # --- BTR ---
    for bank in BTR_BANKS:
        eqs.append(EquipmentGroup(
            "BTR", f"BTR_{bank}", f"{bank} OLTC", "154kV/6.6kV", "bank_transformer",
            "confirmed", "154k_1/154k_2 bottom strip + 6.6_2/6.6_3 OLTC boxes",
        ))

    # --- MAIN VCB ---
    for bank, conf in MAIN_VCB_CONFIDENCE.items():
        eqs.append(EquipmentGroup(
            "VCB", f"VCB_{bank}", f"MAIN VCB {bank}", "6.6kV", "main_vcb",
            conf, "6.6_1.png" if conf == "confirmed" and bank.startswith("3F11") else
                  "6.6_2/6.6_3.png" if conf == "confirmed" else
                  "inferred: BTR bank exists, MAIN VCB not itself photographed",
        ))
    for name, label, conf, source in MAIN_TIES:
        prefix = "DIS" if name.startswith("DIS") else "TIE"
        eqs.append(EquipmentGroup(prefix, name, label, "6.6kV", "bank_bus_tie", conf, source))

    # --- K-span / Q-span ---
    for bank, info in K_SPAN.items():
        for letter in info["letters"]:
            name = f"VCB_{bank}{letter}K"
            eqs.append(EquipmentGroup(
                "VCB", name, name.replace("_", " "), "6.6kV", "k_span",
                info["confidence"], info["source"],
            ))
    for bank, info in Q_SPAN.items():
        for letter in info["letters"]:
            name = f"VCB_{bank}{letter}Q"
            eqs.append(EquipmentGroup(
                "VCB", name, name.replace("_", " "), "6.6kV", "q_span",
                info["confidence"], info["source"],
            ))
    for name, label, conf, source in K_SPAN_BUSES:
        eqs.append(EquipmentGroup("BUS", name, label, "6.6kV", "k_span_bus", conf, source))

    # --- Feeders + LTR + ACB ---
    for bank, info in FEEDER_BANKS.items():
        for branch in info["branches"]:
            for idx in FEEDER_INDEX_RANGE:
                suffix = f"{bank}{branch}{idx}"
                eqs.append(EquipmentGroup(
                    "VCB", f"VCB_{suffix}", f"VCB {suffix}", "6.6kV", "feeder",
                    info["confidence"], info["source"],
                ))
                eqs.append(EquipmentGroup(
                    "LTR", f"LTR_{suffix}", f"LTR {suffix}", "6.6kV/220V", "mold_transformer",
                    info["confidence"], info["source"],
                ))
                eqs.append(EquipmentGroup(
                    "ACB", f"ACB_{suffix}", f"ACB {suffix}", "220V", "acb_output",
                    "inferred", "ACB_ naming convention from SKILL_winccoa.md; no legible ACB label on screen, only value boxes",
                ))
        for spare in info["spare"]:
            name = f"VCB_{bank}{spare}"
            eqs.append(EquipmentGroup(
                "VCB", name, name.replace("_", " "), "6.6kV", "feeder_spare",
                info["confidence"], info["source"],
            ))

    # --- ECB ties ---
    for name, label, conf, source in ECB_TIES:
        eqs.append(EquipmentGroup("ECB", name, label, "220V", "feeder_branch_tie", conf, source))

    return eqs


def build_tags(equipment: list[EquipmentGroup] | None = None) -> list[dict]:
    """Expand (equipment x applicable quantity) into individual DP/tag rows,
    matching the real FMCS convention EQP_NAME_QUANTITY (e.g. VCB_3F11A10_CURRENT).
    """
    equipment = equipment if equipment is not None else build_equipment()
    rows: list[dict] = []
    for eq in equipment:
        qtys = eq.quantities or _std_quantities(eq.prefix)
        for q in qtys:
            if eq.prefix == "LTR" and q == "TEMP":
                for point in LTR_TEMP_POINTS:
                    rows.append({
                        "tag": f"{eq.name}_{q}_{point}",
                        "eqp_name": eq.name,
                        "label": eq.label,
                        "prefix": eq.prefix,
                        "quantity": q,
                        "temp_point": point,
                        "level": eq.level,
                        "role": eq.role,
                        "confidence": eq.confidence,
                        "source": eq.source,
                        "dtype": "BOOL" if q == "STATUS" else "FLOAT",
                    })
                continue
            rows.append({
                "tag": f"{eq.name}_{q}",
                "eqp_name": eq.name,
                "label": eq.label,
                "prefix": eq.prefix,
                "quantity": q,
                "temp_point": None,
                "level": eq.level,
                "role": eq.role,
                "confidence": eq.confidence,
                "source": eq.source,
                "dtype": "BOOL" if q == "STATUS" else "FLOAT",
            })
    return rows


if __name__ == "__main__":
    import pandas as pd

    eq = build_equipment()
    tags = build_tags(eq)
    df = pd.DataFrame(tags)
    print(f"equipment groups: {len(eq)}")
    print(f"total tags: {len(tags)}")
    print(df["confidence"].value_counts())
    print(df.groupby(["prefix", "confidence"]).size())
