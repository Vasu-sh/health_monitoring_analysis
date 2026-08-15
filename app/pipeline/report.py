r"""
Stage 6 -- Report
===================
Previously deferred ("pipeline currently only outputs CSV + PNG, no
human-readable summary" -- PROJECT_NOTES.md). Implemented as Markdown:
plain text, diffable/version-controllable, renders natively if you open it
on GitHub or drop it straight into the Streamlit dashboard with st.markdown.

One report per channel, written next to that channel's CSV/PNG in the same
output folder -- see cli.py / pipeline.__init__ for how out_dir is chosen.
"""

import os
from datetime import datetime

import pandas as pd

from .classify import classify_row
from .constants import DEFECT_FREQS


def generate_channel_report(g: pd.DataFrame, channel: str, defect_freqs: dict = DEFECT_FREQS) -> str:
    """Build the Markdown report text for one channel's trend table
    (already run through flag_onset, i.e. has z_* / health_indicator /
    onset_flagged columns)."""
    g = g.sort_values("file_index")
    z_cols = [c for c in g.columns if c.startswith("z_")]
    latest = g.iloc[-1]
    result = classify_row(latest, z_cols)

    onset_rows = g[g["onset_flagged"]]
    onset_file = onset_rows["file"].iloc[0] if not onset_rows.empty else None

    lines = [
        f"# Health Report -- {channel}",
        f"_generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
        "",
        "## Summary",
        f"- Readings analyzed: {len(g)}",
        f"- Latest health index: {latest['health_indicator']:.2f}",
        "- Onset flagged: " + (f"yes, at `{onset_file}`" if onset_file else "no sustained onset detected"),
        "",
        "## Root-Cause Classification (latest reading)",
        f"- Dominant feature: `{result.dominant_feature}`",
        f"- Category: {result.category}",
        f"- Likely fault: **{result.fault}**",
        f"- Confidence ratio (top / runner-up |z|): {result.confidence_ratio:.2f}"
        + (" -- ambiguous, no single dominant driver (see Uncategorized Anomalies)" if result.is_ambiguous else ""),
        "",
        "## Reference Defect Frequencies Used (Hz)",
    ]
    for name, freq in defect_freqs.items():
        lines.append(f"- {name}: {freq:.2f}")
    lines.append("")
    lines.append(f"See `trend_{channel}.png` in the same folder for the full time-history plot.")
    return "\n".join(lines)


def write_reports(table: pd.DataFrame, out_dir: str, defect_freqs: dict = DEFECT_FREQS) -> list:
    """One report_<channel>.md per channel in out_dir. Returns the list of
    paths written."""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for ch, g in table.groupby("channel"):
        text = generate_channel_report(g, ch, defect_freqs)
        path = os.path.join(out_dir, f"report_{ch}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        paths.append(path)
    return paths
