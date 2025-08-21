# Asset-portal-dashboard.py
# Dashboard + background task runner for "Run AI Interpreter" buttons.
#
# WHAT'S NEW
# - /run_task/<task_key> now launches a detached subprocess and logs to /logs.
# - Simple duplicate-run guard via PID files.
# - /logs lists log files; /logs/<name> lets you download/view them.
#
# REQUIRED ENV VARS (set these to your actual script paths):
#   TASK_QR_API_BF="S:\path\to\API interface_BF_ver00.py"
#   TASK_QR_API_ME="S:\path\to\API interface_ME_ver00.py"
#
# OPTIONAL ENV VARS:
#   PORT=5080
#   FLASK_SECRET_KEY=change-me
#   APP_URL_MOBILE=http://127.0.0.1:5001
#   APP_URL_ME=http://127.0.0.1:5002
#   APP_URL_BF=http://127.0.0.1:5003
#   PYTHON_EXECUTABLE=python (defaults to current interpreter)

import os
import sys
import time
import glob
import json
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from flask import (
    Flask, render_template, request, make_response, redirect,
    url_for, flash, abort, send_from_directory, render_template_string
)

# --- Import chart helpers (your modular file) ---
from charts.approval import render_chart_png, building_options

# -------------------------
# Config
# -------------------------
DEFAULT_PORT = int(os.environ.get("PORT", "5080"))
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

APP_URL_MOBILE = os.environ.get("APP_URL_MOBILE", "http://127.0.0.1:5001")
APP_URL_ME     = os.environ.get("APP_URL_ME",     "http://127.0.0.1:5002")
APP_URL_BF     = os.environ.get("APP_URL_BF",     "http://127.0.0.1:5003")

# Where to store logs/PIDs (repo's ./logs folder by default)
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR  = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Python executable to launch child processes
PYTHON_EXE = os.environ.get("PYTHON_EXECUTABLE", sys.executable)

# Map dashboard tiles
APP_CARDS = [
    {"key": "mobile",    "name": "Asset Capture Mobile App",          "url": APP_URL_MOBILE},
    {"key": "review_me", "name": "Asset Reviewer - Mechanical",       "url": APP_URL_ME},
    {"key": "review_bf", "name": "Asset Reviewer - Backflow Devices", "url": APP_URL_BF},
]

# Background task registry (keys must match your template’s task_key)
TASKS: Dict[str, str] = {
    # Set these via env or edit here:
    "qr_api_bf": os.environ.get("TASK_QR_API_BF", r"S:\MaintOpsPlan\AssetMgt\...\API interface_BF_ver00.py"),
    "qr_api_me": os.environ.get("TASK_QR_API_ME", r"S:\MaintOpsPlan\AssetMgt\...\API interface_ME_ver00.py"),
}

# -------------------------
# App
# -------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = SECRET_KEY

# -------------------------
# Utilities
# -------------------------
def _pid_file(task_key: str) -> Path:
    return LOG_DIR / f"{task_key}.pid"

def _is_pid_alive(pid: int) -> bool:
    try:
        # Works on Linux & Windows (Python 3.9+)
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True

def _read_pid(task_key: str) -> Optional[int]:
    pf = _pid_file(task_key)
    if not pf.exists():
        return None
    try:
        data = json.loads(pf.read_text(encoding="utf-8"))
        return int(data.get("pid", 0)) or None
    except Exception:
        return None

def _write_pid(task_key: str, pid: int, log_path: Path):
    payload = {"pid": pid, "log": str(log_path), "ts": datetime.utcnow().isoformat() + "Z"}
    _pid_file(task_key).write_text(json.dumps(payload, indent=2), encoding="utf-8")

def _clear_pid(task_key: str):
    try:
        _pid_file(task_key).unlink(missing_ok=True)
    except Exception:
        pass

def _make_creationflags():
    # Detach child on Windows so it keeps running after the HTTP request ends
    if os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        return DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    return 0

