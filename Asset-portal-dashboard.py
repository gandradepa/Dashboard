
# Asset-portal-dashboard.py (somente Python)
"""
Asset Portal Dashboard (local-only Flask app)

Rodar:
  python Asset-portal-dashboard.py

Abrir em navegador: http://127.0.0.1:5080
"""

import os
from flask import Flask, render_template

app = Flask(__name__)

APPS = [
    {"key": "capture",   "name": "Asset Capture Mobile App",       "url": "http://127.0.0.1:5001"},
    {"key": "review_me", "name": "Asset Reviewer - Mechanical",    "url": "http://127.0.0.1:5002"},
    {"key": "review_bf", "name": "Asset Reviewer - Backflow Devices", "url": "http://127.0.0.1:5003"},
]

@app.get("/")
def index():
    return render_template("dashboard.html", apps=APPS)

if __name__ == "__main__":
    print("[Asset Portal] Running locally at http://127.0.0.1:5080")
    app.run(host="127.0.0.1", port=5080, debug=False)

