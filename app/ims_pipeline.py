r"""
Backward-compatible entry point.

All real logic now lives in pipeline/ (see PROJECT_NOTES.md for why it was
split -- one file per stage: ingest, features, health, classify, report,
plotting, cli). This file exists only so `python ims_pipeline.py --data-dir
...` and run_pipeline.bat keep working exactly as before, unchanged.
"""

from pipeline.cli import main

if __name__ == "__main__":
    main()
