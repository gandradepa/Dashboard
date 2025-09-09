#!/usr-bin/env python3
# -*- coding: utf-8 -*-
import os
import io
import math
import sqlite3
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # headless for servers
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, Wedge

# === CONFIG ===
DB_PATH_DEFAULT = r"/home/developer/asset_capture_app_dev/data/QR_codes.db"
DB_PATH = os.getenv("DASHBOARD_DB_PATH", DB_PATH_DEFAULT)

TABLES_MAIN = ("sdi_dataset", "sdi_dataset_EL")
TABLE_BUILDINGS = "Buildings"
COMMON_COLS = ["Approved", "Asset Group", "Attribute", "Building", "Description", "QR Code"]

# UBC palette
COLOR_APPROVED = "#002145"
COLOR_NOTAPP   = "#E6ECF2"
COLOR_TARGET   = "#0055b7"

# ---------- Data helpers ----------
def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,))
    return cur.fetchone() is not None

def _read_table(db_path: str, table: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(f'SELECT * FROM "{table}"', conn)

def _read_main_union(db_path: str, tables: tuple[str, ...], cols: list[str]) -> pd.DataFrame:
    dfs = []
    with sqlite3.connect(db_path) as conn:
        for t in tables:
            if not _table_exists(conn, t): continue
            df = pd.read_sql_query(f'SELECT * FROM "{t}"', conn)
            for c in cols:
                if c not in df.columns: df[c] = np.nan
            df = df[cols].copy()
            dfs.append(df)
    if not dfs:
        raise RuntimeError(f"None of the tables {tables} were found in the database.")
    return pd.concat(dfs, ignore_index=True)

def _prepare_data() -> pd.DataFrame:
    df = _read_main_union(DB_PATH, TABLES_MAIN, COMMON_COLS)
    df2 = _read_table(DB_PATH, TABLE_BUILDINGS)
    
    df["Building_key"] = df["Building"].astype(str).str.strip()
    df2["Code_key"]    = df2["Code"].astype(str).str.strip()
    df2 = df2.drop_duplicates(subset=["Code_key"], keep="first")

    df3 = df.merge(df2, left_on="Building_key", right_on="Code_key", how="left")
    if "Approved" not in df3.columns: df3["Approved"] = ""
    df3["Approved"] = df3["Approved"].fillna("").astype(str).str.strip()
    df3["Approved_label"] = df3["Approved"].eq("1").replace({True: "Approved", False: "Not Approved"})
    
    df3["Name"] = df3["Name"].fillna("Unknown").astype(str).str.strip()
    df3["Asset Group"] = df3["Asset Group"].fillna("Unknown").astype(str).str.strip()

    df4 = (
        df3.groupby(["Name", "Asset Group", "Approved_label"], dropna=False)["QR Code"]
           .nunique()
           .reset_index(name="QTY")
           .rename(columns={"Approved_label": "Approved"})
    )
    df4["QTY"] = pd.to_numeric(df4["QTY"], errors="coerce").fillna(0).astype(int)
    return df4

# ---------- Public helpers used by Flask ----------
def building_options():
    try:
        df4 = _prepare_data()
        opts = sorted(df4["Name"].dropna().astype(str).unique(), key=lambda n: n.lower())
        return ["All"] + opts
    except Exception:
        return ["All"]

# ---------- Chart Drawing Functions ----------
def _draw_gauge_chart(ax, value, max_value, target_percent):
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values(): s.set_visible(False)
    ax.set_title("Approval Rate KPI", fontsize=16, weight='bold', color=COLOR_APPROVED, pad=15)

    start_angle, end_angle = 180, 0
    
    background = Wedge(center=(0, 0), r=1.0, theta1=end_angle, theta2=start_angle, width=0.35, facecolor=COLOR_NOTAPP)
    ax.add_patch(background)

    value_angle = start_angle - ((value / max_value) * 180 if max_value > 0 else 0)
    foreground = Wedge(center=(0, 0), r=1.0, theta1=value_angle, theta2=start_angle, width=0.35, facecolor=COLOR_APPROVED)
    ax.add_patch(foreground)
    
    ax.text(0, 0, f"{value/max_value*100 if max_value>0 else 0:.0f}%", ha='center', va='center', fontsize=30, weight='bold', color=COLOR_APPROVED)
    ax.text(0, -0.2, "Approved", ha='center', va='center', fontsize=12, color=COLOR_APPROVED)

    target_value = max_value * (target_percent / 100.0)
    target_angle = start_angle - ((target_value / max_value) * 180 if max_value > 0 else 0)
    target_rad = math.radians(target_angle)
    x = 1.2 * math.cos(target_rad)
    y = 1.2 * math.sin(target_rad)
    ax.plot([x], [y], marker='v', markersize=10, color=COLOR_TARGET, clip_on=False)
    ax.text(x, y + 0.1, f"Target: {target_percent}%", ha='center', va='bottom', color=COLOR_TARGET, fontsize=10)
    
    ax.text(-1, -0.1, "0", ha='center', va='top', fontsize=10)
    ax.text(1, -0.1, f"{max_value}", ha='center', va='top', fontsize=10)
    
    ax.set_xlim(-1.4, 1.4)
    ax.set_ylim(-0.2, 1.4)

def _draw_bar_chart(ax, filtered_data):
    wide = filtered_data.groupby(["Asset Group", "Approved"])["QTY"].sum().unstack(fill_value=0)
    for col in ["Not Approved", "Approved"]:
        if col not in wide.columns: wide[col] = 0
    wide = wide.loc[wide.sum(axis=1).sort_values(ascending=False).index]
    
    groups = wide.index.to_series().fillna("Unknown").astype(str).tolist()
    approved_vals = wide["Approved"].to_numpy()
    not_approved_vals = wide["Not Approved"].to_numpy()
    totals = approved_vals + not_approved_vals
    y = np.arange(len(groups))

    ax.barh(y, not_approved_vals, color=COLOR_NOTAPP, height=0.7)
    ax.barh(y, approved_vals, left=not_approved_vals, color=COLOR_APPROVED, height=0.7)

    max_total = max(totals) if len(totals) > 0 else 0
    for i, total in enumerate(totals):
        if total > 0:
            ax.text(total + (max_total * 0.02), i, str(int(total)), ha='left', va='center', fontsize=9)

    ax.set_yticks(y, groups)
    ax.tick_params(axis='y', labelsize=10)
    ax.invert_yaxis()
    for s in ax.spines.values(): s.set_visible(False)
    ax.grid(False)
    ax.tick_params(axis="both", which="both", length=0)
    ax.set_xticks([])
    ax.set_xlim(0, max_total * 1.15 if max_total > 0 else 1)
    ax.set_title("Assets by Group", fontsize=14, color=COLOR_APPROVED, pad=10)

def _draw_pie_chart(ax, app_total, not_total):
    grand_total = app_total + not_total
    
    def make_autopct(values):
        def my_autopct(pct):
            total = sum(values)
            val = int(round(pct*total/100.0))
            return f'{val}\n({pct:.0f}%)'
        return my_autopct

    wedges, texts, autotexts = ax.pie(
        [app_total, not_total], labels=["", ""],
        colors=[COLOR_APPROVED, COLOR_NOTAPP], 
        autopct=make_autopct([app_total, not_total]),
        startangle=90, counterclock=False,
        wedgeprops={"width": 0.4, "edgecolor": 'none'},
        pctdistance=0.7, textprops={"fontsize": 11, "ha":'center'}, radius=1.0,
    )
    
    for a in autotexts:
        a.set_fontweight("bold")
        a.set_color("black")
    if autotexts and len(autotexts) > 0:
      autotexts[0].set_color("white")
      
    ax.axis("equal")
    ax.set_title("Overall Approval", fontsize=14, color=COLOR_APPROVED, pad=10)

# ---------- Main Rendering Function ----------
def render_chart_png(building: str = "All", chart_type: str = "all") -> bytes:
    try:
        df4 = _prepare_data()
        filtered = df4 if (building == "All" or not building) else df4[df4["Name"] == building]
    except Exception as e:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, f"Data error:\n{e}", ha="center", va="center", wrap=True)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, transparent=True); plt.close(fig); buf.seek(0)
        return buf.read()

    app_total = int(filtered.loc[filtered["Approved"] == "Approved", "QTY"].sum())
    not_total = int(filtered.loc[filtered["Approved"] == "Not Approved", "QTY"].sum())
    grand_total = app_total + not_total

    fig = None
    if chart_type == "gauge":
        fig, ax = plt.subplots(figsize=(6, 4))
        if grand_total == 0: ax.text(0.5, 0.5, "No data", ha="center")
        else: _draw_gauge_chart(ax, app_total, grand_total, 90)
    elif chart_type == "bar":
        num_groups = len(filtered["Asset Group"].unique())
        # --- CORREÇÃO FINAL: Forçar uma proporção alta e estreita na imagem gerada ---
        fig_height = max(8, num_groups * 0.9) 
        fig_width = 6 # Largura reduzida para forçar a proporção
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        if filtered.empty: ax.text(0.5, 0.5, "No data", ha="center")
        else: _draw_bar_chart(ax, filtered)
    elif chart_type == "pie":
        fig, ax = plt.subplots(figsize=(5, 4))
        if grand_total == 0: ax.text(0.5, 0.5, "No data", ha="center")
        else: _draw_pie_chart(ax, app_total, not_total)

    if fig:
        fig.patch.set_facecolor('none')
        ax.set_facecolor('none')
        plt.tight_layout(pad=1.0)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, transparent=True)
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    
    return b""

