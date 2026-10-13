"""Path constants for PROJECT_ELEC datasets.

All paths are relative to the project root (the directory containing this
`src/` package). Verified 2026-09-28 against the files actually on disk —
see README.md section 3 for dataset provenance.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- FMCS (primary, real SCADA extract) ---------------------------------
# Not extracted yet. Loader code must tolerate this path not existing.
FMCS_DIR = ROOT / "fmcs"

# --- SWaT (Kaggle) --------------------------------------------------------
SWAT_DIR = ROOT / "swat"
SWAT_MERGED_CSV = SWAT_DIR / "merged.csv"
SWAT_NORMAL_CSV = SWAT_DIR / "normal.csv"
SWAT_ATTACK_CSV = SWAT_DIR / "attack.csv"
# NOTE: merged.csv == normal.csv rows followed by attack.csv rows appended
# as one trailing block (not interleaved by real timestamp). There is a
# single backwards timestamp jump at the normal/attack boundary. Do not
# build sliding windows across that boundary.

# --- WADI (Kaggle) ---------------------------------------------------------
WADI_DIR = ROOT / "wadi"
WADI_NORMAL_CSV = WADI_DIR / "WADI_14days_new.csv"   # header row only, no units row in this copy
WADI_ATTACK_CSV = WADI_DIR / "WADI_attackdataLABLE.csv"  # extra leading index row -> skiprows=1
# NOTE: WADI_attackdataLABLE.csv's "Time" column lost its hour component in
# some prior Excel pass (values like "00:00.0" = mm:ss.f only). Reconstruct
# elapsed time from the "Row" column (1-second cadence) instead of parsing
# Date+Time directly. Columns 2_LS_001_AL, 2_LS_002_AL, 2_P_001_STATUS,
# 2_P_002_STATUS are entirely NaN in the normal file - drop them.

# --- HAI (git+LFS, icsdataset/hai) -----------------------------------------
HAI_DIR = ROOT / "hai"
# BLOCKED as of 2026-09-28: all versioned CSVs (hai-22.04, hai-23.05,
# haiend-23.05) are LFS pointer stubs. `git lfs fetch` on this remote fails
# with "This repository exceeded its LFS budget" - an upstream limit, not
# fixable locally. Re-check periodically or source from an alternate host.

# --- PowerGraph (figshare 22820534) ----------------------------------------
POWERGRAPH_DIR = ROOT / "fig_share_powergraph_22820534"
POWERGRAPH_CASCADES_DIR = POWERGRAPH_DIR / "dataset_cascades" / "dataset_cascades"
POWERGRAPH_PF_OPF_DIR = POWERGRAPH_DIR / "dataset_pf_opf"
# NOTE: actual on-disk layout double-nests the grid name and PyG's raw/
# folder one level deeper than the top-level dir name suggests, e.g.
#   dataset_cascades/dataset_cascades/ieee24/ieee24/raw/*.mat
# A PyTorch Geometric InMemoryDataset must be pointed at the INNER ieee24
# (POWERGRAPH_CASCADES_DIR / "ieee24" / "ieee24"), not the outer one.
POWERGRAPH_CASCADE_GRIDS = ["ieee24", "ieee39", "ieee118", "uk"]
POWERGRAPH_PF_OPF_GRIDS = ["ieee24", "ieee39", "ieee118", "uk", "texas"]  # texas: pf_opf only


def powergraph_cascade_raw_dir(grid: str) -> Path:
    """Root a PyG InMemoryDataset(root=...) at this path for a cascades grid."""
    return POWERGRAPH_CASCADES_DIR / grid / grid


def powergraph_pf_opf_raw_dir(grid: str) -> Path:
    return POWERGRAPH_PF_OPF_DIR / grid / grid if grid != "texas" else POWERGRAPH_PF_OPF_DIR / "texas"


# --- misc --------------------------------------------------------------
SAMPLE_IMAGE_DIR = ROOT / "sample image"
RESULTS_DIR = ROOT / "results"
SCRIPTS_WINCCOA_DIR = ROOT / "scripts" / "winccoa"
