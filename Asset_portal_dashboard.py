#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Asset Management Dashboard – Flask app (Asset-portal-dashboard.py)

Run locally:
  python Asset-portal-dashboard.py

Open:
  http://127.0.0.1:8002

Features
--------
- App tiles linking to Capture + Review apps
- "Run AI Interpreter" buttons (ME/BF/EL) that launch whitelisted scripts
- Flash message format: "API Interpreter BF/ME/EL: <timestamp> — open summary"
- Approval analytics chart (bar + pie) with Building filter
- Friendly Logs UI:
    /logs          -> recent logs table (When, Title, File, Actions)
    /logs/read     -> summary (default) or raw view
    /logs/download -> download the .log
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
from markupsafe import Markup  # for clickable flash message

# ------------------ Optional chart module ------------------
# Expects a local module at charts/approval.py
CHARTS_AVAILABLE = True
CHARTS_IMPORT_ERROR = ""
try:
    from charts import approval as approval_mod
except Exception as _e:
    CHARTS_AVAILABLE = False
    CHARTS_IMPORT_ERROR = str(_e)

# ------------------ Flask app ------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

# ------------------ Cards shown on the dashboard ------------------
APPS = [
    {"key": "capture",    "name": "Asset Capture Mobile App",           "url": "https://appprod.assetcap.facilities.ubc.ca"},
    {"key": "review_me",  "name": "Asset Reviewer - Mechanical",        "url": "https://reviewme.assetcap.facilities.ubc.ca"},
    {"key": "review_bf",  "name": "Asset Reviewer - Backflow Devices",  "url": "https://reviewbf.assetcap.facilities.ubc.ca"},
    {"key": "review_el",  "name": "Asset Reviewer - Electrical",        "url": "https://reviewel.assetcap.facilities.ubc.ca"},  # NEW
]

# ------------------ Log directory ------------------
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ------------------ Runner helpers ------------------
def _windows_detached_flags() -> int:
    if sys.platform.startswith("win"):
        # CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
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
    """
    Launch a command asynchronously (non-blocking) with UTF-8 I/O.
    Writes stdout/stderr to logs/<first_py_name>.<timestamp>.log (UTF-8).
    """
    timestamp = int(time.time())
    script_path = _cmd_script_path(cmd)
    stem = script_path.stem if script_path else "task"
    log_path = LOG_DIR / f"{stem}.{timestamp}.log"

    log_fp = open(log_path, "w", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        shell=False,
        creationflags=_windows_detached_flags(),
        env=env,
    )
    return log_path

# ------------------ Script locations ------------------
def _default_api_root() -> Path:
    # New default path: where the API scripts live
    return Path("/home/developer/API")

def _build_tasks() -> Dict[str, Dict]:
    """
    Prefer the unified interpreter; fallback to older per-type scripts.
    Labels DO NOT include '(Legacy)'.
    """
    api_root = Path(os.environ.get("QR_API_ROOT", str(_default_api_root())))

    # Paths to scripts in /home/developer/API
    interpreter = api_root / "Asset_Management_API_Interpreter.py"
    old_me = api_root / "API_interface_ME_ver00.py"
    old_bf = api_root / "API_interface_BF_ver00.py"
    old_el = api_root / "API_interface_EL_ver00.py"  # NEW

    tasks: Dict[str, Dict] = {}
    if interpreter.exists():
        # Prefer unified interpreter (add EL)
        tasks["qr_api_me"] = {
            "cmd": [sys.executable, "-X", "utf8", str(interpreter), "--category", "ME"],
            "cwd": api_root,
            "label": "AI Interpreter – Mechanical",
        }
        tasks["qr_api_bf"] = {
            "cmd": [sys.executable, "-X", "utf8", str(interpreter), "--category", "BF"],
            "cwd": api_root,
            "label": "AI Interpreter – Backflow",
        }
        tasks["qr_api_el"] = {  # NEW
            "cmd": [sys.executable, "-X", "utf8", str(interpreter), "--category", "EL"],
            "cwd": api_root,
            "label": "AI Interpreter – Electrical",
        }
    else:
        # Fallback to legacy scripts (add EL)
        tasks["qr_api_me"] = {
            "cmd": [sys.executable, "-X", "utf8", str(old_me)],
            "cwd": api_root,
            "label": "QR API – Mechanical",
        }
        tasks["qr_api_bf"] = {
            "cmd": [sys.executable, "-X", "utf8", str(old_bf)],
            "cwd": api_root,
            "label": "QR API – Backflow",
        }
        tasks["qr_api_el"] = {  # NEW
            "cmd": [sys.executable, "-X", "utf8", str(old_el)],
            "cwd": api_root,
            "label": "QR API – Electrical",
        }
    return tasks

