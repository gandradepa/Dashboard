import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import io
import os
from matplotlib.lines import Line2D

# --- Configuration ---
DB_PATH_DEFAULT = r"/home/developer/asset_capture_app_dev/data/QR_codes.db"
DB_PATH = os.getenv("DASHBOARD_DB_PATH", DB_PATH_DEFAULT)
TABLE_QR_CODE_ASSETS = "QR_code_assets"
TABLE_BUILDINGS = "Buildings"
TABLE_QR_CODES = "QR_codes"

def _get_data(building: str = "All"):
    """Fetches and processes data from the database."""
    with sqlite3.connect(DB_PATH) as conn:
        df_assets = pd.read_sql_query(f'SELECT * FROM "{TABLE_QR_CODE_ASSETS}"', conn)
        df_buildings = pd.read_sql_query(f'SELECT "Code", "Name" FROM "{TABLE_BUILDINGS}"', conn)
        df_qr_codes = pd.read_sql_query(f'SELECT * FROM "{TABLE_QR_CODES}"', conn)

    processed_df = df_assets[['code_assets']].copy()
    processed_df['QR_code_ID'] = processed_df['code_assets'].str[:10]
    split_data = processed_df['code_assets'].str.split(' ', n=2, expand=True)
    processed_df['Code'] = split_data[1]
    
    qr_building = pd.merge(processed_df, df_buildings, on='Code', how='inner')
    final_df = qr_building[['QR_code_ID', 'Code', 'Name']].drop_duplicates().reset_index(drop=True)
    
    operational_cost = pd.merge(df_qr_codes, final_df, on='QR_code_ID', how='inner')
    operational_cost['date_set'] = pd.to_datetime(operational_cost['date_set'], errors='coerce')
    operational_cost.dropna(subset=['date_set'], inplace=True)

    # ADDED: Filter for the last 12 months
    start_date = pd.Timestamp.now() - pd.DateOffset(months=12)
    operational_cost = operational_cost[operational_cost['date_set'] >= start_date].copy()
    
    operational_cost['date'] = operational_cost['date_set'].dt.date
    operational_cost['time'] = operational_cost['date_set'].dt.time
    operational_cost.rename(columns={'Name': 'Property'}, inplace=True)
    
    if building != "All":
        operational_cost = operational_cost[operational_cost['Property'] == building]
    
    operational_cost_grouped = operational_cost.groupby(['date', 'Property']).agg(
        qty_asset=('Code', 'count'),
        min_time=('time', 'min'),
        max_time=('time', 'max')
    ).reset_index()

    dummy_date = pd.to_datetime('1970-01-01').date()
    max_dt = operational_cost_grouped['max_time'].apply(lambda t: pd.to_datetime(f"{dummy_date} {t}"))
    min_dt = operational_cost_grouped['min_time'].apply(lambda t: pd.to_datetime(f"{dummy_date} {t}"))
    
    operational_cost_grouped['total_seconds'] = (max_dt - min_dt).dt.total_seconds()
    operational_cost_grouped = operational_cost_grouped[operational_cost_grouped['min_time'] != operational_cost_grouped['max_time']].copy()
    
    return operational_cost_grouped

