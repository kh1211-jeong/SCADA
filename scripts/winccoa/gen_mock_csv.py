"""Generate mock FMCS trend CSVs for SVR_TEST rehearsal (SKILL_winccoa.md section 6).

THIS DATA IS SYNTHETIC. It exists only to exercise SVR_TEST's DP/trend
pipeline and CLI_TEST's panels before the real Oracle FMCS extract is
available (fmcs/ is currently empty - see README.md 3.1). Replace with the
real extract before using any result for the #1/#2/#3 deliverables, and
label every mock-derived chart/table "가상 데이터(예행용)".

Outputs (into this script's directory unless --out-dir is given):
  mock_wide.csv      timestamp x tag, analysis-ready (pivoted)
  mock_fmcs_raw.csv  EQP_NAME,PARAM_CODE,TRND_DATE,TAG_COMPRS_VAL
                      (mirrors the real Oracle TH_CM_FMCS_TRND compression:
                       one row per tag per minute, "sec:val;sec:val;..."
                       at 3-second cadence - see sample image/trend data
                       sample.png)
  tag_list.csv        the generated equipment/tag catalog, for the CTRL
                       DP-creation script to consume.

Usage:
  python gen_mock_csv.py --minutes 120 --seed 0
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.topology.equipment_catalog import build_equipment, build_tags  # noqa: E402

SEC_STEP = 3
SAMPLES_PER_MIN = 60 // SEC_STEP  # 20


def _load_curve(n_minutes: int, rng: np.random.Generator, base: float, amplitude: float, noise: float) -> np.ndarray:
    """Smooth daily-ish load curve + small noise, one value per minute."""
    t = np.arange(n_minutes) / max(n_minutes, 1)
    curve = base + amplitude * (0.5 + 0.5 * np.sin(2 * np.pi * t - np.pi / 2))
    curve += rng.normal(0, noise, size=n_minutes)
    return curve


def _expand_to_samples(per_minute: np.ndarray, rng: np.random.Generator, jitter: float) -> np.ndarray:
    """20 samples/minute (3s cadence), small jitter around each minute's level."""
    out = np.repeat(per_minute, SAMPLES_PER_MIN)
    out = out + rng.normal(0, jitter, size=out.shape)
    return out


