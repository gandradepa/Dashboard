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
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# --- [CONFIGURATION] Python Path Setup ---
# Ensure the current directory and parent directory are in the python path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from flask import (
    Flask, render_template, redirect, url_for, flash,
    request, abort, Response, jsonify, send_from_directory, Blueprint
)
from markupsafe import Markup

## Import authentication and environment variable libraries
from flask_login import login_user, logout_user, login_required, current_user
from dotenv import load_dotenv

## Add the shared auth_service directory to Python's path
sys.path.append('/home/developer/auth_service') 

from auth_model import db, bcrypt, User
from auth_controller import login_manager


# ------------------ Chart Modules Import Section ------------------
CHARTS_AVAILABLE = False
AI_STATUS_AVAILABLE = False
COMPLETENESS_CHART_AVAILABLE = False
OPERATIONAL_COST_CHART_AVAILABLE = False
FLS_CHARTS_AVAILABLE = False
CHARTS_IMPORT_ERROR = ""

# 1. Try Import: Approval Charts
try:
    from charts import approval as approval_mod
    CHARTS_AVAILABLE = True
except Exception as _e:
    CHARTS_IMPORT_ERROR = str(_e)

# 2. Try Import: AI Status Table
try:
    from charts import ai_status_table_new_version as ai_status_table
    AI_STATUS_AVAILABLE = True
except Exception as _e:
    error_msg = str(_e)
    if CHARTS_IMPORT_ERROR: CHARTS_IMPORT_ERROR += f" | {error_msg}"
    else: CHARTS_IMPORT_ERROR = error_msg

# 3. Try Import: Completeness Score
try:
    from charts import completeness_score as completeness_mod
    COMPLETENESS_CHART_AVAILABLE = True
except Exception as _e:
    error_msg = f"Completeness Chart Error: {str(_e)}"
    if CHARTS_IMPORT_ERROR: CHARTS_IMPORT_ERROR += f" | {error_msg}"
    else: CHARTS_IMPORT_ERROR = error_msg

# 4. Try Import: Operational Cost
try:
    from charts import operational_cost_result as operational_cost_mod
    OPERATIONAL_COST_CHART_AVAILABLE = True
except Exception as _e:
    error_msg = f"Operational Cost Chart Error: {str(_e)}"
    if CHARTS_IMPORT_ERROR: CHARTS_IMPORT_ERROR += f" | {error_msg}"
    else: CHARTS_IMPORT_ERROR = error_msg

# 5. Try Import: FLS Charts (Altair Version - Robust Import)
print("--- Attempting to import FLS Charts ---")
try:
    # Check if altair is installed first
    import altair
    
    # Try importing locally first, then as package
    try:
        import fls_chart as fls_charts_mod
        print("SUCCESS: Imported 'fls_chart' locally.")
    except ImportError:
        from charts import fls_chart as fls_charts_mod
        print("SUCCESS: Imported 'fls_chart' from charts package.")

    FLS_CHARTS_AVAILABLE = True

except ImportError as e:
    FLS_CHARTS_AVAILABLE = False
    error_msg = f"Missing Dependency for FLS Charts (Altair or fls_chart): {e}"
    print(f"CRITICAL ERROR: {error_msg}")
    if CHARTS_IMPORT_ERROR: CHARTS_IMPORT_ERROR += f" | {error_msg}"
    else: CHARTS_IMPORT_ERROR = error_msg

except Exception as e:
    FLS_CHARTS_AVAILABLE = False
    error_msg = f"Error loading FLS Charts module: {e}"
    print(f"CRITICAL ERROR: {error_msg}")
    traceback.print_exc() 
    if CHARTS_IMPORT_ERROR: CHARTS_IMPORT_ERROR += f" | {error_msg}"
    else: CHARTS_IMPORT_ERROR = error_msg