def _draw_combo_chart(ax, data):
    """Draws the daily operational combo chart."""
    if data.empty:
        ax.text(0.5, 0.5, "No data available for this chart.", ha='center', va='center')
        ax.axis('off')
        return

    chart_df = data.copy()
    chart_df['date'] = pd.to_datetime(chart_df['date'])
    chart_df.sort_values('date', inplace=True)

    daily_summary = chart_df.groupby('date').agg(
        total_qty=('qty_asset', 'sum'),
        total_time_seconds=('total_seconds', 'sum')
    ).reset_index()
    daily_summary['weighted_avg_time_minutes'] = (daily_summary['total_time_seconds'] / daily_summary['total_qty'].replace(0, 1)) / 60

    lollipop_color = '#240046'
    line_color = '#7b2cbf'
    fill_color = '#e0c3fc'
    
    x_pos = range(len(daily_summary['date']))

    # --- Area Chart (ax for Average Time) ---
    ax.plot(x_pos, daily_summary['weighted_avg_time_minutes'], color=line_color, linewidth=2.5, zorder=10)
    ax.fill_between(x_pos, daily_summary['weighted_avg_time_minutes'], color=fill_color, alpha=0.45, zorder=5)

    # --- Lollipop Chart (ax2 for Qty of Assets) ---
    ax2 = ax.twinx()
    
    ax2.vlines(x=x_pos, ymin=0, ymax=daily_summary['total_qty'], color=lollipop_color, lw=1.2, zorder=1)

    ax2.scatter(x_pos, daily_summary['total_qty'], s=500, color=lollipop_color, zorder=15)
    ax2.scatter(x_pos, daily_summary['total_qty'], s=350, color='white', zorder=16)

    ax.set_zorder(ax2.get_zorder() + 1)
    ax.patch.set_visible(False)
    
    # --- Title (Left Aligned) ---
    ax.set_title('Operational Asset Data Capture Performance', fontsize=20, fontweight='bold', color='#240046', pad=60, loc='left')
    
    # --- Axes and Ticks ---
    ax.set_xlabel('')
    ax.set_xticks(x_pos)
    ax.set_xticklabels(daily_summary['date'].dt.strftime('%Y-%m-%d'), rotation=0, ha='center')
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_color('#B0B0B0')
    
    for spine in ax2.spines.values():
        spine.set_visible(False)
    
    ax.tick_params(axis='y', length=0)
    ax.tick_params(axis='x', length=0)
    ax2.tick_params(axis='y', length=0)
    ax.set_yticklabels([])
    ax2.set_yticklabels([])

    # --- Data Labels ---
    for i, v in enumerate(daily_summary['total_qty']):
        if v > 0:
            ax2.text(i, v, f'{int(v)}', ha='center', va='center', color=lollipop_color, fontsize=10, fontweight='bold', zorder=17)
    
    y_offset = ax.get_ylim()[1] * 0.03
    for i, v in enumerate(daily_summary['weighted_avg_time_minutes']):
        ax.text(i, v + y_offset, f'{v:.2f}', ha='center', va='bottom', color=line_color, fontsize=10, fontweight='bold', zorder=20)
            
    # --- Custom Legend ---
    legend_elements = [
        Line2D([0], [0], color=line_color, lw=2, label='Average Time in Min'),
        Line2D([0], [0], marker='o', color='w', label='Qty of Assets',
               markerfacecolor=lollipop_color, markersize=10)
    ]
    ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(-0.01, 1.12), ncol=2, frameon=False, fontsize=12.5)


def _draw_card(ax, value, title):
    """Draws a card-style chart."""
    ax.text(0.5, 0.45, value, ha='center', va='center', fontsize=48, fontweight='bold', color='#03045e')
    ax.text(0.5, 0.95, title, ha='center', va='top', fontsize=14, color='gray', linespacing=1.3)
    ax.axis('off')

def render_chart_png(chart_type: str = "combo", building: str = "All") -> bytes:
    """Renders the specified operational cost chart to a PNG byte string."""
    try:
        data = _get_data(building=building)
    except Exception as e:
        print(f"Error getting data for operational cost chart: {e}")
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(0.5, 0.5, "Error: Could not load data for this chart.", ha='center', va='center')
        buf = io.BytesIO()
        fig.savefig(buf, format="png", transparent=True); plt.close(fig); buf.seek(0)
        return buf.read()

    fig, ax = plt.subplots(figsize=(14, 8))
    fig.patch.set_facecolor('none')
    ax.set_facecolor('none')
    
    if chart_type == "combo":
        _draw_combo_chart(ax, data)
    elif chart_type in ["weighted_avg_time", "ai_cost"]:
        plt.close(fig) 
        fig, ax = plt.subplots(figsize=(4, 2.5))
        fig.patch.set_facecolor('none')
        ax.set_facecolor('none')
        
        total_qty = data['qty_asset'].sum()
        total_seconds = data['total_seconds'].sum()

        if chart_type == "weighted_avg_time":
            avg_seconds = total_seconds / total_qty if total_qty > 0 else 0
            m_avg = int(avg_seconds // 60)
            s_avg = int(avg_seconds % 60)
            value = f"{m_avg:02d}:{s_avg:02d}"
            _draw_card(ax, value, "Weighted Avg Time to Capture\nan Asset (MM:SS)")
        elif chart_type == "ai_cost":
            ai_est_cost = total_qty * 0.01
            value = f"${ai_est_cost:.2f}"
            _draw_card(ax, value, "Annual AI Estimated Cost\n(Last 12 Months)")

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf.read()