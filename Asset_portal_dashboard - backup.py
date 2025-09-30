#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Asset Management Dashboard – Flask app (Asset-portal-dashboard.py)

Run locally:
  python Asset-portal-dashboard.py

Open:
  http://127.0.0.1:8002
"""

import os
import sys
import re
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from flask import (
    Flask, render_template, redirect, url_for, flash,
    request, abort, Response, jsonify, send_from_directory
)
from markupsafe import Markup

# ------------------ Optional chart modules ------------------
# We now need to handle THREE potential modules
CHARTS_AVAILABLE = False
AI_STATUS_AVAILABLE = False
COMPLETENESS_CHART_AVAILABLE = False
CHARTS_IMPORT_ERROR = ""

try:
    from charts import approval as approval_mod
    CHARTS_AVAILABLE = True
except Exception as _e:
    CHARTS_IMPORT_ERROR = str(_e)

try:
    # --- [CRITICAL CHANGE] ---
    # Changed 'ai_status_table' to 'ai_status_table_new_version' and aliased it.
    from charts import ai_status_table_new_version as ai_status_table
    AI_STATUS_AVAILABLE = True
except Exception as _e:
    # Append the error if one already exists
    error_msg = str(_e)
    if CHARTS_IMPORT_ERROR and error_msg not in CHARTS_IMPORT_ERROR:
         CHARTS_IMPORT_ERROR = f"{CHARTS_IMPORT_ERROR} | {error_msg}"
    else:
        CHARTS_IMPORT_ERROR = error_msg

# --- ADDED THIS NEW TRY/EXCEPT BLOCK ---
try:
    from charts import completeness_score as completeness_mod
    COMPLETENESS_CHART_AVAILABLE = True
except Exception as _e:
    error_msg = f"Completeness Chart Error: {str(_e)}"
    if CHARTS_IMPORT_ERROR and error_msg not in CHARTS_IMPORT_ERROR:
         CHARTS_IMPORT_ERROR = f"{CHARTS_IMPORT_ERROR} | {error_msg}"
    else:
        CHARTS_IMPORT_ERROR = error_msg
# --- END NEW BLOCK ---


# ------------------ Flask app ------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

# ------------------ Cards shown on the dashboard ------------------
APPS = [
    {"key": "capture",     "name": "Asset Capture Mobile App",           "url": "https://appprod.assetcap.facilities.ubc.ca"},
    {"key": "review_me",   "name": "Asset Reviewer - Mechanical",        "url": "https://reviewme.assetcap.facilities.ubc.ca"},
    {"key": "review_bf",   "name": "Asset Reviewer - Backflow Devices",  "url": "https://reviewbf.assetcap.facilities.ubc.ca"},
    {"key": "review_el",   "name": "Asset Reviewer - Electrical",        "url": "https://reviewel.assetcap.facilities.ubc.ca"},
    {"key": "sdi_process", "name": "SDI Process Application",            "url": "https://sdiprocess.assetcap.facilities.ubc.ca"},
]

# ------------------ Log directory ------------------
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ------------------ Runner helpers ------------------
def _windows_detached_flags() -> int:
    if sys.platform.startswith("win"):
        return 0x00000200 | 0x00000008
    return 0

def _cmd_script_path(cmd: List[str]) -> Optional[Path]:
    # Look for .py or .sh scripts in the command list
    for part in cmd:
        if part.lower().endswith((".py", ".sh")):
            try:
                return Path(part).resolve()
            except Exception:
                return Path(part)
    return None

def _launch_cmd_detached(cmd: List[str], cwd: Optional[Path]) -> Path:
    timestamp = int(time.time())
    
    # Prioritize the Python script name for the log file for clarity
    py_script_path = next((p for p in cmd if p.lower().endswith(".py")), None)
    if py_script_path:
        stem = Path(py_script_path).stem
    else:
        script_path = _cmd_script_path(cmd)
        stem = script_path.stem if script_path else "task"
        
    log_path = LOG_DIR / f"{stem}.{timestamp}.log"

    log_fp = open(log_path, "w", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    subprocess.Popen(
        cmd, cwd=str(cwd) if cwd else None, stdout=log_fp,
        stderr=subprocess.STDOUT, shell=False,
        creationflags=_windows_detached_flags(), env=env
    )
    return log_path

# ------------------ Script locations ------------------
def _get_api_root() -> Path:
    return Path(os.environ.get("QR_API_ROOT", "/home/developer/API"))

def _build_tasks() -> Dict[str, Dict]:
    """
    Builds the task dictionary using a wrapper script to ensure the
    virtual environment is properly activated for each interpreter task.
    """
    api_root = _get_api_root()
    
    wrapper_script = api_root / "run_interpreter.sh"

    me_script = api_root / "API_interface_ME_ver00.py"
    bf_script = api_root / "API_interface_BF_ver00.py"
    el_script = api_root / "API_interface_EL_ver00.py"

    tasks: Dict[str, Dict] = {}
    
    tasks["qr_api_me"] = {"cmd": ["/bin/bash", str(wrapper_script), str(me_script)], "cwd": api_root, "label": "AI Interpreter – Mechanical"}
    tasks["qr_api_bf"] = {"cmd": ["/bin/bash", str(wrapper_script), str(bf_script)], "cwd": api_root, "label": "AI Interpreter – Backflow"}
    tasks["qr_api_el"] = {"cmd": ["/bin/bash", str(wrapper_script), str(el_script)], "cwd": api_root, "label": "AI Interpreter – Electrical"}
    
    # Updated task definition with the correct filename
    update_script = api_root / "updating_process_database.py" 
    tasks["update_db"] = {
        "cmd": ["/bin/bash", str(wrapper_script), str(update_script)],
        "cwd": api_root,
        "label": "Update DB from Photos & JSON"
    }
    
    return tasks

TASKS = _build_tasks()

def _validate_task_key(task_key: str) -> Dict:
    if task_key not in TASKS:
        abort(404, f"Unknown task: {task_key}")
    task = TASKS[task_key]
    
    # Validate that the actual python script exists, not just the wrapper
    py_script_path_str = next((p for p in task.get("cmd", []) if p.lower().endswith(".py")), None)
    if not py_script_path_str or not Path(py_script_path_str).exists():
        print(f"ERROR: Python script for task '{task_key}' not found at: {py_script_path_str}")
        raise FileNotFoundError(f"Python script for {task_key} not found.")
        
    return task

def _extract_ts_from_logname(name: str) -> Optional[str]:
    stem = Path(name).stem
    parts = stem.rsplit(".", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[1]
    return None

def _safe_log_path(name: str) -> Path:
    p = (LOG_DIR / name).resolve()
    if not p.exists() or p.parent != LOG_DIR.resolve():
        abort(404, "Log not found")
    return p

# ------------------ Chart helpers ------------------
def _get_building_options() -> List[str]:
    if not CHARTS_AVAILABLE: return ["All"]
    try: return approval_mod.building_options()
    except Exception: return ["All"]

# ------------------ Routes: Dashboard + Chart ------------------
@app.get("/")
def index():
    building = request.args.get("building", "All")
    options = _get_building_options()
    if building not in options: building = "All"
    task_labels = {k: v.get("label", k) for k, v in TASKS.items()}
    ts = int(time.time())

    summary_data, details_data = None, None
    print("\n--- [Dashboard Load] ---")
    if AI_STATUS_AVAILABLE:
        print("Attempting to fetch pending assets from 'ai_status_table' module...")
        try:
            summary, details = ai_status_table.get_pending_assets()
            if summary is not None and not summary.empty:
                summary_data = summary.to_dict(orient="records")
                print(f"SUCCESS: Loaded {len(summary_data)} summary rows.")
            else:
                 print("INFO: No summary data returned from module.")
            if details is not None and not details.empty:
                details_data = details.to_dict(orient="records")
                print(f"SUCCESS: Loaded {len(details_data)} detailed asset rows.")
            else:
                 print("INFO: No detailed data returned from module.")
        except Exception as e:
            print(f"CRITICAL ERROR fetching asset data: {e}")
    else:
        print("WARNING: 'ai_status_table' not available, skipping asset data fetch.")
    
    print("--- [Rendering Template] ---")

    return render_template(
        "dashboard.html", apps=APPS, task_labels=task_labels,
        chart_enabled=CHARTS_AVAILABLE, charts_error=CHARTS_IMPORT_ERROR,
        building_options=options, selected_building=building, ts=ts,
        ai_status_summary=summary_data,
        ai_asset_details=details_data,
        completeness_chart_enabled=COMPLETENESS_CHART_AVAILABLE
    )

@app.get("/chart/approval.png")
def approval_chart():
    if not CHARTS_AVAILABLE:
        return Response("Chart module unavailable", status=503, mimetype="text/plain")
    building = request.args.get("building", "All")
    chart_type = request.args.get("chart_type", "all") 
    try:
        png_bytes = approval_mod.render_chart_png(building=building, chart_type=chart_type)
        resp = Response(png_bytes, mimetype="image/png")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp
    except Exception as e:
        print(f"Chart error for type '{chart_type}': {e}")
        return Response(f"Chart error: {e}", status=500, mimetype="text/plain")

@app.get("/chart/completeness.png")
def completeness_chart():
    if not COMPLETENESS_CHART_AVAILABLE:
        return Response("Completeness chart module unavailable", status=503, mimetype="text/plain")
    
    building = request.args.get("building", "All")
    try:
        png_bytes = completeness_mod.render_chart_png(building=building)
        if not png_bytes:
             return Response("No data for this chart", status=200, mimetype="text/plain")
        
        resp = Response(png_bytes, mimetype="image/png")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp
    except Exception as e:
        print(f"Completeness chart error for building '{building}': {e}")
        return Response(f"Chart error: {e}", status=500, mimetype="text/plain")

# ------------------ Routes: Run Tasks ------------------
@app.post("/run/<task_key>")
def run_task(task_key: str):
    try:
        task = _validate_task_key(task_key)
        log_path = _launch_cmd_detached(task["cmd"], task.get("cwd"))
        return jsonify({"success": True, "log_name": log_path.name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.get("/log_status/<name>")
def log_status(name: str):
    try:
        path = _safe_log_path(name)
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        lines = [line for line in text.splitlines() if line.strip()]
        last_line = lines[-1] if lines else ""

        if "Traceback (most recent call last):" in text or "Error:" in text or "ModuleNotFoundError" in text:
            return jsonify({"status": "error"})
        
        success_keywords = ["Saved", "Total assets found", "Finished", "Completed", "Done", "SUMMARY", "Successfully updated database", "Success! Updated"]
        if any(keyword.lower() in text.lower() for keyword in success_keywords):
             if any(keyword.lower() in last_line.lower() for keyword in success_keywords):
                return jsonify({"status": "success"})

        return jsonify({"status": "running"})
    except Exception:
        return jsonify({"status": "error"}), 404

# ------------------ Friendly Logs UI ------------------
def _title_from_logname(name: str) -> str:
    base = Path(name).stem.rsplit(".", 1)[0]
    is_interpreter = "API_interface" in base
    is_data_task = "updating_process_database" in base

    if is_data_task:
        return "Data Processing Task"
    
    kind = "API Interpreter" if is_interpreter else "Task"
    
    suffix = ""
    base_upper = base.upper()
    if "ME" in base_upper: suffix = " – ME"
    elif "BF" in base_upper: suffix = " – BF"
    elif "EL" in base_upper: suffix = " – EL"
    return f"{kind}{suffix}"

def _when_from_ts(ts: Optional[str]) -> str:
    try:
        if ts and ts.isdigit(): return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception: pass
    return "—"

def _summarize_log(text: str) -> str:
    keep = []
    for raw in text.splitlines():
        line = raw.strip()
        if re.match(r"^Total assets found.*:\s*\d+\s*$", line, flags=re.IGNORECASE) or \
           re.match(r"^Processing\s+QR\s+\d+", line, flags=re.IGNORECASE) or \
           re.search(r"(^|\s)Saved\s", line, flags=re.IGNORECASE) or \
           re.search(r"Successfully saved", line, flags=re.IGNORECASE) or \
           re.search(r"^--- SUMMARY ---", line, flags=re.IGNORECASE) or \
           re.search(r"Success! Updated", line, flags=re.IGNORECASE) or \
           re.search(r"Successfully updated database", line, flags=re.IGNORECASE):
            keep.append(line)
    return "\n".join(keep) if keep else "No summary items found."

@app.get("/logs")
def list_logs():
    files = list(LOG_DIR.glob("*.log"))
    rows = []
    for p in files:
        ts_raw = _extract_ts_from_logname(p.name)
        rows.append({
            "name": p.name, "when": _when_from_ts(ts_raw),
            "when_ts": int(ts_raw) if ts_raw and ts_raw.isdigit() else 0,
            "title": _title_from_logname(p.name),
            "size_kb": f"{max(p.stat().st_size // 1024, 1)} KB",
        })
    rows.sort(key=lambda r: r["when_ts"], reverse=True)
    return render_template("logs.html", rows=rows)

@app.get("/logs/read")
def read_log():
    name = request.args.get("name", "")
    mode = request.args.get("mode", "summary")
    path = _safe_log_path(name)
    text = path.read_text(encoding="utf-8", errors="replace")
    content = _summarize_log(text) if mode != "raw" else text
    return render_template(
        "log_read.html", name=name, title=_title_from_logname(name),
        when=_when_from_ts(_extract_ts_from_logname(name)),
        is_summary=(mode != "raw"), content=content
    )

@app.get("/logs/download")
def download_log():
    name = request.args.get("name", "")
    _safe_log_path(name)
    return send_from_directory(LOG_DIR, name, as_attachment=True, mimetype="text/plain")

# ------------------ Main ------------------
if __name__ == "__main__":
    print("[Asset Portal] Running at http://127.0.0.1:8002")
    for key, t in TASKS.items():
        sp = _cmd_script_path(t["cmd"])
        print(f"Task {key}: {t.get('label','')} -> {sp}")
    app.run(host="127.0.0.1", port=8002, debug=False)