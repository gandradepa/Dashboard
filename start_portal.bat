:: start_all_apps.bat
@echo off
setlocal
cd /d %~dp0

REM 1) Asset Capture - porta 5001
start "capture-5001" cmd /k python "S:\MaintOpsPlan\AssetMgt\Asset Management Process\Database\8. New Assets\Git_control\asset_capture_app_dev\app.py"

REM 2) Reviewer ME - porta 5002
start "review-me-5002" cmd /k python "S:\MaintOpsPlan\AssetMgt\Asset Management Process\Database\8. New Assets\Git_control\Asset_plate_review_ME\Asset Plate Reviewer_browser_ME_ver01.py"

REM 3) Reviewer BF - porta 5003
start "review-bf-5003" cmd /k python "S:\MaintOpsPlan\AssetMgt\Asset Management Process\Database\8. New Assets\Git_control\Asset_plate_review_BF\Asset Plate Reviewer_browser_BF_ver01.py"
