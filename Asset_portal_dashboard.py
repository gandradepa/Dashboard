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
    request, abort, Response, jsonify, send_from_directory, Blueprint
)
from markupsafe import Markup

## NEW ## -> Import authentication and environment variable libraries
from flask_login import login_user, logout_user, login_required, current_user
from dotenv import load_dotenv

## NEW ## -> Add the shared auth_service directory to Python's path
# This allows us to import our shared modules for database models and login control
sys.path.append('/home/developer/auth_service')
from auth_model import db, bcrypt, User
from auth_controller import login_manager


# ------------------ Optional chart modules ------------------
CHARTS_AVAILABLE = False
AI_STATUS_AVAILABLE = False
COMPLETENESS_CHART_AVAILABLE = False
OPERATIONAL_COST_CHART_AVAILABLE = False
CHARTS_IMPORT_ERROR = ""

try:
    from charts import approval as approval_mod
    CHARTS_AVAILABLE = True
except Exception as _e:
    CHARTS_IMPORT_ERROR = str(_e)

try:
    from charts import ai_status_table_new_version as ai_status_table
    AI_STATUS_AVAILABLE = True
except Exception as _e:
    error_msg = str(_e)
    if CHARTS_IMPORT_ERROR and error_msg not in CHARTS_IMPORT_ERROR:
         CHARTS_IMPORT_ERROR = f"{CHARTS_IMPORT_ERROR} | {error_msg}"
    else:
        CHARTS_IMPORT_ERROR = error_msg

try:
    from charts import completeness_score as completeness_mod
    COMPLETENESS_CHART_AVAILABLE = True
except Exception as _e:
    error_msg = f"Completeness Chart Error: {str(_e)}"
    if CHARTS_IMPORT_ERROR and error_msg not in CHARTS_IMPORT_ERROR:
         CHARTS_IMPORT_ERROR = f"{CHARTS_IMPORT_ERROR} | {error_msg}"
    else:
        CHARTS_IMPORT_ERROR = error_msg

try:
    from charts import operational_cost_result as operational_cost_mod
    OPERATIONAL_COST_CHART_AVAILABLE = True
except Exception as _e:
    error_msg = f"Operational Cost Chart Error: {str(_e)}"
    if CHARTS_IMPORT_ERROR and error_msg not in CHARTS_IMPORT_ERROR:
         CHARTS_IMPORT_ERROR = f"{CHARTS_IMPORT_ERROR} | {error_msg}"
    else:
        CHARTS_IMPORT_ERROR = error_msg


# ------------------ Flask app Configuration ------------------
## NEW ## -> Load environment variables from the central .env file
load_dotenv('/home/developer/.env')

app = Flask(__name__)

## NEW ## -> Configure the app using variables from the .env file for security and SSO
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI')
app.config['SESSION_COOKIE_DOMAIN'] = os.getenv('SESSION_COOKIE_DOMAIN')

## NEW ## -> Connect the extensions (db, bcrypt, login_manager) to this specific app
db.init_app(app)
bcrypt.init_app(app)
login_manager.init_app(app)


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
        if part.lower().endswith((".py", ".sh")):
            try:
                return Path(part).resolve()
            except Exception:
                return Path(part)
    return None

def _launch_cmd_detached(cmd: List[str], cwd: Optional[Path]) -> Path:
    timestamp = int(time.time())
    
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
    api_root = _get_api_root()
    
    wrapper_script = api_root / "run_interpreter.sh"

    me_script = api_root / "API_interface_ME_ver00.py"
    bf_script = api_root / "API_interface_BF_ver00.py"
    el_script = api_root / "API_interface_EL_ver00.py"

    tasks: Dict[str, Dict] = {}
    
    tasks["qr_api_me"] = {"cmd": ["/bin/bash", str(wrapper_script), str(me_script)], "cwd": api_root, "label": "AI Interpreter – Mechanical"}
    tasks["qr_api_bf"] = {"cmd": ["/bin/bash", str(wrapper_script), str(bf_script)], "cwd": api_root, "label": "AI Interpreter – Backflow"}
    tasks["qr_api_el"] = {"cmd": ["/bin/bash", str(wrapper_script), str(el_script)], "cwd": api_root, "label": "AI Interpreter – Electrical"}
    
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


