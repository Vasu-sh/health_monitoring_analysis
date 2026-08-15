r"""
pipeline -- unsupervised IMS bearing analysis, one file per stage
====================================================================
    constants.py  Stage 0: rig physics (RPM, bearing geometry, DEFECT_FREQS)
    ingest.py     Stage 1: discover_files, load_snapshot
    features.py   Stage 2: extract_features, build_trend_table
    health.py     Stage 3/4: baseline z-score, health_indicator, onset alarm
    classify.py   Stage 5: root-cause rules + classify_row() (physics -> fault name)
    report.py     Stage 6: human-readable Markdown report per channel
    plotting.py   trend PNGs
    cli.py        Stage 7: argparse wiring, output-path convention

Import everything from here (both app.py and cli.py do this) so there is
exactly one public surface -- no separate "fallback copy" of constants
needed if this package is missing, unlike the old single-file version.
"""

from .constants import DEFECT_FREQS, SHAFT_HZ, SHAFT_RPM, bearing_defect_frequencies
from .ingest import discover_files, load_snapshot
from .features import amplitude_near, extract_features, build_trend_table
from .health import FEATURE_COLS, flag_onset
from .classify import AMBIGUOUS_RATIO, Classification, DIAGNOSTIC_RULES, classify_row
from .report import generate_channel_report, write_reports
from .plotting import plot_trends

__all__ = [
    "DEFECT_FREQS", "SHAFT_HZ", "SHAFT_RPM", "bearing_defect_frequencies",
    "discover_files", "load_snapshot",
    "amplitude_near", "extract_features", "build_trend_table",
    "FEATURE_COLS", "flag_onset",
    "AMBIGUOUS_RATIO", "Classification", "DIAGNOSTIC_RULES", "classify_row",
    "generate_channel_report", "write_reports",
    "plot_trends",
]