# ------------------ Flask app Configuration ------------------
load_dotenv('/home/developer/.env')

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI')
app.config['SESSION_COOKIE_DOMAIN'] = os.getenv('SESSION_COOKIE_DOMAIN')

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

## --- Path to the SQLite DB --- ##
DB_PATH = r"/home/developer/asset_capture_app_dev/data/QR_codes.db"

# ------------------ Runner helpers (RESTORED FULLY) ------------------
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

# ------------------ Log UI Helpers ------------------
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
            if re.search(r"Successfully processed and saved", line, flags=re.IGNORECASE) or \
               re.search(r"^--- SUMMARY ---", line, flags=re.IGNORECASE) or \
               re.search(r"^Total assets processed:", line, flags=re.IGNORECASE) or \
               re.search(r"^Successfully saved:", line, flags=re.IGNORECASE):
                keep.append(line)
    finally:
        if hasattr(lines, 'close'):
            lines.close()
            
    return "\n".join(keep) if keep else "No summary items found."


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

@main_bp.get("/data/fls_assets")
@login_required
def get_fls_asset_data():
    """
    Provides all necessary data for the FLS Assets table view.
    ALL data is now sourced from QR_codes.db using sqlite3.
    """
    print("--- [START] get_fls_asset_data ---")
    
    # 1. Initialize empty lists
    all_properties = [] 
    filter_properties = [] 
    spaces_by_prop = {}
    device_map = {}
    asset_group_options = []
    asset_group_lookup_map = {}
    asset_group_name_to_option_map = {}  # Maps simple name to full option
    existing_assets = []
    property_asset_tag_map = {}
    property_name_to_code_map = {}
    conn = None

    try:
        print("Connecting to database...")
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # This allows accessing columns by name
        cursor = conn.cursor()
        print("Database connection successful.")

        # --- 1a. Get Property List for MODAL (from Buildings table) ---
        try:
            print("Executing query for 'Buildings' table...")
            # Fetch both Name and Code to build the name->code map
            cursor.execute('SELECT "Name", "Code" FROM Buildings ORDER BY "Name"')
            print("Query for 'Buildings' executed. Fetching rows...")
            for row in cursor.fetchall():
                all_properties.append(row['Name']) 
                property_name_to_code_map[row['Name']] = row['Code']
            print(f"Successfully fetched {len(all_properties)} properties from 'Buildings'.")
        except sqlite3.Error as e:
            print(f"WARNING: Could not query 'Buildings' table from QR_codes.db: {e}")
            all_properties = []

        # --- 1b. Get Property List for FILTER (from new_device table) ---
        try:
            print("Executing query for distinct 'Property' from 'new_device'...")
            cursor.execute('''
                SELECT DISTINCT "Property" FROM new_device 
                WHERE "Property" IS NOT NULL AND TRIM("Property") != '' 
                ORDER BY "Property"
            ''')
            print("Query for distinct 'Property' executed. Fetching rows...")
            for row in cursor.fetchall():
                filter_properties.append(row['Property'])
            print(f"Found {len(filter_properties)} distinct properties in new_device for filtering.")
        except sqlite3.Error as e:
            print(f"WARNING: Could not query 'new_device' for distinct properties: {e}")
            filter_properties = [] 

        # --- 2. Get Spaces by Property (from Buildings_with_SpaceUID view) ---
        spaces_by_prop = {}
        try:
            print("Executing query for 'Buildings_with_SpaceUID' view...")
            cursor.execute('''
                SELECT "Name", "Location" FROM Buildings_with_SpaceUID 
                WHERE "Location" IS NOT NULL AND TRIM("Location") != ''
            ''')
            print("Query for 'Buildings_with_SpaceUID' executed. Fetching rows...")
            for row in cursor.fetchall():
                property_name = row['Name']
                space_location = row['Location']
                if property_name not in spaces_by_prop:
                    spaces_by_prop[property_name] = []
                spaces_by_prop[property_name].append(space_location)
            print(f"Successfully fetched spaces for {len(spaces_by_prop)} properties.")
        except sqlite3.Error as e:
            print(f"WARNING: Could not query 'Buildings_with_SpaceUID' view from QR_codes.db: {e}")
            spaces_by_prop = {}
        
        # --- 3. Get Asset Group Options AND Device Type Map from 'fls_asset_group' ---
        device_map = {}
        asset_group_options = []
        asset_group_lookup_map = {}
        try:
            print("Executing query for 'fls_asset_group' table...")
            cursor.execute("""
                SELECT
                    "Full Classification",
                    "Device Type",
                    "Attribute Set",
                    "Device Address",
                    "Description",
                    CASE
                        WHEN Name IS NOT NULL AND "Full Classification" IS NOT NULL
                            THEN Name || ' | ' || "Full Classification"
                        WHEN Name IS NULL
                            THEN "Full Classification"
                        ELSE Name
                    END AS "AssetGroupOption"
                FROM "fls_asset_group"
                ORDER BY "AssetGroupOption"
            """)
            print("Query for 'fls_asset_group' executed. Fetching rows...")
            for row in cursor.fetchall():
                row_dict = dict(row)
                asset_group_option = row_dict.get('AssetGroupOption')
                if not asset_group_option:
                    continue
                
                asset_group_option = asset_group_option.strip()
                asset_group_options.append(asset_group_option)

                full_classification = row_dict.get('Full Classification')
                device_type = row_dict.get('Device Type')

                if full_classification and device_type:
                    device_map[full_classification] = device_type

                asset_group_lookup_map[asset_group_option] = {
                    'description': row_dict.get('Description'),
                    'attribute_set': row_dict.get('Attribute Set'),
                    'device_address': row_dict.get('Device Address'),
                    'device_type': device_type
                }
                
                # Build reverse mapping: simple name -> full option
                # Extract the Name part (before the |) to map it to the full option
                if ' | ' in asset_group_option:
                    simple_name = asset_group_option.split(' | ')[0].strip()
                    asset_group_name_to_option_map[simple_name] = asset_group_option
                else:
                    asset_group_name_to_option_map[asset_group_option] = asset_group_option
            print(f"Successfully built asset group lookup map with {len(asset_group_lookup_map)} entries.")
            print(f"DEBUG: asset_group_name_to_option_map contains {len(asset_group_name_to_option_map)} entries")
            if len(asset_group_name_to_option_map) > 0:
                first_few = list(asset_group_name_to_option_map.items())[:3]
                print(f"DEBUG: First few mappings: {first_few}")

        except sqlite3.Error as e:
            print(f"WARNING: Could not query 'fls_asset_group' table from QR_codes.db: {e}")
            device_map = {}
            asset_group_options = []
            asset_group_lookup_map = {}

        # --- 4. Get Property to Asset Tag mapping from 'Asset_System_info' ---
        try:
            print("Executing query for 'Asset_System_info' view...")
            cursor.execute('SELECT "Property code", "Asset Tag" FROM Asset_System_info')
            print("Query for 'Asset_System_info' executed. Fetching rows...")
            for row in cursor.fetchall():
                if row['Property code'] and row['Asset Tag']:
                    property_asset_tag_map[row['Property code']] = row['Asset Tag']
            print(f"Successfully built property-to-asset-tag map with {len(property_asset_tag_map)} entries.")
        except sqlite3.Error as e:
            print(f"WARNING: Could not query 'Asset_System_info' view from QR_codes.db: {e}")
            property_asset_tag_map = {}
        
        
        # --- 5. Get existing assets from 'new_device' table ---
        print("Executing query for 'new_device' table...")
        cursor.execute("SELECT * FROM new_device ORDER BY [Creation Date] DESC")
        print("Query for 'new_device' executed. Fetching rows...")
        rows = cursor.fetchall()
        
        if not rows:
            print("FLS get_fls_asset_data: 'new_device' table is empty.")
        
        for row in rows:
            row_dict = dict(row)
            status_val = row_dict.get('Status') 
            
            if str(status_val) not in ('0', '1'):
                workflow_val = row_dict.get('Workflow')
                workflow_normalized = (workflow_val or "").strip().lower()
                status_val = '1' if workflow_normalized.startswith('complete') else '0'
            else:
                status_val = str(status_val)
            
            # Get the asset group from the database
            db_asset_group = row_dict.get('Asset Group')
            # Look up the full AssetGroupOption using the name-to-option mapping
            asset_group_option = asset_group_name_to_option_map.get(db_asset_group, db_asset_group)
            
            print(f"DEBUG: Processing asset {row_dict.get('Asset Tag')}: db_asset_group='{db_asset_group}', mapping result='{asset_group_option}'")
            
            asset = {
                "index": row_dict.get('index'),
                "work_order": row_dict.get('Work Order'),
                "asset_tag": row_dict.get('Asset Tag'),
                "asset_group": asset_group_option,  # Use the full option for dropdown matching
                "description": row_dict.get('Description'),
                "property": row_dict.get('Property'),
                "space": row_dict.get('Space'),
                "space_details": row_dict.get('Space Details'),
                "attribute_set": row_dict.get('Attribute Set'),
                "device_address": row_dict.get('Device Address'),
                "device_type": row_dict.get('Device Type'),
                "un_account_number": row_dict.get('UN Account Number'),
                "planon_code": row_dict.get('Planon Code'),
                "creation_date": str(row_dict.get('Creation Date') or ''),
                "status": status_val,
                "workflow": row_dict.get('Workflow')
            }
            # DEBUG: Log the exact asset being appended
            print(f"DEBUG: About to append asset: {asset}")
            existing_assets.append(asset)
        
        print(f"FLS get_fls_asset_data: Successfully loaded {len(existing_assets)} assets from QR_codes.db.")
        # DEBUG: Show what we're returning to the frontend
        print("DEBUG: Assets being returned to frontend:")
        for asset in existing_assets:
            print(f"  - {asset.get('asset_tag')}: asset_group='{asset.get('asset_group')}'")
        import sys
        sys.stdout.flush()

    except Exception as e:
        print(f"CRITICAL ERROR fetching FLS data from QR_codes.db: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Failed to load FLS asset data from QR_codes.db: {e}"}), 500
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")
        print("--- [END] get_fls_asset_data ---")

    # 3. Return all data
    return jsonify({
        "existing_assets": existing_assets,
        "property_list": all_properties, 
        "filter_property_list": filter_properties, 
        "spaces_by_property": spaces_by_prop,
        "device_type_map": device_map,
        "asset_group_options": asset_group_options,
        "asset_group_lookup_map": asset_group_lookup_map,
        "property_asset_tag_map": property_asset_tag_map,
        "property_name_to_code_map": property_name_to_code_map
    })


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