TASKS = _build_tasks()

def _validate_task_key(task_key: str) -> Dict:
    if task_key not in TASKS:
        abort(404, f"Unknown task: {task_key}")

    task = TASKS[task_key]
    cmd = task.get("cmd", [])
    script_path = _cmd_script_path(cmd)

    if not cmd:
        abort(404, f"No command configured for: {task_key}")

    if script_path and not script_path.exists():
        raise FileNotFoundError(
            f"Script for {task_key} not found: {script_path}\n"
            f"Tip: set QR_API_ROOT to the folder containing your API scripts, "
            f"or ensure the interpreter file exists."
        )
    return task

def _extract_ts_from_logname(name: str) -> Optional[str]:
    # e.g. "API_interface_BF_ver00.1755872945.log" -> "1755872945"
    stem = Path(name).stem
    parts = stem.rsplit(".", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[1]
    return None

# ------------------ Chart helpers ------------------
def _get_building_options() -> List[str]:
    if not CHARTS_AVAILABLE:
        return ["All"]
    try:
        return approval_mod.building_options()
    except Exception:
        return ["All"]

# ------------------ Routes: Dashboard + Chart ------------------
@app.get("/")
def index():
    # Building filter for chart
    building = request.args.get("building", "All")
    options = _get_building_options()
    if building not in options:
        building = "All"

    task_labels = {k: v.get("label", k) for k, v in TASKS.items()}
    ts = int(time.time())  # cache-busting for chart image

    return render_template(
        "dashboard.html",
        apps=APPS,
        task_labels=task_labels,
        chart_enabled=CHARTS_AVAILABLE,
        charts_error=CHARTS_IMPORT_ERROR,
        building_options=options,
        selected_building=building,
        ts=ts,
    )

@app.get("/chart/approval.png")
def approval_chart():
    if not CHARTS_AVAILABLE:
        return Response("Chart module unavailable", status=503, mimetype="text/plain")
    building = request.args.get("building", "All")
    try:
        png_bytes = approval_mod.render_chart_png(building=building)
        resp = Response(png_bytes, mimetype="image/png")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp
    except Exception as e:
        return Response(f"Chart error: {e}", status=500, mimetype="text/plain")

# ------------------ Routes: Run Tasks ------------------
@app.post("/run/<task_key>")
def run_task(task_key: str):
    try:
        task = _validate_task_key(task_key)
        log_path = _launch_cmd_detached(task["cmd"], task.get("cwd"))

        # Custom success text with clickable link: "API Interpreter BF: 1755872945 — open summary"
        label_for_flash = {
            "qr_api_bf": "API Interpreter BF",
            "qr_api_me": "API Interpreter ME",
            "qr_api_el": "API Interpreter EL",  # NEW
        }.get(task_key, f"Task {task_key}")

        ts = _extract_ts_from_logname(log_path.name) or str(int(time.time()))
        link = url_for("read_log", name=log_path.name, mode="summary")
        flash(Markup(f'{label_for_flash}: {ts} — <a href="{link}" class="alert-link">open summary</a>'), "success")

    except Exception as e:
        flash(f"Failed to start task '{task_key}': {e}", "danger")
    # preserve current building filter when redirecting back (falls back to All)
    return redirect(url_for("index", building=request.args.get("building", "All")))

@app.get("/task_status/<task_key>")
def task_status(task_key: str):
    exists = False
    script_path = ""
    try:
        task = _validate_task_key(task_key)
        sp = _cmd_script_path(task["cmd"])
        script_path = str(sp) if sp else ""
        exists = bool(sp and Path(sp).exists())
    except Exception:
        exists = False

    newest = sorted(LOG_DIR.glob("*.log"), reverse=True)[:1]
    payload = {
        "task": task_key,
        "script_exists": exists,
        "script_path": script_path,
        "latest_log": newest[0].name if newest else "",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    return jsonify(payload)

# ------------------ Friendly Logs UI ------------------
def _title_from_logname(name: str) -> str:
    base = Path(name).stem.rsplit(".", 1)[0]  # drop ".<ts>"
    # Heuristics: Interpreter vs QR API, and ME/BF/EL if present in name
    is_interpreter = ("Interpreter" in base) or ("Asset_Management_API_Interpreter" in base)
    kind = "API Interpreter" if is_interpreter else "QR API"

    suffix = ""
    base_upper = base.upper()
    if "ME" in base_upper:
        suffix = " – ME"
    elif "BF" in base_upper:
        suffix = " – BF"
    elif "EL" in base_upper:  # NEW
        suffix = " – EL"

    return f"{kind}{suffix}"

def _when_from_ts(ts: Optional[str]) -> str:
    try:
        if ts and ts.isdigit():
            dt = datetime.fromtimestamp(int(ts))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return "—"

def _summarize_log(text: str) -> str:
    """
    Keep only:
      - Total assets found: N   (EN/PT variants allowed)
      - Processing QR 0000...
      - ✅ Saved <path>
    """
    keep: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()

        # EN/PT variants like:
        # "Total assets found: 2"
        # "Total assets found (após filtro de aprovação): 2"
        if re.match(r"^Total assets found.*:\s*\d+\s*$", line, flags=re.IGNORECASE):
            keep.append(line)
            continue

        # "Processing QR 0000183699 …"
        if re.match(r"^Processing\s+QR\s+\d+", line, flags=re.IGNORECASE):
            keep.append(line)
            continue

        # "Saved ..." with or without emoji
        if re.search(r"(^|\s)Saved\s", line, flags=re.IGNORECASE):
            if "Saved" in line and not line.lstrip().startswith("✅"):
                line = "✅ " + line.lstrip()
            keep.append(line)
            continue

    return "\n".join(keep) if keep else "No summary items found."

def _safe_log_path(name: str) -> Path:
    p = (LOG_DIR / name).resolve()
    if not p.exists() or p.parent != LOG_DIR.resolve():
        abort(404, "Log not found")
    return p

@app.get("/logs")
def list_logs():
    """User-friendly list sorted ONLY by the When timestamp (descending)."""
    files = list(LOG_DIR.glob("*.log"))
    rows = []
    for p in files:
        ts_raw = _extract_ts_from_logname(p.name)           # e.g., "1755874399"
        ts_int = int(ts_raw) if ts_raw and ts_raw.isdigit() else 0  # numeric for sorting
        rows.append({
            "name": p.name,
            "when": _when_from_ts(ts_raw),                  # "YYYY-MM-DD HH:MM:SS" or "—"
            "when_ts": ts_int,                              # used ONLY for sorting
            "title": _title_from_logname(p.name),
            "size_kb": f"{max(p.stat().st_size // 1024, 1)} KB",
        })

    # Sort STRICTLY by when_ts desc; items without a timestamp (0) fall to the bottom
    rows.sort(key=lambda r: r["when_ts"], reverse=True)

    return render_template("logs.html", rows=rows)

@app.get("/logs/read")
def read_log():
    """HTML view: summary (default) or raw text inside <pre>."""
    name = request.args.get("name", "")
    mode = request.args.get("mode", "summary")  # 'summary' | 'raw'
    path = _safe_log_path(name)
    text = path.read_text(encoding="utf-8", errors="replace")

    if mode == "raw":
        content = text
        is_summary = False
    else:
        content = _summarize_log(text)
        is_summary = True

    ts = _extract_ts_from_logname(name)
    return render_template(
        "log_read.html",
        name=name,
        title=_title_from_logname(name),
        when=_when_from_ts(ts),
        is_summary=is_summary,
        content=content,
    )

@app.get("/logs/download")
def download_log():
    """Download the raw .log file."""
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
