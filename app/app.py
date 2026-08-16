import streamlit as st
import numpy as np
import pandas as pd
from datetime import datetime
from scipy.fft import rfft, rfftfreq
import plotly.graph_objects as go
import os
import sys
import tempfile
import io
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

st.set_page_config(page_title="Multi-Modal PdM Fleet Engine", layout="wide")

# Shared Drive-backed storage (optional -- see SETUP_DRIVE.md). Import is
# always safe: drive_store handles its own missing-library/missing-secret
# fallback internally, so this never breaks a local run without it set up.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive_store import load_state as load_shared_state, save_state as save_shared_state

# ==========================================
# PIPELINE INTEGRATION (pipeline/ package)
# ==========================================
# app.py expects a pipeline/ folder to sit next to it. Real per-sensor
# analysis (Section 3 -> "Run Analysis") calls straight into the same
# build_trend_table()/flag_onset()/classify_row() the CLI uses, via this one
# import, so the dashboard can never run a second, drifted copy of the
# order-analysis or root-cause math.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from pipeline import (
        build_trend_table, flag_onset, classify_row, write_reports, plot_trends,
        DIAGNOSTIC_RULES, FEATURE_COLS, DEFECT_FREQS,
    )
    from pipeline.cli import resolve_out_dir
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False
    DEFECT_FREQS = {}
    # Fallback copies so the dashboard (and its demo mode) still work if the
    # pipeline/ package isn't next to app.py -- keep these in sync with
    # pipeline/health.py and pipeline/classify.py.
    FEATURE_COLS = [
        "rms", "crest_factor", "kurtosis",
        "amp_1x", "amp_2x", "amp_3x",
        "amp_FTF_hz", "amp_BPFO_hz", "amp_BPFI_hz", "amp_BSF_hz",
    ]
    DIAGNOSTIC_RULES = {
        "amp_1x": {"category": "Rotor-Level", "fault": "Unbalance / Bent Shaft"},
        "amp_2x": {"category": "Rotor-Level", "fault": "Misalignment"},
        "amp_3x": {"category": "Rotor-Level", "fault": "Misalignment / Mechanical Looseness"},
        "amp_BPFO_hz": {"category": "Rolling-Element Bearing", "fault": "Outer Race Defect"},
        "amp_BPFI_hz": {"category": "Rolling-Element Bearing", "fault": "Inner Race Defect"},
        "amp_BSF_hz": {"category": "Rolling-Element Bearing", "fault": "Roller Element Defect"},
        "amp_FTF_hz": {"category": "Rolling-Element Bearing", "fault": "Cage Defect"},
        "kurtosis": {"category": "General / Broadband", "fault": "Micro-pitting / Early Impulsive Impacts"},
        "rms": {"category": "General / Broadband", "fault": "General Severe Wear (Broadband energy)"},
        "crest_factor": {"category": "General / Broadband", "fault": "Severe Metal-on-Metal Impacts"},
    }

    def classify_row(row, z_cols, ambiguous_ratio=1.3):
        """Minimal stand-in matching pipeline.classify.classify_row's shape,
        used only if the pipeline/ package couldn't be imported."""
        from types import SimpleNamespace
        z_vals = row[z_cols].abs().sort_values(ascending=False)
        dominant = z_vals.index[0].replace("z_", "")
        rule = DIAGNOSTIC_RULES.get(dominant, {"category": "Unknown", "fault": "Unclassified / Unknown"})
        ratio = float(z_vals.iloc[0] / z_vals.iloc[1]) if len(z_vals) > 1 and z_vals.iloc[1] > 1e-9 else float("inf")
        return SimpleNamespace(dominant_feature=dominant, fault=rule["fault"], category=rule["category"],
                                confidence_ratio=ratio, is_ambiguous=ratio < ambiguous_ratio)

HARDWARE_CHANNEL_MAP = {
    "Standard Single-Axis (Vibration)": 1,
    "Triaxial Smart Sensor (3-Axis)": 3,
    "4-in-1 IIoT Node (Vib/Temp/AE/Flux)": 4,
}

