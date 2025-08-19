"""
Asset Management Dashboard – Flask app (Asset-portal-dashboard.py)

Run locally:
  python Asset-portal-dashboard.py

Open:
  http://127.0.0.1:5080

Requires:
  - templates/dashboard.html
  - static/style.css
  - (optional) static/logos/ubc_logo.jpg, static/logos/ubc-facilities_logo.jpg

This app renders the dashboard and exposes a POST-only /run/<task_key> endpoint
to launch approved Python scripts on the server (whitelist). Output from launched
scripts is written to UTF-8 log files in ./logs/.
"""

import os
import sys
import time
import subprocess
from pathlib import Path

from flask import (
    Flask, render_template, redirect, url_for, flash,
    request, abort, Response
)

# ------------------ Flask app ------------------
app = Flask(__name__)
# Needed for flash() messages
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

# ------------------ Cards shown on the dashboard ------------------
APPS = [
    {"key": "capture",   "name": "Asset Capture Mobile App",            "url": "http://127.0.0.1:5001"},
    {"key": "review_me", "name": "Asset Reviewer - Mechanical",         "url": "http://127.0.0.1:5002"},
    {"key": "review_bf", "name": "Asset Reviewer - Backflow Devices",   "url": "http://127.0.0.1:5003"},
]

# ------------------ Whitelisted tasks (safe) ------------------
# Map a short key -> absolute path to a Python script you allow to run
TASKS = {
    "qr_api_bf": r"S:\MaintOpsPlan\AssetMgt\Asset Management Process\Database\8. New Assets\Git_control\QR_code_project_API\API interface_BF_ver00.py",
    "qr_api_me": r"S:\MaintOpsPlan\AssetMgt\Asset Management Process\Database\8. New Assets\Git_control\QR_code_project_API\API interface_ME_ver00.py",
}

# ------------------ Log directory ------------------
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


# ------------------ Helpers ------------------
def _validate_task_key(task_key: str) -> Path:
    """Return script path for a valid task key or 404."""
    if task_key not in TASKS:
        abort(404, f"Unknown task: {task_key}")
    script = Path(TASKS[task_key]).resolve()
    if not script.exists() or script.suffix.lower() != ".py":
        abort(404, f"Script not found or invalid: {script}")
    return script


def _launch_script_detached(script_path: Path) -> Path:
    """
    Launch a Python script asynchronously (non-blocking) with UTF‑8 I/O.
    Uses the same interpreter as this Flask app (sys.executable).
    Writes stdout/stderr to logs/<script>.<timestamp>.log (UTF‑8).
    """
    timestamp = int(time.time())
    log_path = LOG_DIR / f"{script_path.stem}.{timestamp}.log"

    # Open the log as UTF‑8 so emojis/special chars won't break on Windows
    log_fp = open(log_path, "w", encoding="utf-8")

    # Windows detached flags (ignored on non‑Windows)
    creationflags = 0
    if sys.platform.startswith("win"):
        # CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        creationflags = 0x00000200 | 0x00000008

    # Inherit env, force UTF‑8 for child process
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    # -X utf8 enables UTF‑8 mode for the child Python interpreter
    subprocess.Popen(
        [sys.executable, "-X", "utf8", str(script_path)],
        cwd=str(script_path.parent),
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        shell=False,
        creationflags=creationflags,
        env=env,
    )
    return log_path


# ------------------ Routes ------------------
@app.get("/")
def index():
    """
    Renders the dashboard. The template should include forms like:

      <!-- Mechanical -->
      <form method="post" action="{{ url_for('run_task', task_key='qr_api_me') }}">
        <button class="btn ubc-btn" type="submit">Run Mechanical QR API</button>
      </form>

      <!-- Backflow -->
      <form method="post" action="{{ url_for('run_task', task_key='qr_api_bf') }}">
        <button class="btn ubc-btn" type="submit">Run Backflow QR API</button>
      </form>
    """
    return render_template("dashboard.html", apps=APPS)


@app.post("/run/<task_key>")
def run_task(task_key: str):
    """
    POST-only endpoint that starts a whitelisted task in the background.
    Shows a flash message with the created log file name.
    """
    script = _validate_task_key(task_key)
    try:
        log_path = _launch_script_detached(script)
        flash(f"Started task '{task_key}'. Logs: {log_path.name}", "success")
    except Exception as e:
        flash(f"Failed to start task '{task_key}': {e}", "danger")
    return redirect(url_for("index"))


# --------- (Optional) Minimal log browser ----------
@app.get("/logs")
def list_logs():
    newest = sorted(LOG_DIR.glob("*.log"), reverse=True)[:50]
    items = "".join(
        f'<li><a href="{url_for("view_log", name=p.name)}">{p.name}</a></li>'
        for p in newest
    )
    return f"<h3>Recent logs</h3><ul>{items}</ul>"


@app.get("/logs/view")
def view_log():
    name = request.args.get("name", "")
    path = (LOG_DIR / name).resolve()
    if not path.exists() or path.parent != LOG_DIR.resolve():
        abort(404)
    return Response(path.read_text(encoding="utf-8"), mimetype="text/plain")


# ------------------ Main ------------------
if __name__ == "__main__":
    print("[Asset Portal] Running locally at http://127.0.0.1:5080")
    app.run(host="127.0.0.1", port=5080, debug=False)
