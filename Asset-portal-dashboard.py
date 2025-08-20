"""
Asset Management Dashboard – Flask app (Option A: plaintext-compatible login)

Run:
  python Asset-portal-dashboard.py
Open:
  http://127.0.0.1:5080

Requires:
  - templates/login.html
  - templates/dashboard.html
  - static/style.css
  - static/logos/ubc_logo.jpg (optional)
  - static/logos/ubc-facilities_logo.jpg (optional)
"""

import os
import sys
import time
import sqlite3
import subprocess
from pathlib import Path
from functools import wraps

from flask import (
    Flask, render_template, redirect, url_for, flash,
    request, abort, Response, session, g
)
from werkzeug.security import check_password_hash

# ------------------ Flask app ------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

# ------------------ Paths ------------------
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

USERS_DB = r"S:\MaintOpsPlan\AssetMgt\Asset Management Process\Database\8. New Assets\Git_control\asset_capture_app_dev\data\User_control.db"

# ------------------ Dashboard cards ------------------
APPS = [
    {"key": "capture",   "name": "Asset Capture Mobile App",            "url": "http://127.0.0.1:5001"},
    {"key": "review_me", "name": "Asset Reviewer - Mechanical",         "url": "http://127.0.0.1:5002"},
    {"key": "review_bf", "name": "Asset Reviewer - Backflow Devices",   "url": "http://127.0.0.1:5003"},
]

# ------------------ Whitelisted tasks ------------------
TASKS = {
    "qr_api_bf": r"S:\MaintOpsPlan\AssetMgt\Asset Management Process\Database\8. New Assets\Git_control\QR_code_project_API\API interface_BF_ver00.py",
    "qr_api_me": r"S:\MaintOpsPlan\AssetMgt\Asset Management Process\Database\8. New Assets\Git_control\QR_code_project_API\API interface_ME_ver00.py",
}

# ------------------ Auth helpers ------------------
def get_user_row(username: str):
    """Fetch a user row from SQLite by username (case-insensitive)."""
    if not os.path.exists(USERS_DB):
        return None
    try:
        con = sqlite3.connect(USERS_DB)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?) LIMIT 1",
            (username,)
        )
        row = cur.fetchone()
        cur.close()
        con.close()
        return row
    except Exception:
        return None

def is_active_user(row) -> bool:
    """Treat is_active = 1/true/yes as active; if column missing, assume active."""
    if row is None:
        return False
    if "is_active" in row.keys():
        v = row["is_active"]
        try:
            return int(v) == 1
        except Exception:
            return str(v).strip().lower() in {"1", "true", "yes", "y"}
    return True

def validate_password(row, candidate: str) -> bool:
    """
    Option A: Accept plaintext stored in password_hash for backward compatibility.
    If password_hash starts with a known scheme, verify as a real hash.
    Otherwise compare as plaintext. Also supports a legacy 'password' column.
    """
    if row is None:
        return False

    def has(col): return col in row.keys()

    if has("password_hash") and row["password_hash"]:
        ph = str(row["password_hash"])
        if ph.startswith(("pbkdf2:", "scrypt:", "argon2:")):
            try:
                return check_password_hash(ph, candidate)
            except Exception:
                return False
        else:
            # Plaintext fallback
            return ph == candidate

    if has("password") and row["password"] is not None:
        return str(row["password"]) == candidate

    return False

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            next_url = request.path
            return redirect(url_for("login", next=next_url))
        return fn(*args, **kwargs)
    return wrapper

@app.before_request
def load_current_user():
    g.user = session.get("user")  # e.g., {'username': 'gandrade'}

# ------------------ UTF‑8 safe launcher ------------------
def _launch_script_detached(script_path: Path) -> Path:
    """
    Launch Python script asynchronously with UTF‑8 I/O.
    Writes stdout/stderr to logs/<script>.<timestamp>.log
    """
    timestamp = int(time.time())
    log_path = LOG_DIR / f"{script_path.stem}.{timestamp}.log"
    log_fp = open(log_path, "w", encoding="utf-8")

    creationflags = 0
    if sys.platform.startswith("win"):
        # CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        creationflags = 0x00000200 | 0x00000008

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

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

def _validate_task_key(task_key: str) -> Path:
    if task_key not in TASKS:
        abort(404, f"Unknown task: {task_key}")
    script = Path(TASKS[task_key]).resolve()
    if not script.exists() or script.suffix.lower() != ".py":
        abort(404, f"Script not found or invalid: {script}")
    return script

# ------------------ Routes: Auth ------------------
@app.get("/login")
def login():
    if session.get("user"):
        return redirect(url_for("index"))
    return render_template("login.html")

@app.post("/login")
def login_post():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    next_url = request.args.get("next") or url_for("index")

    if not username or not password:
        flash("Please enter username and password.", "danger")
        return redirect(url_for("login", next=next_url))

    row = get_user_row(username)
    if row and is_active_user(row) and validate_password(row, password):
        session["user"] = {"username": row["username"] if "username" in row.keys() else username}
        # NOTE: intentionally no "Signed in successfully." flash
        return redirect(next_url)

    flash("Invalid username or password.", "danger")
    return redirect(url_for("login", next=next_url))

@app.post("/logout")
def logout():
    session.pop("user", None)
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))

# ------------------ Routes: Dashboard & tasks (protected) ------------------
@app.get("/", endpoint="index")  # <-- make the endpoint name 'index'
@login_required
def dashboard():
    return render_template("dashboard.html", apps=APPS)

@app.post("/run/<task_key>")
@login_required
def run_task(task_key: str):
    script = _validate_task_key(task_key)
    try:
        log_path = _launch_script_detached(script)
        flash(f"Started task '{task_key}'. Logs: {log_path.name}", "success")
    except Exception as e:
        flash(f"Failed to start task '{task_key}': {e}", "danger")
    return redirect(url_for("index"))

# ------------------ (Optional) Logs (protected) ------------------
@app.get("/logs")
@login_required
def list_logs():
    newest = sorted(LOG_DIR.glob("*.log"), reverse=True)[:50]
    items = "".join(
        f'<li><a href="{url_for("view_log", name=p.name)}">{p.name}</a></li>'
        for p in newest
    )
    return f"<h3>Recent logs</h3><ul>{items}</ul>"

@app.get("/logs/view")
@login_required
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