# ==========================================
# CUSTOM CSS: PREMIUM "AURA" AESTHETIC
# ==========================================
custom_css = """
<style>
    .stApp { background-color: #030303 !important; }
    html, body, [class*="css"], p, span, div, label { color: #ffffff !important; }
    h1, h2, h3 { text-shadow: 0px 0px 5px rgba(0, 255, 128, 0.7), 0px 0px 15px rgba(0, 200, 100, 0.4), 0px 0px 30px rgba(0, 150, 50, 0.2) !important; }
    div[data-baseweb="select"] > div, div[data-baseweb="input"] > div, div[data-baseweb="multiselect"] > div { background-color: #111111 !important; border: 1px solid rgba(0, 255, 128, 0.3) !important; box-shadow: 0px 0px 10px rgba(0, 255, 128, 0.1) !important; color: white !important; }
    .stButton>button { background-color: #080808 !important; color: #ffffff !important; border: 1px solid rgba(0, 255, 128, 0.6) !important; box-shadow: 0px 0px 15px rgba(0, 255, 128, 0.2) !important; transition: all 0.3s ease-in-out; }
    .stButton>button:hover { box-shadow: 0px 0px 25px rgba(0, 255, 128, 0.6) !important; border-color: #00ff80 !important; }
    .stDataFrame { border: 1px solid rgba(0, 255, 128, 0.3) !important; box-shadow: 0px 0px 15px rgba(0, 255, 128, 0.1) !important; }
    section[data-testid="stSidebar"] { border-right: 1px solid rgba(0, 255, 128, 0.25) !important; }
    section[data-testid="stSidebar"] div[role="radiogroup"] label { padding: 6px 4px !important; }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# ==========================================
# DATABASES, SCHEMAS & SESSION STATE
# ==========================================
SENSOR_MODELS = {
    "Standard Single-Axis (Vibration)": {"parameters": ["1D Vib"], "format": "[Time, Amplitude]"},
    "Triaxial Smart Sensor (3-Axis)": {"parameters": ["Axial", "Radial-X", "Radial-Y"], "format": "[Time, Axial, RadX, RadY]"},
    "4-in-1 IIoT Node (Vib/Temp/AE/Flux)": {"parameters": ["3-Axis Vib", "Temp", "Acoustics", "Flux"], "format": "[Time, Axial, RadX, RadY, Temp, AE, Flux]"}
}

FAULT_DATABASE = {
    "Rotor-Level (Any Shaft)": ["Unbalance", "Angular Misalignment", "Parallel Misalignment", "Bent/Bowed Shaft", "Mechanical Looseness", "Resonance"],
    "Rolling-Element Bearings": ["Outer Race Defect (BPFO)", "Inner Race Defect (BPFI)", "Ball/Roller Defect (BSF)", "Cage Defect (FTF)"],
    "Gearboxes": ["General Tooth Wear", "Cracked/Chipped Tooth"],
    "Pumps": ["Vane Pass (VPF)", "Cavitation"],
    "Motors (Electrical)": ["Stator/Rotor Eccentricity", "Broken Rotor Bars"]
}

# Initialize State
if 'sensors' not in st.session_state:
    st.session_state.sensors = {}
if 'analysis_ready' not in st.session_state:
    st.session_state.analysis_ready = False
if 'target_sensor' not in st.session_state:
    st.session_state.target_sensor = None
if 'active_sensor' not in st.session_state:
    # Which sensor row is selected in Section 2 / feeds Section 3. Kept in
    # session_state (not a local variable) so it survives navigating between
    # sidebar pages, the same way target_sensor already did for Section 4.
    st.session_state.active_sensor = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = "1"
if 'pipeline_results' not in st.session_state:
    # sensor_id -> DataFrame in flag_onset() schema (file_index, file, channel,
    # raw features, z_<feature>, health_indicator, onset_flagged)
    st.session_state.pipeline_results = {}

# One-time load from shared Google Drive storage (if configured), so every
# visitor starts from the same fleet state instead of an empty one. Runs
# once per browser session; silently no-ops if Drive isn't set up.
if '_shared_state_loaded' not in st.session_state:
    _shared = load_shared_state()
    if _shared:
        st.session_state.sensors.update(_shared["sensors"])
        st.session_state.pipeline_results.update(_shared["pipeline_results"])
        if _shared["alerts"]:
            st.session_state.alerts = _shared["alerts"]
    st.session_state._shared_state_loaded = True

# Mock Historical Alerts Database (Feeds Section 5) -- seed rows only, used
# when shared storage isn't configured or is still empty; real analysis
# runs append to this list via sync_pipeline_alerts() below.
if 'alerts' not in st.session_state:
    st.session_state.alerts = [
        {"Timestamp": "2026-07-21 21:45:00", "Sensor_ID": "PUMP-04-NODE", "Zone": "Compressor Station Alpha", "Severity": "🔴 Critical", "Root_Cause": "Unbalance", "Category": "Rotor-Level", "Value": "7.5 mm/s"},
        {"Timestamp": "2026-07-21 18:30:00", "Sensor_ID": "FAN-01-RADIAL", "Zone": "Ventilation HVAC", "Severity": "🟡 Warning", "Root_Cause": "Rising noise floor", "Category": "General / Broadband", "Value": "4.2 mm/s"},
        {"Timestamp": "2026-07-20 14:15:00", "Sensor_ID": "GEAR-02-AXIAL", "Zone": "Main Conveyor", "Severity": "🔴 Critical", "Root_Cause": "GMF Sidebands", "Category": "Gearbox", "Value": "8.1 mm/s"}
    ]

st.title("⚙️ Multi-Modal Fleet Diagnostics Engine")


# ==========================================
# DEMO DATA GENERATOR
# ==========================================
def build_demo_trend(sensor_id, n_points=50, channel_name="ch1"):
    """Synthetic run-to-failure trend in the exact schema flag_onset() returns.
    Lets Section 4/5 be previewed with realistic, decision-relevant numbers
    before real sensor files are wired in via Section 3."""
    rng = np.random.default_rng(abs(hash(sensor_id)) % (2**32))
    dominant_fault = rng.choice(FEATURE_COLS)
    baseline_len = int(n_points * 0.55)
    ramp = np.zeros(n_points)
    ramp[baseline_len:] = np.linspace(0, 1, n_points - baseline_len) ** 2.3
    health = np.clip(0.8 + ramp * 8.5 + rng.normal(0, 0.2, n_points), 0, None)

    rows = []
    for i in range(n_points):
        row = {
            "file_index": i,
            "file": f"demo_{i:04d}",
            "channel": channel_name,
            "health_indicator": float(health[i]),
            "onset_flagged": bool(health[i] > 4.0 and i > baseline_len),
        }
        for feat in FEATURE_COLS:
            if feat == dominant_fault:
                row[f"z_{feat}"] = float(health[i] * rng.uniform(0.85, 1.0))
            else:
                row[f"z_{feat}"] = float(rng.normal(0, 1) * (0.3 + 0.15 * ramp[i]))
        rows.append(row)
    return pd.DataFrame(rows)


def sync_pipeline_alerts(zone_lookup, health_z_thresh):
    """Turn the latest reading of every analyzed sensor/channel into a Section 5
    alert row, so the fleet log reflects real (or demo) pipeline output instead
    of only the three seed rows. Returns True if any new alert was appended,
    so the caller knows whether shared storage needs a fresh save."""
    changed = False
    for sid, df in st.session_state.pipeline_results.items():
        for chan, g in df.groupby("channel"):
            g = g.sort_values("file_index")
            latest = g.iloc[-1]
            if not latest["onset_flagged"]:
                continue
            z_cols = [c for c in g.columns if c.startswith("z_")]
            result = classify_row(latest, z_cols)
            severity = "🔴 Critical" if latest["health_indicator"] > health_z_thresh * 1.5 else "🟡 Warning"
            key = f"{sid}-{chan}-{latest['file']}"
            if any(a.get("_key") == key for a in st.session_state.alerts):
                continue
            st.session_state.alerts.append({
                "Timestamp": latest["file"],
                "Sensor_ID": f"{sid} ({chan})",
                "Zone": zone_lookup.get(sid, "Unknown"),
                "Severity": severity,
                "Root_Cause": result.fault,
                "Category": result.category,
                "Value": f"{latest['health_indicator']:.2f} (z-score)",
                "_key": key,
            })
            changed = True
    return changed


# ==========================================
# SECTION 4 EXPORT: TWO-PART DIAGNOSTIC REPORT
# ==========================================
# Mirrors the standard structure of a real vibration-analysis report (asset
# ID + condition badge + annotated spectra + one-line diagnosis + recommended
# action, per e.g. Power-MI's report guide and sample third-party reports)
# but built from exactly what this pipeline already computes -- no new fault
# types, still bearing-fault + rotor-order + broadband only.
REPORT_RECOMMENDATIONS = {
    "Rotor-Level": "Verify shaft balance and check coupling/foundation alignment at the next opportunity.",
    "Rolling-Element Bearing": "Schedule a bearing inspection; plan replacement if the defect-frequency harmonics persist or grow.",
    "General / Broadband": "Increase monitoring frequency and inspect for general wear, lubrication loss, or looseness.",
    "Unknown": "Signature isn't clearly dominated by one driver -- continue monitoring rather than acting on this reading alone.",
}


def _severity_for(current_health, thresh, onset_flagged):
    """Same 3-level severity vocabulary already used elsewhere in the
    dashboard (sync_pipeline_alerts' Critical/Warning split), reused here so
    the report doesn't introduce a fourth, inconsistent scale."""
    if not onset_flagged:
        return "Acceptable", "#2e7d32"
    if current_health >= thresh * 1.5:
        return "Critical", "#c62828"
    return "Alert", "#f9a825"


def _fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def build_diagnostic_report_html(g_all, sensor_id, channel, health_z_thresh, sample_interval_minutes, defect_freqs):
    """Two-part self-contained HTML report for one sensor/channel:
    Part 1 -- automated machine insight (graphs + rule-based cause, for a
              fast go/no-go read).
    Part 2 -- full underlying data (every raw feature + z-score behind that
              read), for an engineer to independently verify it.
    """
    g = g_all.sort_values("file_index").reset_index(drop=True)
    z_cols = [c for c in g.columns if c.startswith("z_")]
    latest = g.iloc[-1]
    result = classify_row(latest, z_cols)
    current_health = float(latest["health_indicator"])
    onset_flagged = bool(latest["onset_flagged"])
    onset_rows = g[g["onset_flagged"]]
    onset_file = onset_rows["file"].iloc[0] if not onset_rows.empty else None
    severity_label, severity_color = _severity_for(current_health, health_z_thresh, onset_flagged)
    recommendation = REPORT_RECOMMENDATIONS.get(result.category, REPORT_RECOMMENDATIONS["Unknown"])

    recent = g.tail(10)
    slope = float(np.polyfit(recent["file_index"], recent["health_indicator"], 1)[0]) if len(recent) >= 3 else 0.0
    if slope > 0.01 and current_health < health_z_thresh:
        eta_hrs = max(0.0, (health_z_thresh - current_health) / slope) * sample_interval_minutes / 60
        eta_text = f"{eta_hrs:.1f} hours at the current degradation rate"
    elif current_health >= health_z_thresh:
        eta_text = "already past the alarm threshold"
    else:
        eta_text = "stable -- no significant degradation trend"

    # --- Chart 1: health index trend (print-friendly static PNG, not the dashboard's interactive Plotly version) ---
    fig1, ax1 = plt.subplots(figsize=(8, 3.2))
    ax1.plot(g["file_index"], g["health_indicator"], color="#1b5e20", linewidth=1.6, label="Health Indicator")
    ax1.axhline(health_z_thresh, color="#c62828", linestyle="--", linewidth=1.2, label=f"Alarm threshold ({health_z_thresh:.1f})")
    if onset_file is not None:
        ax1.axvline(onset_rows["file_index"].iloc[0], color="#ef6c00", linestyle=":", linewidth=1.4, label="Onset flagged")
    ax1.set_xlabel("Reading index (time order)")
    ax1.set_ylabel("Health index (|z| composite)")
    ax1.set_title(f"{sensor_id} -- {channel}: Health Index Trend")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.25)
    chart1_b64 = _fig_to_base64(fig1)

    # --- Chart 2: latest spectral signature (which feature is driving the alarm) ---
    z_vals = latest[z_cols].abs().sort_values(ascending=False)
    fig2, ax2 = plt.subplots(figsize=(8, 3.2))
    colors = ["#c62828" if c == z_vals.index[0] else "#455a64" for c in z_vals.index]
    ax2.barh([c.replace("z_", "") for c in z_vals.index][::-1], z_vals.values[::-1], color=colors[::-1])
    ax2.set_xlabel("|z-score| (deviation from this channel's own baseline)")
    ax2.set_title(f"{sensor_id} -- {channel}: Latest Spectral Signature ({latest['file']})")
    ax2.grid(alpha=0.25, axis="x")
    chart2_b64 = _fig_to_base64(fig2)

    freqs_rows = "".join(f"<tr><td>{k}</td><td>{v:.2f} Hz</td></tr>" for k, v in defect_freqs.items())

    # Full data table -- everything an engineer needs to re-derive the same conclusion by hand
    show_cols = (["file_index", "file", "health_indicator", "onset_flagged"]
                 + [c for c in g.columns if c.startswith("amp_") or c in ("rms", "crest_factor", "kurtosis")]
                 + z_cols)
    data_table_html = g[show_cols].round(4).to_html(index=False, classes="data-table", border=0)

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    onset_text = f"Yes, at <code>{onset_file}</code>" if onset_file else "No"
    ambiguous_note = (
        " -- below the 1.3x confidence cutoff, so this reading is flagged ambiguous rather than confidently named."
        if result.is_ambiguous else " -- a clearly dominant driver."
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>PdM Diagnostic Report -- {sensor_id} ({channel})</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1a1a1a; background: #ffffff; margin: 0; padding: 32px 40px; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  h2 {{ font-size: 16px; border-bottom: 2px solid #1b5e20; padding-bottom: 4px; margin-top: 36px; }}
  h3 {{ font-size: 13px; color: #444; margin-top: 20px; }}
  .meta {{ color: #555; font-size: 13px; margin-bottom: 20px; }}
  .badge {{ display: inline-block; padding: 4px 12px; border-radius: 4px; color: #fff; font-weight: 600; font-size: 13px; background: {severity_color}; }}
  .gridwrap {{ display: flex; gap: 24px; flex-wrap: wrap; margin: 16px 0; }}
  .metric {{ border: 1px solid #ddd; border-radius: 6px; padding: 10px 16px; min-width: 160px; }}
  .metric .label {{ font-size: 11px; color: #777; text-transform: uppercase; }}
  .metric .value {{ font-size: 16px; font-weight: 600; }}
  img {{ max-width: 100%; border: 1px solid #eee; border-radius: 4px; margin: 8px 0 16px; }}
  table.freqs {{ border-collapse: collapse; font-size: 13px; margin: 8px 0 16px; }}
  table.freqs td {{ padding: 4px 12px; border: 1px solid #ddd; }}
  .rec {{ background: #f4f8f4; border-left: 4px solid #1b5e20; padding: 10px 14px; margin: 12px 0; font-size: 14px; }}
  .caveat {{ font-size: 12px; color: #777; margin-top: 24px; }}
  .data-table-wrap {{ max-height: 520px; overflow: auto; border: 1px solid #ddd; margin-top: 12px; }}
  table.data-table {{ border-collapse: collapse; width: 100%; font-size: 11px; }}
  table.data-table th {{ position: sticky; top: 0; background: #1b5e20; color: #fff; padding: 6px 8px; text-align: right; }}
  table.data-table td {{ padding: 4px 8px; text-align: right; border-bottom: 1px solid #eee; white-space: nowrap; }}
  table.data-table tr:nth-child(even) {{ background: #fafafa; }}
  footer {{ margin-top: 40px; font-size: 11px; color: #999; border-top: 1px solid #eee; padding-top: 10px; }}
  @media print {{ body {{ padding: 10px 20px; }} .data-table-wrap {{ max-height: none; overflow: visible; }} }}
</style>
</head><body>

<h1>Predictive Maintenance Diagnostic Report</h1>
<div class="meta">
  Asset / Sensor: <b>{sensor_id}</b> &nbsp;|&nbsp; Channel: <b>{channel}</b> &nbsp;|&nbsp;
  Readings analyzed: <b>{len(g)}</b> &nbsp;|&nbsp; Report generated: {generated}
</div>

<h2>Part 1 -- Automated Machine Insight</h2>
<p><span class="badge">{severity_label}</span> &nbsp; Diagnosis summary: <b>{result.fault}</b> ({result.category})</p>

<div class="gridwrap">
  <div class="metric"><div class="label">Current Health Index</div><div class="value">{current_health:.2f}</div></div>
  <div class="metric"><div class="label">Alarm Threshold</div><div class="value">{health_z_thresh:.1f}</div></div>
  <div class="metric"><div class="label">Est. Time to Critical</div><div class="value">{eta_text}</div></div>
  <div class="metric"><div class="label">Onset Flagged</div><div class="value">{onset_text}</div></div>
</div>

<h3>Health Index Trend</h3>
<img src="data:image/png;base64,{chart1_b64}" alt="health trend">

<h3>Latest Spectral Signature</h3>
<img src="data:image/png;base64,{chart2_b64}" alt="spectral signature">

<p>
  Dominant driver <code>{result.dominant_feature}</code> is {result.confidence_ratio:.2f}x the runner-up
  |z-score|{ambiguous_note} Physically, a deviation dominated by <code>{result.dominant_feature}</code> is
  consistent with <b>{result.fault}</b>, a {result.category.lower()} signature.
</p>

<div class="rec"><b>Suggested next step:</b> {recommendation}</div>

<h3>Reference Bearing/Shaft-Order Frequencies Used (Hz)</h3>
<table class="freqs">{freqs_rows}</table>

<p class="caveat">
  Rule-based classification (dominant |z-score| lookup against DIAGNOSTIC_RULES), not a trained ML model.
  Defect frequencies are fixed to this rig's RPM/bearing geometry constants, and the order-amplitude FFT has
  no Hann/Hamming windowing applied, so some spectral leakage is possible. This is a machine-generated read,
  not a certified vibration analyst's assessment -- use Part 2 below to verify it.
</p>

<h2>Part 2 -- Engineer Verification Data</h2>
<p>
  Every reading behind the summary above: raw time-domain / order-amplitude features, this channel's baseline
  z-scores, the composite health index, and the onset flag -- for independently checking the automated read
  reading-by-reading.
</p>
<div class="data-table-wrap">{data_table_html}</div>

<footer>
  Generated by the Multi-Modal Fleet Diagnostics Engine -- unsupervised, rule-based bearing-fault pipeline
  (RMS / crest factor / kurtosis + 1X-3X shaft order + FTF/BPFO/BPFI/BSF). Not a substitute for a certified
  analyst's ISO 10816-based assessment.
</footer>
</body></html>"""


# ==========================================
# SIDEBAR: SEQUENCE NAVIGATOR
# ==========================================
# Turns the old single, continuously-scrolling page into five discrete steps
# a user clicks through in series -- and, notably, moves Section 5 (Fleet
# Alerts) to its correct place *after* Section 4 in that sequence. In the
# previous single-page layout Section 5's code had to run before Section 4's
# (it defines health_z_thresh, which Section 4 needs), so it visually
# rendered above Section 4 despite being numbered last. That coupling is
# resolved below by reading the threshold widgets' values out of
# session_state (they persist by key whether or not Section 5 is the active
# page), so Section 4 and Section 5 no longer need to be in that order.
NAV_PAGES = [
    ("1", "🆕 1. New Machine"),
    ("2", "🗃️ 2. Fleet Directory"),
    ("3", "🔀 3. Pipeline Routing"),
    ("4", "📊 4. Diagnostics"),
    ("5", "🚨 5. Fleet Alerts"),
]
_page_keys = [k for k, _ in NAV_PAGES]
_page_labels = [label for _, label in NAV_PAGES]

with st.sidebar:
    st.markdown("### 🧭 Sequence Navigator")
    st.caption("Each step calibrates into the next: deploy → select → ingest → diagnose → alert.")
    _current_idx = _page_keys.index(st.session_state.current_page) if st.session_state.current_page in _page_keys else 0
    _chosen_label = st.radio("Go to step:", _page_labels, index=_current_idx, key="nav_radio", label_visibility="collapsed")
    st.session_state.current_page = _page_keys[_page_labels.index(_chosen_label)]
    st.markdown("---")
    if st.session_state.active_sensor:
        st.caption(f"Active sensor: `{st.session_state.active_sensor}`")
    if st.session_state.target_sensor:
        st.caption(f"Diagnostics target: `{st.session_state.target_sensor}`")

page = st.session_state.current_page

# Threshold values live on Section 5's widgets, but Section 4 (alarm line,
# ETA) and the alert-sync below need them regardless of which page is
# active -- so read them by key with sane defaults rather than relying on
# Section 5 having run first in this script pass.
health_z_thresh = st.session_state.get("health_z_thresh_slider", 4.0)
sample_interval_minutes = st.session_state.get("sample_interval_input", 10)

# Keep the fleet alert log in sync every run, not only while Section 5 is
# the visible page, so the Priority Queue / alert count are always current.
zone_lookup = {sid: s.get("Zone", "Unknown") for sid, s in st.session_state.sensors.items()}
if sync_pipeline_alerts(zone_lookup, health_z_thresh):
    save_shared_state(st.session_state.sensors, st.session_state.pipeline_results, st.session_state.alerts)

# ==========================================
# SECTION 1: DEPLOY HARDWARE
# ==========================================
if page == "1":
    st.header("➕ 1. Deploy New Sensor Node to Fleet")
    deploy_tab1, deploy_tab2, deploy_tab3 = st.tabs(["1️⃣ Metadata", "2️⃣ Baseline", "3️⃣ Schema"])

    with deploy_tab1:
        col_m1, col_m2, col_m3 = st.columns(3)
        sensor_id = col_m1.text_input("Sensor ID:", placeholder="e.g., PUMP-04-NODE")
        parent_zone = col_m2.text_input("Parent Machine / Zone:")
        status = col_m3.selectbox("Current Status:", ["🟢 Online", "🔴 Offline", "🟡 Maintenance Downtime"])
        col_k1, col_k2 = st.columns(2)
        machine_cat = col_k1.selectbox("Target Component Category:", list(FAULT_DATABASE.keys()))
        rpm_val = col_k2.number_input("Operating Speed (RPM):", value=3000, step=100)

    with deploy_tab2:
        bench_mode = st.radio("Benchmark Source:", ["Manual Drag & Drop File", "Predefined Path String"], horizontal=True)
        if bench_mode == "Manual Drag & Drop File":
            benchmark_file = st.file_uploader("Upload nominal/normal reference CSV", key="setup_bench_upload")
            bench_source_val = benchmark_file.name if benchmark_file else "None Uploaded"
        else:
            bench_source_val = st.text_input("Enter Server Path to Nominal Data:", placeholder="/data/baselines/pump04_normal.csv")

    with deploy_tab3:
        hardware_type = st.selectbox("Select Sensor Hardware Modality:", list(SENSOR_MODELS.keys()))
        req_format = SENSOR_MODELS[hardware_type]["format"]
        target_faults = st.multiselect("Targeted Root Causes:", options=FAULT_DATABASE[machine_cat], placeholder="Leave blank for Full Sweep")
        if not target_faults: target_faults = ["All (Full Sweep)"]

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Finalize & Deploy Sensor Profile", use_container_width=True):
            if sensor_id and parent_zone:
                st.session_state.sensors[sensor_id] = {
                    "ID": sensor_id, "Zone": parent_zone, "Status": status, "Hardware": hardware_type,
                    "Component": machine_cat, "RPM": rpm_val, "Benchmark": bench_source_val,
                    "Targets": ", ".join(target_faults), "Schema": req_format, "Last_Ping": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_shared_state(st.session_state.sensors, st.session_state.pipeline_results, st.session_state.alerts)
                st.success(f"Node [{sensor_id}] successfully deployed. Continuing to **2. Fleet Directory** →")
                st.session_state.current_page = "2"
                st.rerun()
            else:
                st.error("Sensor ID and Parent Zone are mandatory fields.")

# ==========================================
# SECTION 2: INTERACTIVE FLEET DIRECTORY
# ==========================================
elif page == "2":
    st.header("🗃️ 2. Sensor Fleet Directory")

    if not st.session_state.sensors:
        st.info("No sensors deployed yet -- go to **1. New Machine** to add one.")
    else:
        df_sensors = pd.DataFrame.from_dict(st.session_state.sensors, orient='index')

        f_col1, f_col2, f_col3 = st.columns(3)
        zone_filter = f_col1.multiselect("Filter by Zone", options=df_sensors['Zone'].unique(), key="z_filt")
        status_filter = f_col2.multiselect("Filter by Status", options=df_sensors['Status'].unique(), key="s_filt")
        type_filter = f_col3.multiselect("Filter by Hardware", options=df_sensors['Hardware'].unique(), key="t_filt")

        filtered_df = df_sensors.copy()
        if zone_filter: filtered_df = filtered_df[filtered_df['Zone'].isin(zone_filter)]
        if status_filter: filtered_df = filtered_df[filtered_df['Status'].isin(status_filter)]
        if type_filter: filtered_df = filtered_df[filtered_df['Hardware'].isin(type_filter)]

        st.markdown("*Select a row below to open its diagnostic pipeline in **3. Pipeline Routing**.*")
        selection_event = st.dataframe(
            filtered_df[['Zone', 'ID', 'Status', 'Hardware', 'Component', 'Last_Ping']],
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
        )

        if selection_event.selection.rows:
            st.session_state.active_sensor = filtered_df.iloc[selection_event.selection.rows[0]]['ID']
            st.session_state.current_page = "3"
            st.rerun()

# ==========================================
# SECTION 3: INGESTION ROUTING
# ==========================================
elif page == "3":
    active_sensor = st.session_state.active_sensor
    if not active_sensor or active_sensor not in st.session_state.sensors:
        st.info("No sensor selected yet -- go to **2. Fleet Directory** and pick a row.")
    else:
        s_data = st.session_state.sensors[active_sensor]
        st.header(f"🔀 3. Pipeline Routing: {active_sensor}")
        tab1, tab2 = st.tabs(["📁 Local Folder / Manual Drop", "🔄 Live IIoT Stream & Storage"])

        with tab1:
            ingest_mode = st.radio(
                "Ingest from:",
                ["📁 Local Folder (recommended for full runs)", "📂 Manual File Drop (a handful of files)"],
                horizontal=True, key="ingest_mode"
            )

            if ingest_mode.startswith("📁"):
                st.caption(
                    "The dashboard runs server-side, so it can read a folder straight off disk -- no browser "
                    "upload needed, which matters once a run is thousands of files (IMS set3 alone is 6,324). "
                    "Point it at the same DATA_ROOT / subfolder pair your `run_pipeline.bat` already uses."
                )
                base_dir = st.text_input(
                    "Data Root (folder containing your dataset subfolders):",
                    value=os.environ.get("IMS_DATA_ROOT", ""),
                    placeholder=r"C:\work folder\PdM (DATABASE)  or  /home/user/pdm/data",
                    key="base_dir_input",
                )
                subfolders = []
                if base_dir:
                    if os.path.isdir(base_dir):
                        subfolders = sorted(
                            d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))
                        )
                        if not subfolders:
                            st.warning("That folder exists but has no subfolders in it.")
                    else:
                        st.warning("That path doesn't exist on the machine running `streamlit run` -- double-check it (and that it isn't a browser-side path).")

                col_f1, col_f2 = st.columns([2, 1])
                chosen_subfolder = col_f1.selectbox("Dataset subfolder:", subfolders) if subfolders else None
                n_ch_folder = col_f2.number_input(
                    "Channels/file:", value=HARDWARE_CHANNEL_MAP.get(s_data['Hardware'], 4), min_value=1, max_value=8, key="n_ch_folder"
                )
                save_to_disk = st.checkbox(
                    "Also save CSV + plots + report to disk (same outputs/<subfolder>/ location the CLI uses)",
                    key="save_folder_run",
                )
                out_root = st.text_input(
                    "Output Root:", value=os.environ.get("IMS_OUTPUT_ROOT", ""), placeholder=r"...\PdM\outputs",
                    key="out_root_input", disabled=not save_to_disk,
                )

                if st.button("Run Analysis on Folder", use_container_width=True, disabled=not chosen_subfolder):
                    if not PIPELINE_AVAILABLE:
                        st.error("pipeline/ package wasn't found next to app.py, so real order-analysis can't run.")
                    else:
                        full_path = os.path.join(base_dir, chosen_subfolder)
                        with st.spinner(f"Running ingest -> features -> health -> alarm -> classify on {chosen_subfolder}..."):
                            trend = build_trend_table(full_path, int(n_ch_folder))
                            trend = flag_onset(trend)
                        st.session_state.pipeline_results[active_sensor] = trend
                        st.session_state.target_sensor = active_sensor
                        st.session_state.analysis_ready = True
                        save_shared_state(st.session_state.sensors, st.session_state.pipeline_results, st.session_state.alerts)

                        if save_to_disk and out_root:
                            run_out_dir = resolve_out_dir(out_root, full_path)
                            os.makedirs(run_out_dir, exist_ok=True)
                            trend.to_csv(os.path.join(run_out_dir, "ims_feature_trend.csv"), index=False)
                            plot_trends(trend, run_out_dir)
                            write_reports(trend, run_out_dir)
                            st.info(f"Saved CSV, plots, and Markdown reports to `{run_out_dir}` -- identical layout to a `run_pipeline.bat` run.")

                        st.success(f"Analyzed `{chosen_subfolder}` ({len(trend)} rows). Continuing to **4. Diagnostics** →")
                        st.session_state.current_page = "4"
                        st.rerun()
            else:
                st.caption(
                    "Tab-separated, one file per timestamp -- same convention ims_pipeline.py expects. "
                    f"Hardware profile implies {HARDWARE_CHANNEL_MAP.get(s_data['Hardware'], 1)} channel(s) per file. "
                    "Fine for a quick test batch; use the Local Folder tab for a full run."
                )
                manual_files = st.file_uploader(
                    f"Drop {s_data['Hardware']} format data below:", key="dropzone", accept_multiple_files=True
                )
                if st.button("Run Manual Analysis", use_container_width=True, disabled=not manual_files):
                    if not PIPELINE_AVAILABLE:
                        st.error("ims_pipeline.py wasn't found next to app.py, so real order-analysis can't run.")
                    else:
                        with st.spinner("Running ingest -> features -> health -> alarm -> classify..."):
                            with tempfile.TemporaryDirectory() as tmpdir:
                                for f in manual_files:
                                    with open(os.path.join(tmpdir, f.name), "wb") as out_f:
                                        out_f.write(f.getbuffer())
                                n_ch = HARDWARE_CHANNEL_MAP.get(s_data['Hardware'], 1)
                                trend = build_trend_table(tmpdir, n_ch)
                                trend = flag_onset(trend)
                        st.session_state.pipeline_results[active_sensor] = trend
                        st.session_state.target_sensor = active_sensor
                        st.session_state.analysis_ready = True
                        save_shared_state(st.session_state.sensors, st.session_state.pipeline_results, st.session_state.alerts)
                        st.success(f"Analyzed {len(manual_files)} snapshots. Continuing to **4. Diagnostics** →")
                        st.session_state.current_page = "4"
                        st.rerun()

            if st.button("🎲 Use Demo Data (no files needed)", use_container_width=True):
                st.session_state.pipeline_results[active_sensor] = build_demo_trend(active_sensor)
                st.session_state.target_sensor = active_sensor
                st.session_state.analysis_ready = True
                st.success("Demo trend generated. Continuing to **4. Diagnostics** →")
                st.session_state.current_page = "4"
                st.rerun()

        with tab2:
            col_stream1, col_stream2 = st.columns(2)
            stream_path = col_stream1.text_input("Input MQTT Stream Path:", value=f"/factory/stream/{active_sensor}")
            output_path = col_stream2.text_input("Automated Output Storage Path:", value=f"s3://analytics-bucket/{active_sensor}/")

            if st.button("Initialize Automated Pipeline"):
                st.session_state.target_sensor = active_sensor
                st.session_state.analysis_ready = True
                st.info(
                    f"This wires to `pipeline.py` writing `ims_feature_trend.csv`-style output to `{output_path}` on a "
                    "schedule -- not yet connected in this prototype. Use 'Manual Diagnostics' or demo data for now."
                )

# ==========================================
# SECTION 4: INTERACTIVE RESULTS & REPORTING
# ==========================================
elif page == "4":
    if not (st.session_state.analysis_ready and st.session_state.target_sensor):
        st.info("No diagnostics yet -- run an analysis in **3. Pipeline Routing**, or select an alert in **5. Fleet Alerts**.")
    else:
        active_target = st.session_state.target_sensor
        st.header(f"📊 4. Interactive Diagnostics: {active_target}")

        trend_df = st.session_state.pipeline_results.get(active_target)
        g_all = None
        if trend_df is not None:
            channels = sorted(trend_df['channel'].unique())
            chan = st.selectbox("Channel", channels, key="health_chan_select")
            g_all = trend_df[trend_df['channel'] == chan].sort_values('file_index').reset_index(drop=True)
        else:
            st.info("No pipeline output for this sensor yet -- run analysis or demo data in Section 3.")

        res_tab1, res_tab2, res_tab3, res_tab4 = st.tabs([
            "📈 Health Index Trend", "🔍 Spectral Analysis", "⚠️ Uncategorized Anomalies", "📤 Export Report"
        ])

        with res_tab1:
            st.subheader("Machine Health Degradation")
            if g_all is None:
                st.caption("Waiting on pipeline output.")
            else:
                current_health = float(g_all["health_indicator"].iloc[-1])
                recent = g_all.tail(10)
                slope = float(np.polyfit(recent["file_index"], recent["health_indicator"], 1)[0]) if len(recent) >= 3 else 0.0

                fig_health = go.Figure()
                fig_health.add_trace(go.Scatter(
                    x=g_all['file_index'], y=g_all['health_indicator'],
                    mode='lines+markers', line=dict(color='#00ff80'), name="Health Indicator"
                ))
                fig_health.add_hline(y=health_z_thresh, line_dash="dash", line_color="red", annotation_text="Alarm Threshold")
                onset_rows = g_all[g_all['onset_flagged']]
                if not onset_rows.empty:
                    fig_health.add_vline(x=onset_rows['file_index'].iloc[0], line_dash="dot", line_color="orange", annotation_text="Onset")
                fig_health.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_health, use_container_width=True)

                m1, m2, m3 = st.columns(3)
                m1.metric("Current Health Index", f"{current_health:.2f}", delta=f"{slope:+.3f} / reading")
                if slope > 0.01 and current_health < health_z_thresh:
                    eta_hrs = max(0.0, (health_z_thresh - current_health) / slope) * sample_interval_minutes / 60
                    m2.metric("Est. Time to Critical", f"{eta_hrs:.1f} hrs")
                elif current_health >= health_z_thresh:
                    m2.metric("Est. Time to Critical", "Already past threshold")
                else:
                    m2.metric("Est. Time to Critical", "Stable")
                m3.metric("Alarm State", "🚨 Flagged" if bool(g_all['onset_flagged'].iloc[-1]) else "🟢 Normal")

        with res_tab2:
            st.subheader("Categorized Faults (Order/FFT Signature)")
            if g_all is None:
                st.caption("Waiting on pipeline output.")
            else:
                latest = g_all.iloc[-1]
                z_cols = [c for c in g_all.columns if c.startswith('z_')]
                result = classify_row(latest, z_cols)
                z_vals = latest[z_cols].abs().sort_values(ascending=False)

                if latest['onset_flagged'] and not result.is_ambiguous:
                    st.error(
                        f"**Rule-Based Classification:** dominant driver `{result.dominant_feature}` "
                        f"(|z|={z_vals.iloc[0]:.1f}) → **{result.fault}** _({result.category})_"
                    )
                elif latest['onset_flagged']:
                    st.warning(f"**Ambiguous signature** -- top driver `{result.dominant_feature}` is only {result.confidence_ratio:.1f}x the runner-up. See the Uncategorized Anomalies tab.")
                else:
                    st.success("No sustained onset flagged -- current signature is within baseline variation.")

                fig_spec = go.Figure(go.Bar(
                    x=z_vals.values, y=[c.replace('z_', '') for c in z_vals.index], orientation='h',
                    marker_color=['#ff4d4d' if c == z_vals.index[0] else '#00c86e' for c in z_vals.index]
                ))
                fig_spec.update_layout(
                    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    title="Feature deviation from baseline (|z-score|)", xaxis_title="|z|"
                )
                st.plotly_chart(fig_spec, use_container_width=True)

                if DEFECT_FREQS:
                    freqs_str = ", ".join(f"{k}≈{v:.1f} Hz" for k, v in DEFECT_FREQS.items())
                    st.caption(
                        f"Theoretical defect frequencies for the IMS rig geometry: {freqs_str}. "
                        "These are fixed to that rig's RPM/bearing constants -- a fleet-ready version would "
                        "recompute them per sensor from its own RPM (already captured on deploy) and bearing geometry."
                    )

        with res_tab3:
            st.subheader("Engineer's Error & Anomaly Report")
            if g_all is None:
                st.caption("Waiting on pipeline output.")
            else:
                z_cols = [c for c in g_all.columns if c.startswith('z_')]

                g_check = g_all.copy()
                g_check['confidence_ratio'] = g_check.apply(
                    lambda row: classify_row(row, z_cols).confidence_ratio, axis=1
                )
                ambiguous = g_check[g_check['onset_flagged'] & (g_check['confidence_ratio'] < 1.3)]

                st.markdown(
                    "Flagged readings where no single feature clearly dominates (top driver isn't at least "
                    "1.3x the runner-up) -- the rule table can't confidently name these; they're "
                    "broadband/general-wear signatures instead of one classic fault."
                )
                if ambiguous.empty:
                    st.success("No ambiguous readings -- every flagged point has one clearly dominant driver.")
                else:
                    st.warning(f"⚠️ {len(ambiguous)} flagged reading(s) lack a clear dominant driver.")
                    st.dataframe(
                        ambiguous[['file', 'health_indicator', 'confidence_ratio']].rename(
                            columns={'health_indicator': 'Health Index', 'confidence_ratio': 'Top/2nd Ratio', 'file': 'File'}
                        ),
                        use_container_width=True, hide_index=True
                    )
                    st.button("Flag for Machine Learning Pipeline Training", key="flag_ml")

        with res_tab4:
            st.subheader("Export Diagnostic Report")
            st.markdown(
                "One file, two insights: **Part 1** is the automated machine read -- health trend, "
                "spectral signature, and the rule-based cause -- for a fast go/no-go decision. "
                "**Part 2** is the full underlying data (every raw feature and z-score) so an engineer "
                "can independently verify that read reading-by-reading, not just take it on faith."
            )
            if g_all is None:
                st.caption("Waiting on pipeline output.")
            else:
                report_key = f"report_html_{active_target}_{chan}"
                if st.button("📄 Generate Report", use_container_width=True, key="gen_report_btn"):
                    with st.spinner("Building report -- rendering charts and assembling the data appendix..."):
                        st.session_state[report_key] = build_diagnostic_report_html(
                            g_all, active_target, chan, health_z_thresh, sample_interval_minutes, DEFECT_FREQS
                        )
                    st.success("Report ready -- download below.")

                if report_key in st.session_state:
                    st.download_button(
                        "⬇️ Download Report (HTML)",
                        data=st.session_state[report_key],
                        file_name=f"PdM_Report_{active_target}_{chan}_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
                        mime="text/html",
                        use_container_width=True,
                    )
                    st.caption(
                        "Opens in any browser. For a PDF copy, open the file and use the browser's "
                        "Print → Save as PDF (the report has a print-friendly layout built in)."
                    )

# ==========================================
# SECTION 5: FLEET ALERTS & THRESHOLD HISTORY
# ==========================================
elif page == "5":
    st.header("🚨 5. Fleet Alerts & Historical Telemetry")

    with st.expander("⚙️ Configure Operational Thresholds", expanded=False):
        st.markdown(
            "ISO-style **mm/s velocity limits** apply to classic single-value vibration sensors. "
            "The **composite health index** is a separate, self-referential z-score baselined against "
            "each asset's own early-life data (what the pipeline's Section 4 output is measured in) -- "
            "not the same unit, so it gets its own alarm line. Note this slider only drives the dashboard's "
            "display, priority-queue ETA and severity labels; it doesn't re-run the pipeline's own onset "
            "detection (fixed at `z_thresh=4.0` inside ims_pipeline.py unless you edit that default)."
        )
        col_t1, col_t2, col_t3 = st.columns(3)
        vib_warning = col_t1.slider("Vibration Warning (mm/s)", 1.0, 10.0, 4.5, 0.1)
        vib_critical = col_t2.slider("Vibration Critical (mm/s)", 5.0, 15.0, 7.1, 0.1)
        temp_limit = col_t3.slider("Temperature Limit (°C)", 40, 120, 85, 1)
        col_t4, col_t5 = st.columns(2)
        # Explicit keys so these values persist in session_state and stay
        # readable from Section 4 / the alert-sync above even when this
        # (Section 5) page isn't the one currently on screen.
        health_z_thresh = col_t4.slider("Composite Health Index Alarm (z-score)", 2.0, 8.0, 4.0, 0.1, key="health_z_thresh_slider")
        sample_interval_minutes = col_t5.number_input("Snapshot Interval (minutes)", value=10, min_value=1, step=1, key="sample_interval_input")
        if st.button("Apply Global Thresholds"):
            st.success("Thresholds synced to backend engine.")

    # --- Maintenance priority queue: the actual decision this section exists to drive ---
    st.markdown("#### 🎯 Maintenance Priority Queue (soonest-to-critical first)")
    priority_rows = []
    for sid, df in st.session_state.pipeline_results.items():
        for chan, g in df.groupby("channel"):
            g = g.sort_values("file_index")
            current = float(g["health_indicator"].iloc[-1])
            recent = g.tail(10)
            slope = float(np.polyfit(recent["file_index"], recent["health_indicator"], 1)[0]) if len(recent) >= 3 else 0.0
            if bool(g["onset_flagged"].iloc[-1]) and current >= health_z_thresh:
                eta_readings, trend_label = 0.0, "🚨 Already critical"
            elif slope > 0.01 and current < health_z_thresh:
                eta_readings, trend_label = max(0.0, (health_z_thresh - current) / slope), "📈 Worsening"
            else:
                continue
            priority_rows.append({
                "Sensor": f"{sid} ({chan})",
                "Zone": zone_lookup.get(sid, "Unknown"),
                "Current Health (z)": round(current, 2),
                "Trend": trend_label,
                "Est. Time to Critical (hrs)": round(eta_readings * sample_interval_minutes / 60, 1),
            })

    if priority_rows:
        st.dataframe(
            pd.DataFrame(priority_rows).sort_values("Est. Time to Critical (hrs)"),
            use_container_width=True, hide_index=True
        )
        st.caption("Service the top row first -- it's projected to cross the alarm threshold soonest at its current degradation rate.")
    else:
        st.caption("No analyzed sensor is currently trending toward its alarm threshold.")

    df_alerts = pd.DataFrame(st.session_state.alerts)

    # Filters specific to the Alerts table
    a_col1, a_col2, a_col3 = st.columns(3)
    a_zone = a_col1.multiselect("Filter Alerts by Zone", options=df_alerts['Zone'].unique())
    a_sensor = a_col2.multiselect("Filter Alerts by Sensor", options=df_alerts['Sensor_ID'].unique())
    a_sev = a_col3.multiselect("Filter Alerts by Severity", options=df_alerts['Severity'].unique())

    filtered_alerts = df_alerts.copy()
    if a_zone: filtered_alerts = filtered_alerts[filtered_alerts['Zone'].isin(a_zone)]
    if a_sensor: filtered_alerts = filtered_alerts[filtered_alerts['Sensor_ID'].isin(a_sensor)]
    if a_sev: filtered_alerts = filtered_alerts[filtered_alerts['Severity'].isin(a_sev)]

    st.markdown("*Select an alert below to jump to its full analytical report in **4. Diagnostics**.*")
    display_cols = [c for c in filtered_alerts.columns if c != "_key"]
    alert_event = st.dataframe(
        filtered_alerts[display_cols], use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
    )

    # If a user clicks an alert here, it overrides Section 3's target and jumps to Section 4
    if alert_event.selection.rows:
        clicked_sensor_label = filtered_alerts.iloc[alert_event.selection.rows[0]]['Sensor_ID']
        clicked_sensor = clicked_sensor_label.split(" (")[0]
        st.session_state.target_sensor = clicked_sensor
        st.session_state.analysis_ready = True
        st.session_state.current_page = "4"
        st.rerun()
