# charts/approval.py
import os
import io
import sqlite3
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # headless for servers
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# === CONFIG ===
DB_PATH_DEFAULT = r"/home/developer/asset_capture_app_dev/data/QR_codes.db"
DB_PATH = os.getenv("DASHBOARD_DB_PATH", DB_PATH_DEFAULT)

TABLES_MAIN = ("sdi_dataset", "sdi_dataset_EL")  # <— use both
TABLE_BUILDINGS = "Buildings"

# Columns common to both tables (as per your note)
COMMON_COLS = ["Approved", "Asset Group", "Attribute", "Building", "Description", "QR Code"]

# UBC palette
COLOR_APPROVED = "#002145"  # dark blue
COLOR_NOTAPP   = "#E6ECF2"  # light grey
BG_FACE        = "#f4f7fb"  # Match website background


# ---------- Data helpers ----------
def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    )
    return cur.fetchone() is not None

def _read_table(db_path: str, table: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(f'SELECT * FROM "{table}"', conn)

def _read_main_union(db_path: str, tables: tuple[str, ...], cols: list[str]) -> pd.DataFrame:
    """Read the listed tables, keep only cols, and union them into a single df."""
    dfs = []
    with sqlite3.connect(db_path) as conn:
        for t in tables:
            if not _table_exists(conn, t):
                continue
            df = pd.read_sql_query(f'SELECT * FROM "{t}"', conn)

            # Ensure all expected columns exist (if any is missing, create empty)
            for c in cols:
                if c not in df.columns:
                    df[c] = np.nan

            # Keep only the common columns in the defined order
            df = df[cols].copy()
            df["__source_table__"] = t  # optional: handy for debugging
            dfs.append(df)

    if not dfs:
        raise RuntimeError(f"None of the tables {tables} were found in the database.")
    return pd.concat(dfs, ignore_index=True)

def _ensure(df: pd.DataFrame, cols: list, name: str):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"Missing column(s) {missing} in {name}. Available: {list(df.columns)}")

def _prepare_data() -> pd.DataFrame:
    """Return df4 grouped as (Name, Asset Group, Approved, QTY)."""
    # --- df now pulls from BOTH main tables ---
    df = _read_main_union(DB_PATH, TABLES_MAIN, COMMON_COLS)

    # Buildings map
    df2 = _read_table(DB_PATH, TABLE_BUILDINGS)

    _ensure(df,  ["Building"], "main_union")
    _ensure(df2, ["Code", "Name"], "Buildings")

    # Normalize keys for join
    df["Building_key"] = df["Building"].astype(str).str.strip()
    df2["Code_key"]    = df2["Code"].astype(str).str.strip()
    df2 = df2.drop_duplicates(subset=["Code_key"], keep="first")

    # Merge to get Building Name
    df3 = df.merge(df2, left_on="Building_key", right_on="Code_key", how="left") \
            .drop(columns=["Building_key", "Code_key"])

    # Clean up optional columns from Buildings if present
    df3 = df3.drop(columns=["Owner Rep", "Usage"], errors="ignore")

    # Normalize Approved ? "Approved"/"Not Approved"
    if "Approved" not in df3.columns:
        df3["Approved"] = ""
    df3["Approved"] = df3["Approved"].fillna("").astype(str).str.strip()
    df3["Approved_label"] = df3["Approved"].eq("1").replace({True: "Approved", False: "Not Approved"})

    _ensure(df3, ["Name", "Asset Group", "Approved_label", "QR Code"], "merged")
    df3["Name"] = df3["Name"].fillna("Unknown").astype(str).str.strip()
    df3["Asset Group"] = df3["Asset Group"].fillna("Unknown").astype(str).str.strip()

    # Group: distinct QR Code counts by (Building Name, Asset Group, Approved)
    df4 = (
        df3.groupby(["Name", "Asset Group", "Approved_label"], dropna=False)["QR Code"]
           .nunique()
           .reset_index(name="QTY")
           .rename(columns={"Approved_label": "Approved"})
           .sort_values(["Name", "Asset Group", "Approved"])
           .reset_index(drop=True)
    )
    df4["QTY"] = pd.to_numeric(df4["QTY"], errors="coerce").fillna(0).astype(int)
    return df4


# ---------- Public helpers used by Flask ----------
def building_options():
    """Return ['All', ...] list for the dropdown."""
    try:
        df4 = _prepare_data()
        opts = sorted(df4["Name"].dropna().astype(str).unique(), key=lambda n: n.lower())
        return ["All"] + opts
    except Exception:
        return ["All"]

