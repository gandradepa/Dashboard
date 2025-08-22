#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from flask import (
    Flask, render_template, redirect, url_for, flash,
    request, abort, Response, jsonify
)

# ---- Try to load charts module ----
CHARTS_AVAILABLE = True
CHARTS_IMPORT_ERROR = ""
try:
    # charts/approval.py
    from charts import approval as approval_mod
except Exception as _e:
    CHARTS_AVAILABLE = False
    CHARTS_IMPORT_ERROR = str(_e)

# ------------------ Flask app ------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

# ------------------ Cards shown on the dashboard ------------------
APPS = [
    {"key": "capture",   "name": "Asset Capture Mobile App",            "url": "http://127.0.0.1:5001"},
    {"key": "review_me", "name": "Asset Reviewer - Mechanical",         "url": "http://127.0.0.1:5002"},
    {"key": "review_bf", "name": "Asset Reviewer - Backflow Devices",   "url": "http://127.0.0.1:5003"},
]

# ------------------ Log directory ------------------
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


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


def _default_api_root() -> Path:
    return Path(
        r"S:\MaintOpsPlan\AssetMgt\Asset Management Process\Database\8. New Assets\Git_control\QR_code_project_API"
    )


def _build_tasks() -> Dict[str, Dict]:
    """
    Prefer the unified interpreter; fallback to older per-type scripts.
    Labels DO NOT include '(Legacy)'.
    """
    api_root = Path(os.environ.get("QR_API_ROOT", str(_default_api_root())))

    interpreter = api_root / "Asset_Management_API_Interpreter.py"
    old_me = api_root / "API interface_ME_ver00.py"
    old_bf = api_root / "API interface_BF_ver00.py"

    tasks: Dict[str, Dict] = {}

    if interpreter.exists():
        tasks["qr_api_me"] = {
            "cmd": [sys.executable, "-X", "utf8", str(interpreter), "--category", "ME"],
            "cwd": api_root,
            "label": "AI Interpreter – Mechanical"
        }
        tasks["qr_api_bf"] = {
            "cmd": [sys.executable, "-X", "utf8", str(interpreter), "--category", "BF"],
            "cwd": api_root,
            "label": "AI Interpreter – Backflow"
        }
    else:
        tasks["qr_api_me"] = {
            "cmd": [sys.executable, "-X", "utf8", str(old_me)],
            "cwd": api_root,
            "label": "QR API – Mechanical"
        }
        tasks["qr_api_bf"] = {
            "cmd": [sys.executable, "-X", "utf8", str(old_bf)],
            "cwd": api_root,
            "label": "QR API – Backflow"
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
    # e.g. "API interface_BF_ver00.1755872945.log" -> "1755872945"
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


# ------------------ Routes ------------------
@app.get("/")
def index():
    # For the chart filter
    building = request.args.get("building", "All")
    options = _get_building_options()
    if building not in options:
        building = "All"

    task_labels = {k: v.get("label", k) for k, v in TASKS.items()}
    # ts used for cache-busting chart image
    ts = int(time.time())

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
        # prevent stale images
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp
    except Exception as e:
        return Response(f"Chart error: {e}", status=500, mimetype="text/plain")


@app.post("/run/<task_key>")
def run_task(task_key: str):
    try:
        task = _validate_task_key(task_key)
        log_path = _launch_cmd_detached(task["cmd"], task.get("cwd"))

        # Custom success text: "API Interpreter BF: 1755872945"
        label_for_flash = {
            "qr_api_bf": "API Interpreter BF",
            "qr_api_me": "API Interpreter ME",
        }.get(task_key, f"Task {task_key}")

        ts = _extract_ts_from_logname(log_path.name) or str(int(time.time()))
        flash(f"{label_for_flash}: {ts}", "success")

    except Exception as e:
        flash(f"Failed to start task '{task_key}': {e}", "danger")
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
    for key, t in _build_tasks().items():
        sp = _cmd_script_path(t["cmd"])
        print(f"Task {key}: {t.get('label','')} -> {sp}")
    app.run(host="127.0.0.1", port=5080, debug=False)