##-------------------------------------------------------------##
## Authentication Routes Blueprint                             ##
##-------------------------------------------------------------##
auth_bp = Blueprint('auth', __name__, template_folder='templates')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user, remember=request.form.get('remember'))
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.index'))
        else:
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('auth.login'))
            
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

app.register_blueprint(auth_bp)


##-------------------------------------------------------------##
## Main Application Routes Blueprint                           ##
##-------------------------------------------------------------##
main_bp = Blueprint('main', __name__, template_folder='templates')

@main_bp.get("/")
@login_required
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
    
    recent_logs = []
    try:
        log_files = sorted(LOG_DIR.glob("*.log"), key=os.path.getmtime, reverse=True)
        for p in log_files[:5]:
            ts_raw = _extract_ts_from_logname(p.name)
            recent_logs.append({
                "name": p.name,
                "when": _when_from_ts(ts_raw),
                "title": _title_from_logname(p.name),
            })
    except Exception as e:
        print(f"WARNING: Could not fetch recent logs: {e}")

    print("--- [Rendering Template] ---")

    return render_template(
        "dashboard.html", apps=APPS, task_labels=task_labels,
        chart_enabled=CHARTS_AVAILABLE, charts_error=CHARTS_IMPORT_ERROR,
        building_options=options, selected_building=building, ts=ts,
        ai_status_summary=summary_data,
        ai_asset_details=details_data,
        completeness_chart_enabled=COMPLETENESS_CHART_AVAILABLE,
        operational_cost_chart_enabled=OPERATIONAL_COST_CHART_AVAILABLE,
        recent_logs=recent_logs,
        username=current_user.username
    )

@main_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_user.check_password(old_password):
            flash('Your old password was entered incorrectly. Please try again.', 'danger')
            return redirect(url_for('main.change_password'))

        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return redirect(url_for('main.change_password'))

        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'danger')
            return redirect(url_for('main.change_password'))

        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', new_password):
            flash('New password must contain at least one special character (e.g., !@#$%).', 'danger')
            return redirect(url_for('main.change_password'))

        current_user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        db.session.commit()

        flash('Your password has been updated successfully!', 'success')
        return redirect(url_for('main.index'))
        
    return render_template('change_password.html')

# ------------------ Chart Routes ------------------
@main_bp.get("/chart/approval.png")
@login_required
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

@main_bp.get("/chart/completeness.png")
@login_required
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

@main_bp.get("/chart/operational_cost.png")
@login_required
def operational_cost_chart():
    if not OPERATIONAL_COST_CHART_AVAILABLE:
        abort(404, "Operational cost chart module not available.")
    try:
        chart_type = request.args.get("type", "combo")
        building = request.args.get("building", "All")
        png_bytes = operational_cost_mod.render_chart_png(chart_type=chart_type, building=building)
        
        resp = Response(png_bytes, mimetype="image/png")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp
    except Exception as e:
        print(f"Operational cost chart error for type '{chart_type}': {e}")
        return Response(f"Chart error: {e}", status=500, mimetype="text/plain")

