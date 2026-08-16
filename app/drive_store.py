r"""
Shared persistent storage, backed by one Google Drive JSON file
==================================================================
Lets every visitor of the deployed dashboard see the same sensors /
analysis results / alerts, instead of each browser tab starting from an
empty fleet. Visitors never touch Drive directly or need a Google account
-- they only ever talk to this Streamlit app, which holds the one Google
service-account key and reads/writes the shared file on everyone's behalf.

Setup (service account, API key, Streamlit secrets): see SETUP_DRIVE.md
in the repo root.

Known limitations (fine for a portfolio-scale demo, not a real database):
  - Last write wins. If two visitors trigger a save in the same second,
    one can overwrite the other.
  - The whole fleet state round-trips as one JSON file on every save/load
    -- convenient for a handful of sensors and a few hundred rows each,
    not meant for large-scale production fleet data.
"""

import io
import json
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
    _GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    _GOOGLE_LIBS_AVAILABLE = False

FILE_NAME = "pdm_fleet_state.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]


def drive_configured() -> bool:
    """True only if the google-api libraries are installed AND a
    gcp_service_account secret is present. Lets app.py skip Drive calls
    (and stay silent about it) when running locally without secrets set up."""
    return _GOOGLE_LIBS_AVAILABLE and "gcp_service_account" in st.secrets


@st.cache_resource(show_spinner=False)
def _get_service():
    creds = service_account.Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _find_file_id(service, debug: bool = False) -> Optional[str]:
    folder_id = st.secrets.get("gcp_drive_folder_id")
    query = f"name = '{FILE_NAME}' and trashed = false"
    if folder_id:
        query += f" and '{folder_id}' in parents"
    result = service.files().list(q=query, spaces="drive", fields="files(id, name, parents, owners)").execute()
    files = result.get("files", [])
    if debug:
        st.sidebar.info(
            f"**Drive debug**\n\n"
            f"- folder_id secret: `{folder_id!r}`\n"
            f"- query: `{query}`\n"
            f"- files found: {len(files)}\n"
            + "\n".join(f"  - {f}" for f in files)
        )
    return files[0]["id"] if files else None


def _describe_error(e: Exception) -> str:
    """Pull the actual HTTP status + reason out of an HttpError instead of
    just showing the generic exception class name."""
    if _GOOGLE_LIBS_AVAILABLE and isinstance(e, HttpError):
        status = getattr(e.resp, "status", "?")
        try:
            reason = e.error_details[0].get("reason", "") if e.error_details else ""
        except Exception:
            reason = ""
        detail = f"HTTP {status}"
        if reason:
            detail += f" ({reason})"
        if reason == "storageQuotaExceeded":
            detail += (
                " -- service accounts have no Drive storage of their own. Create "
                f"an empty {FILE_NAME} yourself in the shared folder (as your own "
                "account) so the app only ever updates it, never creates it."
            )
        return detail
    return e.__class__.__name__


def load_state() -> Optional[Dict[str, Any]]:
    """Returns {"sensors": dict, "pipeline_results": {sensor_id: DataFrame},
    "alerts": list}, or None if Drive isn't configured/reachable -- caller
    should fall back to empty local-only defaults in that case."""
    if not drive_configured():
        return None
    try:
        service = _get_service()
        file_id = _find_file_id(service, debug=st.secrets.get("gcp_debug", False))
        if file_id is None:
            return {"sensors": {}, "pipeline_results": {}, "alerts": []}

        request = service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buf.seek(0)
        raw = json.loads(buf.read().decode("utf-8"))

        pipeline_results = {
            sid: pd.DataFrame(records) for sid, records in raw.get("pipeline_results", {}).items()
        }
        return {
            "sensors": raw.get("sensors", {}),
            "pipeline_results": pipeline_results,
            "alerts": raw.get("alerts", []),
        }
    except Exception as e:
        print(f"[drive_store] load_state failed: {e!r}")
        st.sidebar.warning(f"Shared storage unavailable ({_describe_error(e)}) -- running local-only this session.")
        return None


def save_state(sensors: dict, pipeline_results: Dict[str, pd.DataFrame], alerts: List[dict]) -> bool:
    """Best-effort save; returns True on success. Never raises -- a failed
    save shouldn't crash the dashboard, it just means this session's
    changes stay local instead of shared with other visitors."""
    if not drive_configured():
        return False
    try:
        service = _get_service()
        payload = {
            "sensors": sensors,
            "pipeline_results": {sid: df.to_dict(orient="records") for sid, df in pipeline_results.items()},
            "alerts": alerts,
        }
        raw_bytes = json.dumps(payload, default=str).encode("utf-8")
        media = MediaIoBaseUpload(io.BytesIO(raw_bytes), mimetype="application/json", resumable=False)

        file_id = _find_file_id(service, debug=st.secrets.get("gcp_debug", False))
        if file_id:
            service.files().update(fileId=file_id, media_body=media).execute()
        else:
            folder_id = st.secrets.get("gcp_drive_folder_id")
            if not folder_id:
                print("[drive_store] save_state: gcp_drive_folder_id secret is missing or empty.")
                st.sidebar.warning(
                    "Shared storage misconfigured: gcp_drive_folder_id secret is missing. "
                    "Service accounts have no Drive storage of their own -- a shared folder ID "
                    "is required. Check your Streamlit secrets for a top-level "
                    'gcp_drive_folder_id = "..." line (outside the [gcp_service_account] block).'
                )
                return False
            metadata = {"name": FILE_NAME, "parents": [folder_id]}
            service.files().create(body=metadata, media_body=media, fields="id").execute()
        return True
    except Exception as e:
        print(f"[drive_store] save_state failed: {e!r}")
        st.sidebar.warning(f"Couldn't save to shared storage ({_describe_error(e)}) -- your change stays visible to you this session, but may not persist for others.")
        return False
