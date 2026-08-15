# ⚙️ Multi-Modal Fleet Diagnostics Engine

A physics-based **predictive maintenance (PdM) dashboard** (mainly onlt health monitoring for now not PdM but will be in future)for rolling-element
bearing fault diagnosis, built on the NASA/IMS run-to-failure vibration
dataset. It turns raw vibration snapshots into a per-sensor health trend,
flags the onset of degradation, and names the most likely root cause —
unbalance, misalignment, or a specific bearing defect (outer race / inner
race / roller / cage) — using bearing-geometry defect frequencies, not a
black-box model.

> Built as a portfolio project to demonstrate applied vibration analysis
> and predictive-maintenance engineering, currently scoped to bearing-fault
> physics on the IMS dataset.

## What it does

- **Order + spectral analysis** — RMS, crest factor, kurtosis, and FFT-derived
  amplitudes at 1X/2X/3X shaft order plus the four classic bearing defect
  frequencies (FTF, BPFO, BPFI, BSF), computed from bearing geometry and
  shaft speed.
- **Unsupervised health index** — each channel is baselined against its own
  early-life data; a composite z-score tracks how far it's drifted, with a
  persistence-gated alarm for sustained onset (not one noisy spike).
- **Rule-based root-cause classification** — the dominant deviating feature
  is mapped to a physical fault (e.g. `amp_BPFO_hz` → Outer Race Defect) via
  a single, auditable rule table — the same logic used by both the CLI and
  the dashboard, so the two can never disagree.
- **Fleet view** — a maintenance priority queue that estimates time-to-critical
  per sensor from its recent degradation slope, plus a filterable alert log.
- **Two-part exportable report** — an automated read (trend chart, spectral
  signature, plain-English diagnosis) alongside the full underlying data table,
  so an engineer can verify the call reading-by-reading.

## Screenshots

*(add a screenshot or two of the dashboard here — e.g. Section 3 run-analysis
view and a generated diagnostic report — to give visitors a preview without
needing to run it locally)*

## Tech stack

| Layer | Tools |
|---|---|
| Dashboard | [Streamlit](https://streamlit.io), Plotly |
| Signal processing | NumPy, SciPy (`rfft`, `kurtosis`) |
| Data handling | pandas |
| Reporting | Matplotlib (static charts), self-contained HTML export |

## Project structure

```
.
├── app/
│   ├── app.py                 # Streamlit dashboard (5-section workflow)
│   ├── ims_pipeline.py        # Thin backward-compatible CLI entry point
│   ├── run_pipeline.bat       # Windows convenience wrapper for the CLI
│   └── pipeline/              # The actual engine — one file per stage
│       ├── constants.py       #   Stage 0: rig physics, DEFECT_FREQS
│       ├── ingest.py          #   Stage 1: discover_files, load_snapshot
│       ├── features.py        #   Stage 2: feature extraction, trend table
│       ├── health.py          #   Stage 3/4: baseline z-score, onset alarm
│       ├── classify.py        #   Stage 5: root-cause rules, classify_row()
│       ├── report.py          #   Stage 6: per-channel Markdown report
│       ├── plotting.py        #   Trend PNGs
│       └── cli.py             #   Stage 7: argparse wiring
├── data/                      # Raw datasets (gitignored — see data/README.md)
├── outputs/                   # Pipeline output: CSV + plots + reports
│   └── set2_data/             #   Sample output committed for a quick preview
├── setup_pdm_dirs.bat         # One-time Windows folder scaffolding script
└── requirements.txt
```

`app.py` and the CLI both import from the same `pipeline/` package, so the
dashboard's "Run Analysis" step and `python ims_pipeline.py` on the command
line always produce identical numbers — there's exactly one implementation
of the order-analysis and root-cause logic, not two drifting copies.

## Getting started

```bash
# 1. Clone and install
git clone <YOUR_REPO_URL>
cd <YOUR_REPO_NAME>
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Get the data — see data/README.md for the download link and folder layout

# 3. Run the dashboard
streamlit run app/app.py
```

The dashboard also runs in a self-contained **demo mode** (synthetic
run-to-failure trends) if you just want to click through Sections 4/5
without wiring up real data first.

### Command-line pipeline (optional)

```bash
python app/ims_pipeline.py --data-dir data/set2_data --n-channels 4 --out-dir outputs
```

Or set `IMS_DATA_ROOT` / `IMS_OUTPUT_ROOT` once (see `data/README.md`) and
just pass the subfolder name.

## How the physics works

Bearing defect frequencies are derived once from shaft speed + bearing
geometry (`pipeline/constants.py`) and reused everywhere else:

- **FTF** (Fundamental Train Frequency) — cage defect
- **BPFO** (Ball Pass Frequency, Outer race) — outer race defect
- **BPFI** (Ball Pass Frequency, Inner race) — inner race defect
- **BSF** (Ball Spin Frequency) — roller/ball defect

Each reading's dominant deviating feature (by |z-score|) is looked up
against a fixed rule table to name the most likely fault. If the top and
second-place features are within 1.3x of each other, the reading is flagged
**ambiguous** rather than confidently named — a broadband/general-wear
signature instead of one classic fault.

## Known limitations

- Rule-based classification, not a trained ML model — it names the fault
  physics implies, not one learned from labeled failure data.
- Defect frequencies are fixed to the IMS rig's RPM and bearing geometry;
  a different asset needs its own constants (see `pipeline/constants.py`).
- No spectral windowing (Hann/Hamming) is applied to the order-amplitude
  FFT, so some spectral leakage is possible.
- Scope is intentionally narrow: bearing-fault + rotor-order + broadband
  vibration diagnostics only — not a general condition-monitoring platform.

## License

MIT — see [LICENSE](LICENSE).
