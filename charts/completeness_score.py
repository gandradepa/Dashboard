import pandas as pd
import os
import numpy as np
import sqlite3
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import io

def render_chart_png(building: str = "All") -> bytes:
    """
    Renders the completeness score chart for a given building and returns it as PNG bytes.
    """
    # --- LOAD BUILDING DATASET ---
    try:
        db_path = r"/home/developer/asset_capture_app_dev/data/QR_codes.db"
        conn = sqlite3.connect(db_path)
        query = "SELECT * FROM Buildings"
        building_df = pd.read_sql_query(query, conn)
        conn.close()
        building_df = building_df[["Code", "Name"]]
        building_df = building_df.rename(columns={"Code": "building_number", "Name": "Property"})
    except Exception as e:
        print(f"Warning: Could not read database. {e}")
        building_data = {'building_number': ['314-1', '201T', '405'], 'Property': ['UBC HOSPITAL - ACU', 'HEBB BUILDING', 'CHEMISTRY/PHYSICS']}
        building_df = pd.DataFrame(building_data)

    # --- PROCESS JSON FILES ---
    path = r"/home/developer/Output_jason_api"
    df_list = []
    
    if os.path.exists(path):
        for filename in os.listdir(path):
            if filename.endswith('.json') and any(s in filename for s in ["_ME_", "_BF_", "_EL_"]):
                try:
                    df_list.append(pd.read_json(os.path.join(path, filename)))
                except Exception:
                    pass

    if not df_list:
        return b''

    combined_df = pd.concat(df_list, ignore_index=True)
    columns_to_select = ["building_number", "Approved", "asset_type", "completeness_score"]
    existing_columns = [col for col in columns_to_select if col in combined_df.columns]
    completeness_score = combined_df[existing_columns].copy()

    if 'Approved' not in completeness_score.columns:
        completeness_score['Approved'] = False
    if 'asset_type' in completeness_score.columns:
        completeness_score['asset_type'] = completeness_score['asset_type'].str.replace(r'[^a-zA-Z]', '', regex=True)

    conditions = [
        completeness_score['asset_type'] == 'ME',
        completeness_score['asset_type'] == 'BF',
        completeness_score['asset_type'] == 'EL'
    ]
    values = [5, 4, 5]
    completeness_score['field_qty'] = np.select(conditions, values, default=0)
    completeness_score['found_value'] = (completeness_score['field_qty'] * (completeness_score['completeness_score'] / 100)).fillna(0).astype('int64')

    completeness_score = completeness_score[completeness_score['Approved'] == False]
    
    final_summary = completeness_score.groupby(['building_number', 'asset_type']).agg(
        field_qty=('field_qty', 'sum'),
        found_value=('found_value', 'sum'),
    ).reset_index()

    final_summary['% of Completeness'] = ((final_summary['found_value'] / final_summary['field_qty']) * 100).replace([np.inf, -np.inf], 0).fillna(0).round(2)
    
    # --- MERGE AND FINALIZE ---
    merged_df = pd.merge(final_summary, building_df, on='building_number', how='left')
    completeness_summary = merged_df[["Property", "building_number", "asset_type", "% of Completeness"]]

    # --- VISUALIZATION BLOCK ---
    if building != "All":
        data_to_plot = completeness_summary[completeness_summary['Property'] == building].sort_values('asset_type')
    else:
        if not completeness_summary.empty:
            first_property = completeness_summary['Property'].iloc[0]
            data_to_plot = completeness_summary[completeness_summary['Property'] == first_property].sort_values('asset_type')
        else:
            data_to_plot = pd.DataFrame()
            
    if data_to_plot.empty:
        return b''

    property_name = data_to_plot['Property'].iloc[0]

    num_charts = len(data_to_plot)
    fig, axes = plt.subplots(1, num_charts, figsize=(num_charts * 2.5, 5), squeeze=False)
    axes = axes.flatten()
    cmap = LinearSegmentedColormap.from_list("custom_RdYlGn", ["#9d0208", "#fcf300", "#008000"])

    for i, (idx, row) in enumerate(data_to_plot.iterrows()):
        ax = axes[i]
        asset_type, score = row['asset_type'], row['% of Completeness']
        gradient = np.linspace(0, 1, 256).reshape(-1, 1)
        ax.imshow(gradient, aspect='auto', cmap=cmap, extent=[0, 1, 0, 100])
        ax.axhline(score, color='black', lw=1.5)
        ax.text(1.1, score, f'{int(round(score))}', va='center', ha='left', fontsize=12, fontweight='bold')
        ax.set_title(asset_type, fontsize=14, fontweight='bold')
        ax.set_ylim(0, 100)
        ax.set_xticks([])
        ax.spines[['top', 'right', 'bottom']].set_visible(False)

    # --- THIS IS THE CORRECTED LINE ---
    fig.suptitle(f'Completeness Score for: {property_name}', fontsize=16, fontweight='bold', y=1.05)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    
    # --- SAVE TO BUFFER ---
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight')
    plt.close(fig)
    buffer.seek(0)
    
    return buffer.getvalue()