def generate(minutes: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    rng = np.random.default_rng(seed)
    equipment = build_equipment()
    tags = build_tags(equipment)

    start = pd.Timestamp("2026-09-24 00:00:00")
    minute_index = pd.date_range(start, periods=minutes, freq="min")
    sample_index = pd.date_range(start, periods=minutes * SAMPLES_PER_MIN, freq=f"{SEC_STEP}s")

    # group tags by (eqp_name) so CURRENT/VOLTAGE/PF stay physically consistent
    by_eqp: dict[str, list[dict]] = {}
    for row in tags:
        by_eqp.setdefault(row["eqp_name"], []).append(row)

    wide_cols: dict[str, np.ndarray] = {}
    raw_rows: list[dict] = []

    for eqp_name, rows in by_eqp.items():
        level = rows[0]["level"]
        rated_v = 6600.0 if "6.6kV" in level else (154000.0 if "154kV" in level else 220.0)
        if level == "154kV":
            rated_v = 154.0  # displayed in kV on those screens

        base_load = rng.uniform(0.3, 0.85)  # fraction of a notional rating, drives CURRENT/POWER/LOAD together
        load_curve_min = _load_curve(minutes, rng, base=base_load, amplitude=0.15, noise=0.02)
        load_curve_min = np.clip(load_curve_min, 0.05, 1.0)

        rated_current = rng.uniform(200, 1600)
        pf_sign = rng.choice([1, -1], p=[0.8, 0.2])  # mostly lagging(+), sometimes leading(-) - 진상/지상
        pf_base = pf_sign * rng.uniform(95, 99)

        current_min = load_curve_min * rated_current
        voltage_min = rated_v * (1 - 0.01 * load_curve_min) + rng.normal(0, rated_v * 0.001, minutes)
        pf_min = pf_base + rng.normal(0, 0.3, minutes)
        pf_min = np.clip(pf_min, -99.9, 99.9)
        # POWER (kW) = sqrt(3) * V(kV) * I(A) * (PF/100) ; here V is already
        # in the same unit family as the screen boxes (kV for 154k/6.6k, V for 220V)
        v_for_power = voltage_min if level != "220V" else voltage_min / 1000.0
        power_min = np.sqrt(3) * v_for_power * current_min * (pf_min / 100.0)
        reactive_min = power_min * np.tan(np.arccos(np.clip(np.abs(pf_min) / 100.0, 0.01, 1.0))) * np.sign(pf_min)
        temp_min = 40 + 15 * load_curve_min + rng.normal(0, 1.0, minutes)
        load_pct_min = 100 * load_curve_min
        tap_min = np.round(np.clip(8 + rng.normal(0, 0.3, minutes), 6, 12))
        status_min = rng.choice([1, 1, 1, 1, 0], size=minutes)  # mostly closed/normal

        series_by_qty = {
            "CURRENT": current_min, "VOLTAGE": voltage_min, "POWER": power_min,
            "REACTIVE": reactive_min, "PF": pf_min, "TEMP": temp_min,
            "LOAD": load_pct_min, "TAP": tap_min, "STATUS": status_min,
        }

        for row in rows:
            qty = row["quantity"]
            per_min = series_by_qty.get(qty)
            if per_min is None:
                continue
            jitter = {
                "CURRENT": rated_current * 0.005, "VOLTAGE": rated_v * 0.0005, "POWER": abs(power_min).mean() * 0.005 + 1e-6,
                "REACTIVE": abs(reactive_min).mean() * 0.01 + 1e-6, "PF": 0.05, "TEMP": 0.2, "LOAD": 0.3, "TAP": 0.0, "STATUS": 0.0,
            }.get(qty, 0.0)
            samples = _expand_to_samples(per_min, rng, jitter)
            if row["dtype"] == "BOOL":
                samples = (samples > 0.5).astype(int)

            wide_cols[row["tag"]] = samples

            # raw compressed rows: one per minute, 20 samples "sec:val;..."
            for m in range(minutes):
                seg = samples[m * SAMPLES_PER_MIN:(m + 1) * SAMPLES_PER_MIN]
                comprs = ";".join(f"{s}:{v:.4f}" for s, v in zip(range(0, 60, SEC_STEP), seg))
                raw_rows.append({
                    # EQP_NAME carries the full tag incl. quantity suffix
                    # (e.g. VCB_3F11A10_CURRENT) - confirmed from
                    # sample image/trend data sample.png, NOT the bare
                    # equipment root. PARAM_CODE is constant ("PVLAST")
                    # across all rows in that capture, so it is NOT the
                    # quantity discriminator.
                    "EQP_NAME": row["tag"],
                    "PARAM_CODE": "PVLAST",
                    "TRND_DATE": minute_index[m].strftime("%y/%m/%d %H:%M:%S"),
                    "TAG_COMPRS_VAL": comprs,
                })

    wide_df = pd.DataFrame(wide_cols, index=sample_index)
    wide_df.index.name = "timestamp"
    raw_df = pd.DataFrame(raw_rows)
    return wide_df, raw_df, tags


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=120)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()

    wide_df, raw_df, tags = generate(args.minutes, args.seed)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    wide_path = args.out_dir / "mock_wide.csv"
    raw_path = args.out_dir / "mock_fmcs_raw.csv"
    tag_list_path = args.out_dir / "tag_list.csv"

    wide_df.to_csv(wide_path)
    raw_df.to_csv(raw_path, index=False)
    pd.DataFrame(tags).to_csv(tag_list_path, index=False)

    n_float = sum(1 for t in tags if t["dtype"] == "FLOAT")
    n_bool = sum(1 for t in tags if t["dtype"] == "BOOL")
    print(f"tags: {len(tags)} ({n_float} FLOAT, {n_bool} BOOL)")
    print(f"mock_wide.csv   : {wide_df.shape[0]} rows x {wide_df.shape[1]} cols -> {wide_path}")
    print(f"mock_fmcs_raw.csv: {len(raw_df)} rows -> {raw_path}")
    print(f"tag_list.csv    : {len(tags)} rows -> {tag_list_path}")
    print("NOTE: synthetic data - do not use for #1/#2/#3 reporting without labeling it as such.")


if __name__ == "__main__":
    main()