# --- [FIXED FLS CHART ROUTE FOR ORIGINAL SCRIPT] ---
@main_bp.get("/chart/fls_charts.html")
@login_required
def fls_charts():
    if not FLS_CHARTS_AVAILABLE:
        error_msg = f"FLS charts module unavailable. Details: {CHARTS_IMPORT_ERROR}"
        return Response(error_msg, 503, mimetype="text/plain")

    # The original script fetches its own data via its fls_df() function.
    # It takes no arguments.
    try:
        fls_charts_mod.generate_charts()
    except Exception as e:
        print(f"Error generating FLS charts: {e}")
        traceback.print_exc()
        return Response(f"Error generating charts: {e}", 500, mimetype="text/plain")

    # Render the container. has_data=True triggers the iframes.
    ts = int(time.time())
    return render_template("fls_charts_container.html", ts=ts, has_data=True)

# ------------------ FLS Asset CRUD Routes ------------------
@main_bp.post("/fls/add_assets")
@login_required
def add_fls_assets():
    """
    Adds a new asset or updates an existing one in the QR_codes.db
    using an INSERT ... ON CONFLICT (upsert) command.
    This now saves ALL fields from the modal.
    """
    data = request.get_json()
    if not data or not isinstance(data, list):
        return jsonify({"success": False, "message": "Invalid data format."}), 400

    conn = None
    try:
        asset_data = data[0]
        
        # --- Prepare all data from modal ---
        asset_index = asset_data.get('index')
        
        # Generate creation date string, used *only* if inserting
        creation_date = datetime.utcnow().strftime('%m/%d/%Y')

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # --- Use INSERT ... ON CONFLICT (Upsert) ---
        # [NEW] This query is now expanded to include 16 columns
        query = """
            INSERT INTO new_device (
                "index", "Asset Tag", "Asset Group", "Description", "Property", "Space", "Space Details",
                "Attribute Set", "Device Address", "Device Type", "UN Account Number",
                "Status", "Work Order", "Creation Date", "Planon Code", "Workflow"
            ) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT("index") DO UPDATE SET
                "Asset Tag" = excluded."Asset Tag",
                "Asset Group" = excluded."Asset Group",
                "Description" = excluded."Description",
                "Property" = excluded."Property",
                "Space" = excluded."Space",
                "Space Details" = excluded."Space Details",
                "Attribute Set" = excluded."Attribute Set",
                "Device Address" = excluded."Device Address",
                "Device Type" = excluded."Device Type",
                "UN Account Number" = excluded."UN Account Number",
                "Status" = excluded."Status",
                "Work Order" = excluded."Work Order",
                "Planon Code" = excluded."Planon Code",
                "Workflow" = excluded."Workflow"
        """
        
        # Build the parameters tuple in the correct order
        params = (
            asset_index,
            asset_data.get('asset_tag'),
            asset_data.get('asset_group'),
            asset_data.get('description'),
            asset_data.get('property'),
            asset_data.get('space'),
            asset_data.get('space_details'), # <-- [NEW] Added Space Details
            asset_data.get('attribute_set'),
            asset_data.get('device_address'),
            asset_data.get('device_type'),
            asset_data.get('un_account_number'),
            asset_data.get('status'),
            asset_data.get('work_order'),
            creation_date,  # This is only used on INSERT
            asset_data.get('planon_code'),
            asset_data.get('workflow')
        )
        
        cursor.execute(query, params)
        conn.commit()

        if cursor.rowcount > 0:
            # Fetch the *actual* creation date from the DB
            cursor.execute('SELECT "Creation Date" FROM new_device WHERE "index" = ?', (asset_index,))
            result = cursor.fetchone()
            if result:
                asset_data['creation_date'] = result[0]
            else:
                asset_data['creation_date'] = creation_date
            
            message = "Asset successfully saved."
        else:
            message = "No changes detected."

        # Return the saved asset data so the frontend table can update
        # (it's already in the correct format in asset_data)
        
        return jsonify({"success": True, "message": message, "assets": [asset_data]})

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR in add_fls_assets: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Database error: {e}"}), 500
    finally:
        if conn:
            conn.close()


