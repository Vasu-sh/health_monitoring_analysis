r"""
Plotting -- per-channel trend PNGs (time-domain, shaft-order, health index).
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def plot_trends(table: pd.DataFrame, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)

    for ch, g in table.groupby("channel"):
        g = g.sort_values("file_index")
        fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)

        axes[0].plot(g["file_index"], g["rms"], label="RMS")
        axes[0].plot(g["file_index"], g["kurtosis"], label="Kurtosis")
        axes[0].set_title(f"{ch}: time-domain indicators")
        axes[0].legend()

        for col in ["amp_1x", "amp_2x", "amp_3x"]:
            axes[1].plot(g["file_index"], g[col], label=col)
        axes[1].set_title(f"{ch}: shaft-order amplitudes")
        axes[1].legend()

        axes[2].plot(g["file_index"], g["health_indicator"], color="black", label="health indicator")
        onset = g[g["onset_flagged"]]
        if not onset.empty:
            axes[2].axvline(onset["file_index"].iloc[0], color="red", linestyle="--", label="flagged onset")
        axes[2].set_title(f"{ch}: composite health indicator")
        axes[2].set_xlabel("file index (time order)")
        axes[2].legend()

        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, f"trend_{ch}.png"), dpi=120)
        plt.close(fig)
