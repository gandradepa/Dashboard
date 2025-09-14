#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Asset Management Dashboard – Flask app (Asset-portal-dashboard.py)

Run locally:
  python3 Asset-portal-dashboard.py

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

# ------------------ Optional modules (Corrected Logic) ------------------

# Block for analytics charts (approval)
CHARTS_AVAILABLE = True
CHARTS_IMPORT_ERROR = ""
try:
    print("Attempting to import chart module: approval...")
    from charts import approval as approval_mod
    print("Successfully imported approval module.")
except Exception as _e:
    CHARTS_AVAILABLE = False
    CHARTS_IMPORT_ERROR = str(_e)
    print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print(f"CRITICAL: Failed to import approval module. Visual charts will be disabled. Error: {_e}")
    print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

# SEPARATE block for the AI status table data
AI_STATUS_TABLE_AVAILABLE = True
try:
    print("Attempting to import data module: ai_status_table...")
    from charts import ai_status_table
    print("Successfully imported ai_status_table module.")
except Exception as _e:
    AI_STATUS_TABLE_AVAILABLE = False
    print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print(f"CRITICAL: Failed to import ai_status_table module. Pending assets table will be disabled. Error: {_e}")
    print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")


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
    for part in cmd:
        if part.lower().endswith(".py"):
            try:
                return Path(part).resolve()
            except Exception:
                return Path(part)
    return None

def _launch_cmd_detached(cmd: List[str], cwd: Optional[Path]) -> Path:
    timestamp = int(time.time())
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
def _default_api_root() -> Path:
    return Path("/home/developer/API")

def _build_tasks() -> Dict[str, Dict]:
    api_root = Path(os.environ.get("QR_API_ROOT", str(_default_api_root())))
    interpreter = api_root / "Asset_Management_API_Interpreter.py"
    old_me = api_root / "API_interface_ME_ver00.py"
    old_bf = api_root / "API_interface_BF_ver00.py"
    old_el = api_root / "API_interface_EL_ver00.py"

    tasks: Dict[str, Dict] = {}
    if interpreter.exists():
        tasks["qr_api_me"] = {"cmd": [sys.executable, "-X", "utf8", str(interpreter), "--category", "ME"], "cwd": api_root, "label": "AI Interpreter – Mechanical"}
        tasks["qr_api_bf"] = {"cmd": [sys.executable, "-X", "utf8", str(interpreter), "--category", "BF"], "cwd": api_root, "label": "AI Interpreter – Backflow"}
        tasks["qr_api_el"] = {"cmd": [sys.executable, "-X", "utf8", str(interpreter), "--category", "EL"], "cwd": api_root, "label": "AI Interpreter – Electrical"}
    else:
        tasks["qr_api_me"] = {"cmd": [sys.executable, "-X", "utf8", str(old_me)], "cwd": api_root, "label": "QR API – Mechanical"}
        tasks["qr_api_bf"] = {"cmd": [sys.executable, "-X", "utf8", str(old_bf)], "cwd": api_root, "label": "QR API – Backflow"}
        tasks["qr_api_el"] = {"cmd": [sys.executable, "-X", "utf8", str(old_el)], "cwd": api_root, "label": "QR API – Electrical"}
    return tasks

TASKS = _build_tasks()

def _validate_task_key(task_key: str) -> Dict:
    if task_key not in TASKS:
        abort(404, f"Unknown task: {task_key}")
    task = TASKS[task_key]
    script_path = _cmd_script_path(task.get("cmd", []))
    if not task.get("cmd"):
        abort(404, f"No command configured for: {task_key}")
    if script_path and not script_path.exists():
        raise FileNotFoundError(f"Script for {task_key} not found: {script_path}")
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

# ------------------ Routes: Dashboard + Chart (Corrected Logic) ------------------
@app.get("/")
def index():
    """
    Main dashboard page. This function runs on every page load,
    ensuring data is always fresh.
    """
    print("\n--- [Dashboard Load] ---")
    
    ai_status_summary, ai_asset_details = [], []
    # Use the new, separate flag to check if the data table module is available
    if AI_STATUS_TABLE_AVAILABLE:
        print("Attempting to fetch pending assets from 'ai_status_table' module...")
        try:
            summary_df, details_df = ai_status_table.get_pending_assets()
            
            if summary_df is not None and not summary_df.empty:
                ai_status_summary = summary_df.to_dict(orient='records')
                print(f"SUCCESS: Loaded {len(ai_status_summary)} summary rows.")
            else:
                print("INFO: Pending assets summary data is empty or None.")

            if details_df is not None and not details_df.empty:
                ai_asset_details = details_df.to_dict(orient='records')
                print(f"SUCCESS: Loaded {len(ai_asset_details)} detailed asset rows.")
            else:
                print("INFO: Detailed asset data is empty or None.")

        except Exception as e:
            print(f"ERROR: Failed to get pending assets data: {e}")
            ai_status_summary, ai_asset_details = [], []
    else:
        print("WARNING: ai_status_table module not available, skipping asset data fetch.")

    building = request.args.get("building", "All")
    options = _get_building_options()
    if building not in options: building = "All"
    task_labels = {k: v.get("label", k) for k, v in TASKS.items()}
    ts = int(time.time())
    
    print("--- [Rendering Template] ---")
    return render_template(
        "dashboard.html", apps=APPS, task_labels=task_labels,
        chart_enabled=CHARTS_AVAILABLE, charts_error=CHARTS_IMPORT_ERROR,
        building_options=options, selected_building=building, ts=ts,
        ai_status_summary=ai_status_summary,
        ai_asset_details=ai_asset_details
    )

@app.get("/chart/approval.png")
def approval_chart():
    if not CHARTS_AVAILABLE:
        return Response("Chart module unavailable", status=503, mimetype="text/plain")
    
    building = request.args.get("building", "All")
    chart_type = request.args.get("chart_type", "gauge") 

    try:
        png_bytes = approval_mod.render_chart_png(building=building, chart_type=chart_type)
        resp = Response(png_bytes, mimetype="image/png")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp
    except Exception as e:
        print(f"Chart error for type '{chart_type}': {e}")
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

        if "Traceback (most recent call last):" in text or "Error:" in text:
            return jsonify({"status": "error"})
        
        success_keywords = ["Saved", "Total assets found", "Finished", "Completed", "Done"]
        if any(keyword.lower() in last_line.lower() for keyword in success_keywords):
            return jsonify({"status": "success"})
        
        return jsonify({"status": "running"})
    except Exception:
        return jsonify({"status": "error"}), 404

# ------------------ Friendly Logs UI ------------------
def _title_from_logname(name: str) -> str:
    base = Path(name).stem.rsplit(".", 1)[0]
    is_interpreter = ("Interpreter" in base) or ("Asset_Management_API_Interpreter" in base)
    kind = "API Interpreter" if is_interpreter else "QR API"
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
           re.search(r"(^|\s)Saved\s", line, flags=re.IGNORECASE):
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
    
    # Use debug=True to see more detailed errors and auto-reload changes
    app.run(host="127.0.0.1", port=8002, debug=True)
