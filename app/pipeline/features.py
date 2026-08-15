r"""
Stage 2 -- Feature extraction
==============================
Per file, per channel: time-domain stats (RMS, kurtosis, crest factor) and
order-domain amplitudes (1X/2X/3X shaft orders + the four bearing defect
frequencies from constants.DEFECT_FREQS).

Known caveat carried over from the original single-file version: no
windowing (Hann/Hamming) before the FFT, so there's some spectral leakage
in the order-amplitude estimates. Also `amplitude_near`'s tol_hz=2.0 search
window is fixed regardless of RPM. Both are listed as open items in
PROJECT_NOTES.md, not bugs.
"""

import os

import numpy as np
import pandas as pd
from scipy.fft import rfft, rfftfreq
from scipy.stats import kurtosis

from .constants import FS, SHAFT_HZ, DEFECT_FREQS
from .ingest import discover_files, load_snapshot


def amplitude_near(freqs: np.ndarray, spectrum: np.ndarray, target_hz: float, tol_hz: float = 2.0) -> float:
    mask = np.abs(freqs - target_hz) <= tol_hz
    return float(spectrum[mask].max()) if mask.any() else np.nan


def extract_features(sig: np.ndarray, fs: int = FS) -> dict:
    n = len(sig)
    freqs = rfftfreq(n, d=1 / fs)
    spectrum = np.abs(rfft(sig - sig.mean()))

    rms = float(np.sqrt(np.mean(sig ** 2)))
    peak = float(np.max(np.abs(sig)))

    feats = {
        "rms": rms,
        "peak": peak,
        "crest_factor": peak / rms if rms else np.nan,
        "kurtosis": float(kurtosis(sig)),
        "amp_1x": amplitude_near(freqs, spectrum, SHAFT_HZ),
        "amp_2x": amplitude_near(freqs, spectrum, 2 * SHAFT_HZ),
        "amp_3x": amplitude_near(freqs, spectrum, 3 * SHAFT_HZ),
    }
    for name, f in DEFECT_FREQS.items():
        feats[f"amp_{name}"] = amplitude_near(freqs, spectrum, f)
    return feats


def build_trend_table(data_dir: str, n_channels: int) -> pd.DataFrame:
    """Run extract_features() across every file in data_dir -> one long
    feature table (file_index, file, channel, <features...>)."""
    files = discover_files(data_dir)
    print(f"Found {len(files)} snapshots in {data_dir}")

    rows = []
    for idx, f in enumerate(files):
        try:
            df = load_snapshot(f, n_channels)
        except Exception as e:
            print(f"  skipped {f}: {e}")
            continue

        for ch in df.columns:
            feats = extract_features(df[ch].to_numpy())
            feats.update({"file_index": idx, "file": os.path.basename(f), "channel": ch})
            rows.append(feats)

        if idx % max(1, len(files) // 10) == 0:
            print(f"  processed {idx + 1}/{len(files)}")

    table = pd.DataFrame(rows)
    front = ["file_index", "file", "channel"]
    return table[front + [c for c in table.columns if c not in front]]
