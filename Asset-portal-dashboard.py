# Asset-portal-dashboard.py
# Dashboard that renders templates/dashboard.html and serves the Approval chart
# via /charts/approval.png (filtered by ?building=).
#
# Requires:
#   - templates/dashboard.html  (your updated version with chart section)
#   - charts/approval.py        (module containing render_chart_png, building_options)
#   - static/                   (your CSS/logos)
#
# Optional env vars:
#   PORT=5080
#   FLASK_SECRET_KEY=change-me
#   APP_URL_MOBILE=http://127.0.0.1:5001
#   APP_URL_ME=http://127.0.0.1:5002
#   APP_URL_BF=http://127.0.0.1:5003
#   DASHBOARD_DB_PATH=... (used inside charts/approval.py)

import os
from flask import (
    Flask, render_template, request, make_response,
    redirect, url_for, flash
)

# Import the modular chart/data helpers
from charts.approval import render_chart_png, building_options

# -------------------------
# Config
# -------------------------
DEFAULT_PORT = int(os.environ.get("PORT", "5080"))
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

APP_URL_MOBILE = os.environ.get("APP_URL_MOBILE", "http://127.0.0.1:5001")
APP_URL_ME     = os.environ.get("APP_URL_ME",     "http://127.0.0.1:5002")
APP_URL_BF     = os.environ.get("APP_URL_BF",     "http://127.0.0.1:5003")

APP_CARDS = [
    {"key": "mobile",    "name": "Asset Capture Mobile App",          "url": APP_URL_MOBILE},
    {"key": "review_me", "name": "Asset Reviewer - Mechanical",       "url": APP_URL_ME},
    {"key": "review_bf", "name": "Asset Reviewer - Backflow Devices", "url": APP_URL_BF},
]

# -------------------------
# App
# -------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = SECRET_KEY


# -------------------------
# Routes
# -------------------------
@app.get("/")
def dashboard():
    """
    Renders your dashboard.html with:
      - apps: tiles for the three applications
      - building_options: ['All', ...] for the chart dropdown
    """
    try:
        opts = building_options()
    except Exception:
        opts = ["All"]
    return render_template("dashboard.html", apps=APP_CARDS, building_options=opts)


@app.get("/charts/approval.png")
def approval_chart_png():
    """
    Returns the approval chart as a PNG.
    Query param:
      ?building=<Name>  (or "All")
    """
    b = request.args.get("building", "All")
    png = render_chart_png(b)
    resp = make_response(png)
    resp.headers["Content-Type"] = "image/png"
    # prevent browser caching so dropdown changes reflect immediately
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


# --- Stubs matching your template actions (replace with real handlers if you have them) ---
@app.post("/logout")
def logout():
    flash("You have been logged out.", "secondary")
    return redirect(url_for("dashboard"))

@app.post("/run_task/<task_key>")
def run_task(task_key: str):
    # Example: trigger background job for 'qr_api_bf' or 'qr_api_me'
    flash(f"Task '{task_key}' triggered.", "info")
    return redirect(url_for("dashboard"))

@app.get("/logs")
def list_logs():
    # Wire this to your real logs UI if you have one
    flash("Logs viewer not implemented in this demo.", "warning")
    return redirect(url_for("dashboard"))


# -------------------------
# Main
# -------------------------
if __name__ == "__main__":
    print(f"[Asset Portal] Running locally at http://127.0.0.1:{DEFAULT_PORT}")
    app.run(host="127.0.0.1", port=DEFAULT_PORT, debug=False)
