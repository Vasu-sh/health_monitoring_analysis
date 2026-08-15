r"""
Stage 1 -- Ingest
==================
Nothing physics- or fault-related lives here on purpose: this stage only
knows how to find files on disk and read one into a DataFrame. Swapping
data sources later (e.g. a live IIoT stream instead of flat files) means
touching only this file.
"""

import glob
import os

import pandas as pd


def discover_files(data_dir: str) -> list:
    """IMS filenames ARE timestamps (e.g. 2003.10.22.12.06.24) so a plain
    sort puts them in time order."""
    files = sorted(glob.glob(os.path.join(data_dir, "*")))
    if not files:
        raise FileNotFoundError(f"No files found in {data_dir}")
    return files


def load_snapshot(filepath: str, n_channels: int) -> pd.DataFrame:
    """Read one raw tab-separated snapshot file into a DataFrame with
    columns ch1..chN."""
    names = [f"ch{i + 1}" for i in range(n_channels)]
    return pd.read_csv(filepath, sep="\t", header=None, names=names)