@main_bp.post("/fls/delete_assets")
@login_required
def delete_fls_assets():
    data = request.get_json()
    indices = data.get('indices', [])
    if not indices:
        return jsonify({"success": False, "message": "No asset indices provided."}), 400
    
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create placeholders for the IN clause
        placeholders = ', '.join('?' for _ in indices)
        # --- FIX: Use "index" instead of QR_code_ID ---
        query = f'DELETE FROM new_device WHERE "index" IN ({placeholders})'
        
        cursor.execute(query, indices)
        conn.commit()
        
        print(f"FLS delete_fls_assets: Deleted {len(indices)} assets.")
        return jsonify({"success": True, "message": f"Successfully deleted {len(indices)} asset(s)."})
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR in delete_fls_assets: {e}")
        return jsonify({"success": False, "message": f"Database error: {e}"}), 500
    finally:
        if conn:
            conn.close()

@main_bp.post("/fls/bulk_update_assets")
@login_required
def bulk_update_assets():
    """
    Updates multiple assets at once based on user selection.
    Only updates columns that are explicitly allowed.
    """
    data = request.get_json()
    indices = data.get('indices', [])
    updates = data.get('updates', {})

    if not indices:
        return jsonify({"success": False, "message": "No asset indices provided."}), 400
    if not updates:
        return jsonify({"success": False, "message": "No updates specified."}), 400

    # Whitelist of columns allowed for bulk update.
    # This matches the fields available in the bulk edit modal.
    ALLOWED_BULK_UPDATE_COLS = {"Property", "Space", "Status", "Workflow"}
    
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # To fetch updated rows by column name
        cursor = conn.cursor()

        set_clauses = []
        params = []
        
        for column_name, value in updates.items():
            if column_name in ALLOWED_BULK_UPDATE_COLS:
                # Use quoted column names
                set_clauses.append(f'"{column_name}" = ?')
                params.append(value)
            else:
                return jsonify({"success": False, "message": f"Bulk update for column '{column_name}' is not allowed."}), 400

        if not set_clauses:
            return jsonify({"success": False, "message": "No valid update fields provided."}), 400

        set_query_part = ", ".join(set_clauses)
        where_placeholders = ', '.join('?' for _ in indices)
        
        # --- FIX: Use "index" instead of QR_code_ID ---
        query = f'UPDATE new_device SET {set_query_part} WHERE "index" IN ({where_placeholders})'
        
        params.extend(indices)
        
        cursor.execute(query, params)
        conn.commit()
        
        print(f"FLS bulk_update_assets: Updated {len(indices)} assets with fields: {list(updates.keys())}.")

        # --- Fetch the updated rows to send back to the client ---
        select_placeholders = ', '.join('?' for _ in indices)
        # --- FIX: Use "index" instead of QR_code_ID ---
        select_query = f'SELECT * FROM new_device WHERE "index" IN ({select_placeholders})'
        cursor.execute(select_query, indices)
        updated_rows = cursor.fetchall()

        # Format the rows in the same way as get_fls_asset_data
        assets_list = []
        for row in updated_rows:
            row_dict = dict(row)
            status_val = row_dict.get('Status')
            if str(status_val) not in ('0', '1'):
                status_val = '0' # Default to 'Ongoing' if invalid
            else:
                status_val = str(status_val)

            # --- FIX: Read all columns from the DB row ---
            asset = {
                "index": row_dict.get('index'),
                "work_order": row_dict.get('Work Order'),
                "asset_tag": row_dict.get('Asset Tag'),
                "asset_group": row_dict.get('Asset Group'),
                "description": row_dict.get('Description'),
                "property": row_dict.get('Property'),
                "space": row_dict.get('Space'),
                "space_details": row_dict.get('Space Details'), # <-- [NEW] Added Space Details
                "attribute_set": row_dict.get('Attribute Set'),
                "device_address": row_dict.get('Device Address'),
                "device_type": row_dict.get('Device Type'),
                "un_account_number": row_dict.get('UN Account Number'),
                "planon_code": row_dict.get('Planon Code'),
                "creation_date": row_dict.get('Creation Date'),
                "status": status_val,
                "workflow": row_dict.get('Workflow')
            }
            assets_list.append(asset)

        return jsonify({"success": True, "message": "Assets updated successfully.", "assets": assets_list})

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERROR in bulk_update_assets: {e}")
        return jsonify({"success": False, "message": f"Database error: {e}"}), 500
    finally:
        if conn:
            conn.close()


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
    
@main_bp.get("/logs/download") # <-- THIS IS THE CORRECTED TYPO
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