# ------------------ Task Routes ------------------
@main_bp.post("/run/<task_key>")
@login_required
def run_task(task_key: str):
    try:
        task = _validate_task_key(task_key)
        log_path = _launch_cmd_detached(task["cmd"], task.get("cwd"))
        return jsonify({"success": True, "log_name": log_path.name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@main_bp.get("/log_status/<name>")
@login_required
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

# ------------------ Log UI Routes ------------------
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

# CORRECTED: Single, correct version of the function
def _summarize_log(text: str = None, path: Path = None) -> str:
    """Efficiently summarizes a log file by reading line-by-line from a path."""
    if not path:
        lines = text.splitlines() if text else []
    else:
        lines = path.open("r", encoding="utf-8", errors="replace")

    keep = []
    try:
        for raw in lines:
            line = raw.strip()
            # This 'if' block now correctly captures all relevant summary lines
            if re.search(r"Successfully processed and saved", line, flags=re.IGNORECASE) or \
               re.search(r"^--- SUMMARY ---", line, flags=re.IGNORECASE) or \
               re.search(r"^Total assets processed:", line, flags=re.IGNORECASE) or \
               re.search(r"^Successfully saved:", line, flags=re.IGNORECASE):
                keep.append(line)
    finally:
        if hasattr(lines, 'close'):
            lines.close()
            
    return "\n".join(keep) if keep else "No summary items found."

@main_bp.get("/logs")
@login_required
def list_logs():
    from_view = request.args.get("from", None)
    rows = []
    try:
        # Sort all log files by modification time, descending
        all_files = sorted(LOG_DIR.glob("*.log"), key=os.path.getmtime, reverse=True)

        # Limit the list to only the 200 most recent files to prevent memory errors
        recent_files = all_files[:200]

        for p in recent_files:
            try:
                ts_raw = _extract_ts_from_logname(p.name)
                rows.append({
                    "name": p.name, 
                    "when": _when_from_ts(ts_raw),
                    "title": _title_from_logname(p.name),
                    "size_kb": f"{max(p.stat().st_size // 1024, 1)} KB",
                })
            except Exception as e:
                print(f"WARNING: Skipping log file '{p.name}' due to error: {e}")

    except Exception as e:
        print(f"CRITICAL: Could not read logs directory: {e}")
        flash("Error: Could not read the log directory.", "danger")

    return render_template("logs.html", rows=rows, from_view=from_view)

@main_bp.get("/logs/read")
@login_required
def read_log():
    name = request.args.get("name", "")
    mode = request.args.get("mode", "summary")
    path = _safe_log_path(name)
    
    # Set a 5MB limit for viewing raw logs in the browser
    RAW_VIEW_LIMIT_BYTES = 5 * 1024 * 1024 
    content = ""
    is_summary = (mode != "raw")

    try:
        if is_summary:
            # Efficiently summarize from the file path
            content = _summarize_log(path=path)
        else:  # Raw mode
            file_size = path.stat().st_size
            if file_size > RAW_VIEW_LIMIT_BYTES:
                size_mb = file_size / 1024 / 1024
                content = (f"Error: Raw log file is too large to display ({size_mb:.2f} MB).\n\n"
                           f"Please use the 'Download' button to view the full log.")
            else:
                content = path.read_text(encoding="utf-8", errors="replace")

    except Exception as e:
        print(f"CRITICAL ERROR reading log {name}: {e}")
        flash(f"Could not read log file: {e}", "danger")
        content = f"Error: A critical error occurred while trying to read the log file."

    return render_template(
        "log_read.html", name=name, title=_title_from_logname(name),
        when=_when_from_ts(_extract_ts_from_logname(name)),
        is_summary=is_summary, content=content
    )
    
@main_bp.get("/logs/download")
@login_required
def download_log():
    name = request.args.get("name", "")
    _safe_log_path(name)
    return send_from_directory(LOG_DIR, name, as_attachment=True, mimetype="text/plain")

app.register_blueprint(main_bp)


# ------------------ Main ------------------
if __name__ == "__main__":
    print("[Asset Portal] Running at http://127.0.0.1:8002")
    for key, t in TASKS.items():
        sp = _cmd_script_path(t["cmd"])
        print(f"Task {key}: {t.get('label','')} -> {sp}")
    app.run(host="127.0.0.1", port=8002, debug=False)