def _start_task(task_key: str) -> Path:
    """
    Start a task as a detached subprocess.
    Returns the log file path.
    """
    script = TASKS.get(task_key)
    if not script:
        raise ValueError(f"Unknown task key: {task_key}")
    script_path = Path(script)
    if not script_path.exists():
        raise FileNotFoundError(f"Script for {task_key} not found: {script_path}")

    # Duplicate-run guard
    old_pid = _read_pid(task_key)
    if old_pid and _is_pid_alive(old_pid):
        raise RuntimeError(f"Task '{task_key}' is already running (PID {old_pid}).")

    # Create log file
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"{task_key}_{ts}.log"
    log_file = open(log_path, "ab", buffering=0)

    # Build command
    cmd = [PYTHON_EXE, str(script_path)]
    cwd = str(script_path.parent)

    # Launch
    creationflags = _make_creationflags()
    try:
        if os.name == "nt":
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                shell=False,
                creationflags=creationflags,
            )
        else:
            # On POSIX, start a new session
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                shell=False,
                preexec_fn=os.setsid
            )
    except Exception:
        log_file.close()
        log_path.unlink(missing_ok=True)
        raise

    # Persist PID for status/guard
    _write_pid(task_key, proc.pid, log_path)
    return log_path

# -------------------------
# Routes
# -------------------------
@app.get("/")
def dashboard():
    try:
        opts = building_options()
    except Exception:
        opts = ["All"]
    return render_template("dashboard.html", apps=APP_CARDS, building_options=opts)

@app.get("/charts/approval.png")
def approval_chart_png():
    b = request.args.get("building", "All")
    png = render_chart_png(b)
    resp = make_response(png)
    resp.headers["Content-Type"] = "image/png"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp

@app.post("/run_task/<task_key>")
def run_task(task_key: str):
    """
    Launch background process for the requested task.
    Shows a flash with the log file name and current status.
    """
    try:
        log_path = _start_task(task_key)
        flash(f"Task '{task_key}' started. Logging to {log_path.name}", "success")
    except FileNotFoundError as e:
        flash(str(e), "danger")
    except RuntimeError as e:
        flash(str(e), "warning")
    except Exception as e:
        flash(f"Failed to start task '{task_key}': {e}", "danger")
    return redirect(url_for("dashboard"))

@app.get("/task_status/<task_key>")
def task_status(task_key: str):
    """Simple JSON status (PID alive?)"""
    pid = _read_pid(task_key)
    alive = _is_pid_alive(pid) if pid else False
    return {"task": task_key, "pid": pid, "alive": alive}

@app.post("/logout")
def logout():
    flash("You have been logged out.", "secondary")
    return redirect(url_for("dashboard"))

# ---- Logs UI ----
@app.get("/logs")
def list_logs():
    files = sorted(glob.glob(str(LOG_DIR / "*.log")), key=os.path.getmtime, reverse=True)
    items = [
        {
            "name": Path(p).name,
            "size_kb": round(os.path.getsize(p) / 1024, 1),
            "mtime": datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for p in files
    ]
    # Simple inline template so you don't need a new file
    tpl = """
    <!doctype html><html><head>
    <meta charset="utf-8"><title>Logs</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"/>
    </head><body class="p-3">
      <div class="container">
        <h1 class="h4 mb-3">Background Task Logs</h1>
        <p><a href="{{ url_for('dashboard') }}" class="btn btn-sm btn-secondary">← Back</a></p>
        {% if items %}
          <table class="table table-sm table-striped align-middle">
            <thead><tr><th>File</th><th>Size (KB)</th><th>Modified</th><th></th></tr></thead>
            <tbody>
              {% for it in items %}
              <tr>
                <td><code>{{ it.name }}</code></td>
                <td>{{ it.size_kb }}</td>
                <td>{{ it.mtime }}</td>
                <td><a class="btn btn-sm btn-outline-primary" href="{{ url_for('get_log', name=it.name) }}" target="_blank">Open</a></td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        {% else %}
          <div class="alert alert-info">No logs yet.</div>
        {% endif %}
      </div>
    </body></html>
    """
    return render_template_string(tpl, items=items)

@app.get("/logs/<path:name>")
def get_log(name: str):
    # Security: only serve files under LOG_DIR
    safe = Path(name).name
    return send_from_directory(LOG_DIR, safe, mimetype="text/plain", as_attachment=False)

# -------------------------
# Main
# -------------------------
if __name__ == "__main__":
    print(f"[Asset Portal] Running locally at http://127.0.0.1:{DEFAULT_PORT}")
    app.run(host="127.0.0.1", port=DEFAULT_PORT, debug=False)