def render_chart_png(building: str = "All") -> bytes:
    """Return PNG bytes of the chart (bar + pie)."""
    fig, (ax_bar, ax_pie) = plt.subplots(1, 2, figsize=(16, 7), gridspec_kw={"width_ratios": [3, 1]})
    
    # Set background for figure and axes
    fig.patch.set_facecolor(BG_FACE)
    for ax in (ax_bar, ax_pie): ax.set_facecolor(BG_FACE)

    try:
        df4 = _prepare_data()
        filtered = df4 if (building == "All" or not building) else df4[df4["Name"] == building]
    except Exception as e:
        ax_bar.text(0.5, 0.5, f"Data error:\n{e}", ha="center", va="center", fontsize=12, wrap=True)
        ax_bar.set_xticks([]); ax_bar.set_yticks([]); ax_pie.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", transparent=True); plt.close(fig); buf.seek(0)
        return buf.read()

    if filtered.empty:
        ax_bar.text(0.5, 0.5, "No data for selection", ha="center", va="center", fontsize=12)
        ax_bar.set_xticks([]); ax_bar.set_yticks([])
        ax_pie.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=12)
        ax_pie.set_xticks([]); ax_pie.set_yticks([])
    else:
        wide = (
            filtered.groupby(["Asset Group", "Approved"], dropna=False)["QTY"]
                    .sum()
                    .unstack(fill_value=0)
        )
        for col in ["Not Approved", "Approved"]:
            if col not in wide.columns: wide[col] = 0
        wide = wide.loc[wide.sum(axis=1).sort_values(ascending=False).index]

        groups = wide.index.to_series().fillna("Unknown").astype(str).tolist()
        approved_vals = wide["Approved"].to_numpy()
        not_approved_vals = wide["Not Approved"].to_numpy()
        totals = approved_vals + not_approved_vals
        y = np.arange(len(groups))

        ax_bar.barh(y, not_approved_vals, color=COLOR_NOTAPP, height=0.7, edgecolor=BG_FACE)
        ax_bar.barh(y, approved_vals, left=not_approved_vals, color=COLOR_APPROVED, height=0.7, edgecolor=BG_FACE)

        max_total = max(totals) if len(totals) > 0 else 0
        for i, total in enumerate(totals):
            if total > 0:
                ax_bar.text(total + (max_total * 0.01), i, str(int(total)),
                            ha='left', va='center', fontsize=9)

        ax_bar.set_yticks(y, groups)
        ax_bar.invert_yaxis()
        ax_bar.set_ylabel("Asset Group")

        for s in ax_bar.spines.values(): s.set_visible(False)
        ax_bar.grid(False)
        ax_bar.tick_params(axis="both", which="both", length=0)
        ax_bar.set_xticks([])
        ax_bar.set_xlim(0, max_total * 1.15 if max_total > 0 else 1)

        # --- Donut Chart Logic ---
        app_total = int(filtered.loc[filtered["Approved"] == "Approved", "QTY"].sum())
        not_total = int(filtered.loc[filtered["Approved"] == "Not Approved", "QTY"].sum())
        
        grand_total = app_total + not_total
        if grand_total == 0:
            ax_pie.text(0.5, 0.5, "No totals", ha="center", va="center", fontsize=12); ax_pie.axis("off")
        else:
            wedges, texts, autotexts = ax_pie.pie(
                [app_total, not_total],
                labels=["Approved", "Not Approved"],
                colors=[COLOR_APPROVED, COLOR_NOTAPP],
                autopct=lambda p: f"{p:.0f}%",
                startangle=90, counterclock=False,
                wedgeprops={"width": 0.4, "edgecolor": BG_FACE},
                pctdistance=0.8,
                textprops={"fontsize": 11},
                radius=1.1,
            )
            
            ax_pie.text(
                0, 0, f"{grand_total}\nAssets", 
                ha="center", va="center", 
                fontsize=17, fontweight="bold", color=COLOR_APPROVED
            )

            for a in autotexts: a.set_fontweight("normal")
            for w, t, a in zip(wedges, texts, autotexts):
                 if t.get_text() == "Approved":
                     a.set_color("white"); a.set_fontweight("bold")
                 else:
                     a.set_color("black")

            ax_pie.axis("equal")
            ax_pie.set_title("Overall Approval %", y=1.0, pad=-25)

        for s in ax_pie.spines.values(): s.set_visible(False)
        ax_pie.set_xticks([]); ax_pie.set_yticks([])

    plt.subplots_adjust(left=0.1, right=0.9, top=0.85, bottom=0.15, wspace=0.3)

    buf = io.BytesIO()
    # Save with transparent background
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf.read()

