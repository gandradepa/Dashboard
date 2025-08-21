# charts/approval.py
import os
import io
import sqlite3
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # headless for servers
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Patch

# === CONFIG ===
DB_PATH_DEFAULT = r"S:\MaintOpsPlan\AssetMgt\Asset Management Process\Database\8. New Assets\Git_control\asset_capture_app_dev\data\QR_codes.db"
DB_PATH = os.getenv("DASHBOARD_DB_PATH", DB_PATH_DEFAULT)

TABLE_MAIN = "sdi_dataset"
TABLE_BUILDINGS = "Buildings"

# UBC palette
COLOR_APPROVED = "#002145"  # dark blue
COLOR_NOTAPP   = "#E6ECF2"  # light grey
BG_FACE        = "white"


# ---------- Data helpers ----------
def _read_table(db_path: str, table: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(f'SELECT * FROM "{table}"', conn)

def _ensure(df: pd.DataFrame, cols: list, name: str):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"Missing column(s) {missing} in {name}. Available: {list(df.columns)}")

def _prepare_data() -> pd.DataFrame:
    """Return df4 grouped as (Name, Asset Group, Approved, QTY)."""
    df  = _read_table(DB_PATH, TABLE_MAIN)
    df2 = _read_table(DB_PATH, TABLE_BUILDINGS)

    _ensure(df,  ["Building"], "sdi_dataset")
    _ensure(df2, ["Code", "Name"], "Buildings")

    df["Building_key"] = df["Building"].astype(str).str.strip()
    df2["Code_key"]    = df2["Code"].astype(str).str.strip()
    df2 = df2.drop_duplicates(subset=["Code_key"], keep="first")

    df3 = df.merge(df2, left_on="Building_key", right_on="Code_key", how="left") \
            .drop(columns=["Building_key", "Code_key"])

    df3 = df3.drop(columns=["Owner Rep", "Usage"], errors="ignore")

    if "Approved" not in df3.columns:
        df3["Approved"] = ""
    df3["Approved"] = df3["Approved"].fillna("").astype(str).str.strip()
    df3["Approved_label"] = df3["Approved"].eq("1").replace({True: "Approved", False: "Not Approved"})

    _ensure(df3, ["Name", "Asset Group", "Approved_label", "QR Code"], "merged")
    df3["Name"] = df3["Name"].fillna("Unknown").astype(str).str.strip()
    df3["Asset Group"] = df3["Asset Group"].fillna("Unknown").astype(str).str.strip()

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

def _draw_pill_stacked(ax, x_centers, totals, approved, width=0.62):
    rounding = width / 2.0
    max_total = max(totals) if len(totals) else 0
    for x, total, app in zip(x_centers, totals, approved):
        notapp = max(total - app, 0)
        if total <= 0:
            continue
        x0 = x - width / 2.0
        clip = FancyBboxPatch((x0, 0), width, total,
                              boxstyle=f"round,pad=0,rounding_size={rounding}",
                              linewidth=0, facecolor="none", edgecolor="none")
        ax.add_patch(clip)
        seg_not = Rectangle((x0, 0), width, notapp, facecolor=COLOR_NOTAPP, edgecolor="none")
        seg_not.set_clip_path(clip); ax.add_patch(seg_not)
        seg_app = Rectangle((x0, notapp), width, app, facecolor=COLOR_APPROVED, edgecolor="none")
        seg_app.set_clip_path(clip); ax.add_patch(seg_app)
        ax.text(x, total, str(int(total)), ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, max_total * 1.15 if max_total else 1)

def render_chart_png(building: str = "All") -> bytes:
    """Return PNG bytes of the chart (bar + pie)."""
    fig, (ax_bar, ax_pie) = plt.subplots(1, 2, figsize=(16, 7), gridspec_kw={"width_ratios": [3, 1]})
    for ax in (ax_bar, ax_pie): ax.set_facecolor(BG_FACE)

    try:
        df4 = _prepare_data()
        filtered = df4 if (building == "All" or not building) else df4[df4["Name"] == building]
    except Exception as e:
        ax_bar.text(0.5, 0.5, f"Data error:\n{e}", ha="center", va="center", fontsize=12, wrap=True)
        ax_bar.set_xticks([]); ax_bar.set_yticks([]); ax_pie.axis("off")
        buf = io.BytesIO(); fig.tight_layout()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight"); plt.close(fig); buf.seek(0)
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
        totals = (wide["Not Approved"] + wide["Approved"]).to_numpy()
        approved_vals = wide["Approved"].to_numpy()
        x = np.arange(len(groups))

        _draw_pill_stacked(ax_bar, x, totals, approved_vals, width=0.62)
        ax_bar.set_xlabel("Asset Group"); ax_bar.set_ylabel("")
        ax_bar.set_xticks(x, groups, rotation=45, ha="right")
        for lbl in ax_bar.get_xticklabels(): lbl.set_fontsize(lbl.get_fontsize() * 0.8)
        ax_bar.legend(handles=[
            Patch(facecolor=COLOR_APPROVED, edgecolor="none", label="Approved"),
            Patch(facecolor=COLOR_NOTAPP, edgecolor="none", label="Not Approved"),
        ], title="Status", frameon=False)
        for s in ax_bar.spines.values(): s.set_visible(False)
        ax_bar.grid(False); ax_bar.tick_params(axis="both", which="both", length=0); ax_bar.set_yticks([])

        app_total = int(filtered.loc[filtered["Approved"] == "Approved", "QTY"].sum())
        not_total = int(filtered.loc[filtered["Approved"] == "Not Approved", "QTY"].sum())
        if app_total + not_total == 0:
            ax_pie.text(0.5, 0.5, "No totals", ha="center", va="center", fontsize=12); ax_pie.axis("off")
        else:
            wedges, texts, autotexts = ax_pie.pie(
                [app_total, not_total],
                labels=["Approved", "Not Approved"],
                colors=[COLOR_APPROVED, COLOR_NOTAPP],
                autopct=lambda p: f"{p:.0f}%",
                startangle=90, counterclock=False,
                wedgeprops={"linewidth": 0, "edgecolor": "none"},
                textprops={"fontsize": 11, "color": "black"},
            )
            for a in autotexts: a.set_color("black"); a.set_fontweight("normal")
            for t in texts: t.set_color("black")
            for w, t, a in zip(wedges, texts, autotexts):
                if t.get_text() == "Approved":
                    a.set_color("white"); a.set_fontweight("bold")
            ax_pie.axis("equal"); ax_pie.set_title("Overall Approval %")
        for s in ax_pie.spines.values(): s.set_visible(False)
        ax_pie.set_xticks([]); ax_pie.set_yticks([])

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
