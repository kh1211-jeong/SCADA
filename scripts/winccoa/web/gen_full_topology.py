"""Generate the FULL-plant tag list + topology.json from EGMS's own
build_topology.py (reused verbatim, not reimplemented, per EGMS/CLAUDE.md's
own rule: "기존에 검증된 로직은 재구현하지 말고 import해서 재사용").

Every node gets a STATUS bool. Types that carry real analog readings in the
reference screens additionally get POWER/VOLTAGE/CURRENT/PF (breakers/mains)
or TEMP/LOAD (transformers).

Usage:
  python gen_full_topology.py --egms-path "..\\..\\..\\EGMS" \
      --tag-list-out "C:\\WinCC_OA_Proj\\SVR_TEST\\scripts\\tag_list_full.csv" \
      --topology-out "C:\\WinCC_OA_Proj\\SVR_TEST\\javascript\\web\\topology_full.json"
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ANALOG_TYPES = {"BTR", "MAIN", "VCB_FEEDER", "ACB", "ACB_MAIN_EMG", "GCB"}
TEMP_TYPES = {"BTR", "LTR"}
# everything gets STATUS except pure structural nodes
NO_STATUS_TYPES = {"BUS", "RETURN"}


def node_level(name: str, etype: str, LEVEL: dict, tie_level_fn) -> int:
    if etype in ("TIE", "DIS"):
        return tie_level_fn(name)
    return LEVEL.get(etype, 10)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--egms-path", type=Path, required=True)
    ap.add_argument("--tag-list-out", type=Path, required=True)
    ap.add_argument("--topology-out", type=Path, required=True)
    args = ap.parse_args()

    sys.path.insert(0, str(args.egms_path.resolve()))
    import build_topology as bt  # the actual EGMS module, reused not reimplemented

    g = bt.gen_grid()
    cov = bt.coverage(g)
    print(f"EGMS build_topology: {cov['nodes']} nodes, {cov['edges']} edges, "
          f"{len(cov['orphans'])} orphans, {len(cov['unparsed'])} unparsed")

    rows = []
    nodes_json = []
    for e in g.equipment:
        name, etype, meta = e["name"], e["etype"], e["meta"]
        level = node_level(name, etype, bt.LEVEL, bt.tie_level)
        nodes_json.append({"id": name, "etype": etype, "level": level, "meta": meta})

        if etype not in NO_STATUS_TYPES:
            rows.append({"tag": f"{name}_STATUS", "dtype": "BOOL"})
        if etype in ANALOG_TYPES:
            for suffix in ("POWER", "VOLTAGE", "CURRENT", "PF"):
                rows.append({"tag": f"{name}_{suffix}", "dtype": "FLOAT"})
        if etype in TEMP_TYPES:
            rows.append({"tag": f"{name}_TEMP", "dtype": "FLOAT"})
            rows.append({"tag": f"{name}_LOAD", "dtype": "FLOAT"})

    edges_json = [{"src": e["src"], "dst": e["dst"], "etype": e["etype"]} for e in g.edges]

    args.tag_list_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.tag_list_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["tag", "dtype"])
        w.writeheader()
        w.writerows(rows)

    args.topology_out.parent.mkdir(parents=True, exist_ok=True)
    args.topology_out.write_text(
        json.dumps({"nodes": nodes_json, "edges": edges_json}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"wrote {args.tag_list_out} ({len(rows)} tags)")
    print(f"wrote {args.topology_out} ({len(nodes_json)} nodes, {len(edges_json)} edges)")


if __name__ == "__main__":
    main()
