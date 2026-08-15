r"""
Stage 5 -- Classification (root-cause / physics)
===================================================
This is the ONLY file that says what a deviating feature *means*
mechanically. ingest/features/health don't know fault names; the CLI,
report.py, and app.py (dashboard) all call classify_row() so the "which
fault is this" logic can never fork into two different answers between the
command line and the dashboard -- which is what the original app.py did
(the same top-feature / confidence-ratio math was duplicated 3x).

Root-cause categories, grouped by what physically produces each signature:
  - Rotor-Level        : shaft-order harmonics (1X/2X/3X)      -> unbalance, misalignment, looseness
  - Rolling-Element Bearing : bearing defect frequencies (FTF/BPFO/BPFI/BSF) -> race/roller/cage defects
  - General / Broadband : time-domain stats (RMS, kurtosis, crest factor) -> general wear, impacting

To add or re-tune a root cause, edit DIAGNOSTIC_RULES here only.
"""

from dataclasses import dataclass

import pandas as pd

AMBIGUOUS_RATIO = 1.3   # top/runner-up |z| below this = no clearly dominant driver

DIAGNOSTIC_RULES = {
    "amp_1x":       {"category": "Rotor-Level",             "fault": "Unbalance / Bent Shaft"},
    "amp_2x":       {"category": "Rotor-Level",             "fault": "Misalignment"},
    "amp_3x":       {"category": "Rotor-Level",             "fault": "Misalignment / Mechanical Looseness"},
    "amp_BPFO_hz":  {"category": "Rolling-Element Bearing", "fault": "Outer Race Defect"},
    "amp_BPFI_hz":  {"category": "Rolling-Element Bearing", "fault": "Inner Race Defect"},
    "amp_BSF_hz":   {"category": "Rolling-Element Bearing", "fault": "Roller Element Defect"},
    "amp_FTF_hz":   {"category": "Rolling-Element Bearing", "fault": "Cage Defect"},
    "kurtosis":     {"category": "General / Broadband",     "fault": "Micro-pitting / Early Impulsive Impacts"},
    "rms":          {"category": "General / Broadband",     "fault": "General Severe Wear (Broadband energy)"},
    "crest_factor": {"category": "General / Broadband",     "fault": "Severe Metal-on-Metal Impacts"},
}


@dataclass
class Classification:
    dominant_feature: str
    fault: str
    category: str
    confidence_ratio: float
    is_ambiguous: bool


def classify_row(row: pd.Series, z_cols: list, ambiguous_ratio: float = AMBIGUOUS_RATIO) -> Classification:
    """Name the dominant root cause for one reading (a row with z_<feature>
    columns). Used identically by the CLI alarm print, report.py, and every
    dashboard panel that needs a fault name -- change the math here once,
    everywhere stays in sync."""
    z_vals = row[z_cols].abs().sort_values(ascending=False)
    dominant = z_vals.index[0].replace("z_", "")
    rule = DIAGNOSTIC_RULES.get(dominant, {"category": "Unknown", "fault": "Unclassified / Unknown"})
    confidence_ratio = (
        float(z_vals.iloc[0] / z_vals.iloc[1])
        if len(z_vals) > 1 and z_vals.iloc[1] > 1e-9
        else float("inf")
    )
    return Classification(
        dominant_feature=dominant,
        fault=rule["fault"],
        category=rule["category"],
        confidence_ratio=confidence_ratio,
        is_ambiguous=confidence_ratio < ambiguous_ratio,
    )
