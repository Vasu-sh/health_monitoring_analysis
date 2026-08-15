r"""
Stage 3/4 -- Health index & onset alarm
=========================================
Purely statistical: baseline each channel against its own early-run data,
compute a composite health_indicator (mean |z-score| across FEATURE_COLS),
and persistence-gate an onset_flagged alarm. This stage deliberately does
NOT know what a fault is called -- see classify.py for that. Keeping the
two separate means health.py stays reusable even if the fault-naming rules
change (or a trained classifier replaces classify.py later).
"""

import pandas as pd

FEATURE_COLS = [
    "rms", "crest_factor", "kurtosis",
    "amp_1x", "amp_2x", "amp_3x",
    "amp_FTF_hz", "amp_BPFO_hz", "amp_BPFI_hz", "amp_BSF_hz",
]


def flag_onset(table: pd.DataFrame, baseline_frac: float = 0.2,
                z_thresh: float = 4.0, persistence: int = 5) -> pd.DataFrame:
    """Adds z_<feature> columns, health_indicator, and onset_flagged to
    `table`, baselined per-channel against that channel's first
    `baseline_frac` of readings."""
    out = []
    for ch, g in table.groupby("channel"):
        g = g.sort_values("file_index").reset_index(drop=True)
        n_baseline = max(5, int(len(g) * baseline_frac))
        baseline = g.iloc[:n_baseline]

        z_cols = []
        for col in FEATURE_COLS:
            mu, sigma = baseline[col].mean(), baseline[col].std()
            sigma = sigma if sigma > 1e-12 else 1e-12
            z_col = f"z_{col}"
            g[z_col] = (g[col] - mu) / sigma
            z_cols.append(z_col)

        g["health_indicator"] = g[z_cols].abs().mean(axis=1)

        above = g["health_indicator"] > z_thresh
        onset_idx = None
        run_len = 0
        for i, flag in enumerate(above):
            run_len = run_len + 1 if flag else 0
            if run_len >= persistence:
                onset_idx = i - persistence + 1
                break

        g["onset_flagged"] = False
        if onset_idx is not None:
            g.loc[onset_idx:, "onset_flagged"] = True

        out.append(g)

    return pd.concat(out, ignore_index=True)
