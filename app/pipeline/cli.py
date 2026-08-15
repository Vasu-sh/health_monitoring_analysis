r"""
Stage 7 -- CLI entry point
============================
Wires ingest -> features -> health -> classify -> report -> plot together,
and defines the ONE rule for where output goes:

    <out-dir>/<run-name>/ims_feature_trend.csv
    <out-dir>/<run-name>/trend_<channel>.png
    <out-dir>/<run-name>/report_<channel>.md

run-name defaults to the dataset folder's own name (e.g. "set2_data"), so
running the CLI against set1/set2/set3 never overwrites another run, and
the dashboard's Local Folder tab -- which reads the same subfolder name --
can find (or write) results in the exact same place. See app.py's
"Save outputs to disk" option.

Usage
------
    python ims_pipeline.py --data-dir "C:\...\PdM\data\set2_data" --n-channels 4
    # or, with IMS_DATA_ROOT set once:
    python ims_pipeline.py --data-dir set2_data --n-channels 4

Get the data first:
    https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip
"""

import argparse
import os

from .classify import classify_row
from .constants import DEFECT_FREQS
from .features import build_trend_table
from .health import flag_onset
from .plotting import plot_trends
from .report import write_reports


def resolve_data_dir(data_dir: str, base_dir: str) -> str:
    """Let --data-dir be just a folder name (e.g. "set2_data") instead of
    the full path every time. If data_dir is already an absolute path it's
    used as-is; otherwise it's joined onto base_dir.

    base_dir comes from --base-dir, or if that's not given, from the
    IMS_DATA_ROOT environment variable.
    """
    if os.path.isabs(data_dir):
        return data_dir
    if not base_dir:
        raise ValueError(
            "data-dir is a relative folder name but no base directory was given. "
            "Pass --base-dir \"...\\PdM\\data\" or set the IMS_DATA_ROOT "
            "environment variable once (see run_pipeline.bat)."
        )
    return os.path.join(base_dir, data_dir)


def resolve_out_dir(out_dir: str, data_dir: str) -> str:
    """<out-dir>/<data folder's own name>/ -- see module docstring. Keeps
    every dataset's CSV/plots/reports in a predictable, non-colliding spot
    that the dashboard can find using the same subfolder name."""
    run_name = os.path.basename(os.path.normpath(data_dir))
    return os.path.join(out_dir, run_name)


def main():
    parser = argparse.ArgumentParser(description="Unsupervised IMS bearing trend pipeline")
    parser.add_argument("--data-dir", required=True,
                         help="Folder of raw snapshot files. Either a full path, or just "
                              "the subfolder name (e.g. set2_data) if --base-dir / "
                              "IMS_DATA_ROOT is set.")
    parser.add_argument("--base-dir", default=os.environ.get("IMS_DATA_ROOT", ""),
                         help="Parent folder containing set1_data/set2_data/etc. "
                              "Defaults to the IMS_DATA_ROOT environment variable if set.")
    parser.add_argument("--n-channels", type=int, default=4, help="4 for sets 2/3, 8 for set 1")
    parser.add_argument("--out-dir", default=os.environ.get("IMS_OUTPUT_ROOT", "./outputs"),
                         help="Parent folder for output; results land in <out-dir>/<data-dir name>/. "
                              "Defaults to the IMS_OUTPUT_ROOT environment variable, else ./outputs.")
    parser.add_argument("--baseline-frac", type=float, default=0.2)
    parser.add_argument("--z-thresh", type=float, default=4.0)
    parser.add_argument("--persistence", type=int, default=5)
    args = parser.parse_args()

    data_dir = resolve_data_dir(args.data_dir, args.base_dir)
    out_dir = resolve_out_dir(args.out_dir, data_dir)
    os.makedirs(out_dir, exist_ok=True)

    print("Theoretical bearing defect frequencies (Hz):", DEFECT_FREQS)

    table = build_trend_table(data_dir, args.n_channels)
    table = flag_onset(table, args.baseline_frac, args.z_thresh, args.persistence)

    for ch, g in table.groupby("channel"):
        g = g.sort_values("file_index")
        onset = g[g["onset_flagged"]]
        if onset.empty:
            print(f"[{ch}] no sustained onset above z={args.z_thresh} detected")
            continue
        z_cols = [c for c in g.columns if c.startswith("z_")]
        first_onset = onset.iloc[0]
        result = classify_row(first_onset, z_cols)
        print(f"\n\U0001f6a8 ALARM: [{ch}] Degradation Onset Detected!")
        print(f"   -> Time: {first_onset['file']}")
        print(f"   -> Primary Driver: {result.dominant_feature}")
        print(f"   -> Auto-Classification: {result.fault} ({result.category})")

    csv_path = os.path.join(out_dir, "ims_feature_trend.csv")
    table.to_csv(csv_path, index=False)
    print(f"\nWrote {len(table)} rows to {csv_path}")

    plot_trends(table, out_dir)
    print(f"Plots written to {out_dir}/trend_<channel>.png")

    report_paths = write_reports(table, out_dir)
    print(f"Reports written to {out_dir}/report_<channel>.md ({len(report_paths)} file(s))")


if __name__ == "__main__":
    main()
