import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import io
import os

# --- Configuration ---
DB_PATH_DEFAULT = r"/home/developer/asset_capture_app_dev/data/QR_codes.db"
DB_PATH = os.getenv("DASHBOARD_DB_PATH", DB_PATH_DEFAULT)
TABLE_QR_CODE_ASSETS = "QR_code_assets"
TABLE_BUILDINGS = "Buildings"
TABLE_QR_CODES = "QR_codes"

def _get_data():
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
    
    operational_cost['date'] = operational_cost['date_set'].dt.date
    operational_cost['time'] = operational_cost['date_set'].dt.time
    operational_cost.rename(columns={'Name': 'Property'}, inplace=True)
    
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

    chart_df['record_time_asset_minutes'] = (chart_df['total_seconds'] / chart_df['qty_asset'].replace(0, 1)) / 60.0

    daily_summary = chart_df.groupby('date').agg(
        total_qty=('qty_asset', 'sum'),
        total_time_seconds=('total_seconds', 'sum')
    ).reset_index()
    daily_summary['weighted_avg_time_minutes'] = (daily_summary['total_time_seconds'] / daily_summary['total_qty'].replace(0, 1)) / 60

    bar_color = '#03045e'
    line_color = '#6A6AD8'
    x_pos = range(len(daily_summary['date']))

    ax.plot(x_pos, daily_summary['weighted_avg_time_minutes'], color=line_color, marker='o', linestyle='-',
             linewidth=3, markersize=10, markerfacecolor='white',
             markeredgecolor=line_color, markeredgewidth=3, label='Average Time in Min')

    ax2 = ax.twinx()
    ax2.bar(x_pos, daily_summary['total_qty'], width=0.7, color=bar_color, align='center', label='Qty of Assets')

    ax.set_zorder(ax2.get_zorder() + 1)
    ax.patch.set_visible(False)
    
    ax.set_title('Operational Asset Data Capture Performance', fontsize=20, fontweight='bold', color='#03045e', pad=60)
    ax.set_xlabel('Execution Date', fontsize=12, labelpad=10)
    
    ax.set_xticks(x_pos)
    ax.set_xticklabels(daily_summary['date'].dt.strftime('%Y-%m-%d'), rotation=45, ha='right')
    
    for spine in ['top', 'right', 'left']:
        ax.spines[spine].set_visible(False)
        ax2.spines[spine].set_visible(False)
    ax.spines['bottom'].set_color('#B0B0B0')
    
    ax.tick_params(axis='y', length=0)
    ax2.tick_params(axis='y', length=0)
    ax.set_yticklabels([])
    ax2.set_yticklabels([])

    for i, v in enumerate(daily_summary['total_qty']):
        if v > 0:
            ax2.text(i, v / 2, f'{int(v)}', ha='center', va='center', color='white', fontsize=12, fontweight='bold')
    
    y_offset = ax.get_ylim()[1] * 0.02 if ax.get_ylim()[1] > 0 else 0.1
    for i, v in enumerate(daily_summary['weighted_avg_time_minutes']):
        ax.text(i, v + y_offset, f'{v:.2f}', ha='center', va='bottom', color=line_color, fontsize=10)
            
    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(handles1 + handles2, labels1 + labels2, loc='lower center', bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False, fontsize=12.5)


def _draw_card(ax, value, title):
    """Draws a card-style chart."""
    ax.text(0.5, 0.5, value, ha='center', va='center', fontsize=48, fontweight='bold', color='#03045e')
    ax.text(0.5, 0.85, title, ha='center', va='center', fontsize=14, color='gray')
    ax.axis('off')

def render_chart_png(chart_type: str = "combo") -> bytes:
    """Renders the specified operational cost chart to a PNG byte string."""
    try:
        data = _get_data()
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
            _draw_card(ax, value, "Weighted Avg Time (MM:SS)")
        elif chart_type == "ai_cost":
            ai_est_cost = total_qty * 0.10
            value = f"${ai_est_cost:.2f}"
            _draw_card(ax, value, "AI Estimated Cost")

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, transparent=True)
    plt.close(fig)
    buf.seek(0)
    return buf.read()

