r"""
Stage 0 -- Physical constants
==============================
The only file in the pipeline that hard-codes rig/bearing physics. Every
other stage imports DEFECT_FREQS from here instead of recomputing it, so
there's exactly one place to change when the geometry changes.

`bearing_defect_frequencies()` takes the IMS test rig's numbers as defaults
but accepts overrides -- this is what a future per-sensor fleet version
would call with each sensor's own RPM + bearing spec instead of these
fixed constants (see PROJECT_NOTES.md open items).
"""

import numpy as np

# ----------------------------------------------------------------------
# IMS test rig constants (from dataset documentation)
# ----------------------------------------------------------------------
FS = 20_000              # sampling rate, Hz
SHAFT_RPM = 2000          # constant operating speed
SHAFT_HZ = SHAFT_RPM / 60

N_ROLLERS = 16
ROLLER_DIA_IN = 0.331
PITCH_DIA_IN = 2.815
CONTACT_ANGLE_DEG = 15.17


def bearing_defect_frequencies(
    shaft_hz: float = SHAFT_HZ,
    n_rollers: int = N_ROLLERS,
    roller_dia_in: float = ROLLER_DIA_IN,
    pitch_dia_in: float = PITCH_DIA_IN,
    contact_angle_deg: float = CONTACT_ANGLE_DEG,
) -> dict:
    """Classic rolling-element defect frequencies (FTF/BPFO/BPFI/BSF) from
    shaft speed + bearing geometry. Defaults reproduce the fixed IMS rig."""
    angle_rad = np.deg2rad(contact_angle_deg)
    ratio = (roller_dia_in / pitch_dia_in) * np.cos(angle_rad)

    ftf = 0.5 * shaft_hz * (1 - ratio)
    bpfo = 0.5 * n_rollers * shaft_hz * (1 - ratio)
    bpfi = 0.5 * n_rollers * shaft_hz * (1 + ratio)
    bsf = (pitch_dia_in / (2 * roller_dia_in)) * shaft_hz * (1 - ratio ** 2)
    return {"FTF_hz": ftf, "BPFO_hz": bpfo, "BPFI_hz": bpfi, "BSF_hz": bsf}


DEFECT_FREQS = bearing_defect_frequencies()
