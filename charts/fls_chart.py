import pandas as pd
import sqlite3
import os
import altair as alt

TITLE_FONT_SIZE = 26
AXIS_TITLE_FONT_SIZE = 18
AXIS_LABEL_FONT_SIZE = 16

def fls_df():
    """
    Connects to the QR_codes.db database, reads the 'new_device' table,
    and returns the data as a pandas DataFrame.
    """
    # --- Database Connection Setup ---
    db_path = r"/home/developer/asset_capture_app_dev/data/QR_codes.db"

    if not os.path.exists(db_path):
        print(f"Error: Database file not found at '{db_path}'")
        return pd.DataFrame()

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        query = "SELECT * FROM new_device"
        df = pd.read_sql_query(query, conn)
        print(f"Successfully loaded {len(df)} rows from the 'new_device' table.")
        return df

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return pd.DataFrame()
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

def generate_charts():
    """
    Generates specific Altair charts and saves them as HTML files in the 'static' directory.
    """
    # --- Setup Paths ---
    basedir = os.path.abspath(os.path.dirname(__file__))
    app_dir = os.path.dirname(basedir)
    
    if os.path.basename(basedir) == 'charts':
        static_dir = os.path.join(app_dir, 'static')
    else:
        static_dir = os.path.join(basedir, 'static')
    
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
        print(f"Created static directory at: {static_dir}")

    new_device_dataframe = fls_df()

    if not new_device_dataframe.empty:
        print("\n--- Processing Data ---")

        # --- [FIX 1] Rename [Creation Date] column to 'Creation Date' ---
        if '[Creation Date]' in new_device_dataframe.columns:
            new_device_dataframe.rename(columns={'[Creation Date]': 'Creation Date'}, inplace=True)
        elif 'Creation Date' not in new_device_dataframe.columns:
            print("Error: 'Creation Date' column not found. Cannot proceed.")
            return

        # --- [FIX 2] Normalize 'Workflow' column ---
        if 'Workflow' in new_device_dataframe.columns:
            new_device_dataframe['Workflow'] = new_device_dataframe['Workflow'].fillna('New').astype(str)
            new_device_dataframe['Workflow_Normalized'] = new_device_dataframe['Workflow'].str.strip().str.lower()
        else:
            print("Warning: 'Workflow' column not found. Cannot create charts.")
            return 

        # --- [FIX 3] Use normalized column for filtering ---
        filtered_df = new_device_dataframe[~new_device_dataframe['Workflow_Normalized'].str.startswith('complete')].copy()

        columns_to_keep = ["Property", "Status", "Workflow", "Creation Date"]
        
        if all(col in filtered_df.columns for col in columns_to_keep):
            fls_df1 = filtered_df[columns_to_keep].copy()
            fls_df1['Creation Date'] = pd.to_datetime(fls_df1['Creation Date'], errors='coerce').dt.normalize()
            
            today = pd.to_datetime('today').normalize()
            fls_df1['QTY of Days'] = (today - fls_df1['Creation Date']).dt.days
            fls_df1.dropna(subset=['QTY of Days'], inplace=True)
            fls_df1['QTY of Days'] = fls_df1['QTY of Days'].astype(int)

            fls_df2 = fls_df1.drop(columns=['Creation Date'])

            # --- Prepare Summary Data for Priority Chart ---
            summary_df = fls_df2.groupby(["Property", "Status", "Workflow"]).agg(
                Average_Days=('QTY of Days', 'mean'),
                Device_QTY=('Status', 'size') 
            ).reset_index()
            summary_df["Average_Days"] = summary_df["Average_Days"].round().astype(int)
            summary_df["Device_QTY"] = summary_df["Device_QTY"].astype(int)

            # --- Prepare Data for Monitor Chart ---
            temp_df = new_device_dataframe.copy()
            temp_df['Creation Date'] = pd.to_datetime(temp_df['Creation Date'], errors='coerce').dt.normalize()
            today = pd.to_datetime('today').normalize()
            temp_df['QTY of Days'] = (today - temp_df['Creation Date']).dt.days
            temp_df.dropna(subset=['QTY of Days'], inplace=True)
            temp_df['QTY of Days'] = temp_df['QTY of Days'].astype(int)

            workflow_stats_df = temp_df.groupby('Workflow').agg(
                Device_QTY=('Workflow', 'size'),
                Average_Days=('QTY of Days', 'mean')
            ).reset_index()
            workflow_stats_df["Device_QTY"] = workflow_stats_df["Device_QTY"].astype(int)
            workflow_stats_df["Average_Days"] = workflow_stats_df["Average_Days"].round().astype(int)

            # ==========================================
            # CHART 1: Devices in Process - Monitor (Matches visualization 3)
            # ==========================================
            workflow_order = ['New', 'Assigned', 'In Progress', 'Pending', 'Complete']
            funnel_chart = alt.Chart(workflow_stats_df).mark_bar().encode(
                x=alt.X(
                    'Device_QTY:Q',
                    title='Number of Devices',
                    stack='center',
                    axis=alt.Axis(
                        format='d',
                        tickMinStep=1,
                        titleFontSize=AXIS_TITLE_FONT_SIZE,
                        labelFontSize=AXIS_LABEL_FONT_SIZE
                    )
                ),
                y=alt.Y(
                    'Workflow:N',
                    title='Workflow Stage',
                    sort=workflow_order,
                    axis=alt.Axis(
                        titleFontSize=AXIS_TITLE_FONT_SIZE,
                        labelFontSize=AXIS_LABEL_FONT_SIZE
                    )
                ),
                color=alt.Color('Workflow:N', legend=None, sort=workflow_order),
                tooltip=[
                    alt.Tooltip('Workflow:N', title='Stage'),
                    alt.Tooltip('Device_QTY:Q', title='Device Count'),
                    alt.Tooltip('Average_Days:Q', title='Avg Days in Stage', format='d')
                ]
            ).properties(
                title=alt.TitleParams(
                    text='Devices in Process - Monitor',
                    fontSize=TITLE_FONT_SIZE
                ),
                width='container', 
                height=300  # Adjusted height to ensure fit
            )
            funnel_filename = os.path.join(static_dir, 'devices_in_process_monitor.html')
            funnel_chart.save(funnel_filename)
            print(f"Chart saved successfully to '{funnel_filename}'")

            # ==========================================
            # CHART 2: Prioritization Chart (Matches visualization 2)
            # ==========================================
            scatter_plot = (
                alt.Chart(summary_df)
                .mark_circle()
                .encode(
                    x=alt.X(
                        'Average_Days:Q',
                        title='Average Days Outstanding',
                        axis=alt.Axis(
                            format='d',
                            tickMinStep=1,
                            titleFontSize=AXIS_TITLE_FONT_SIZE,
                            labelFontSize=AXIS_LABEL_FONT_SIZE
                        )
                    ),
                    y=alt.Y(
                        'Device_QTY:Q',
                        title='Outstanding Devices',
                        axis=alt.Axis(
                            format='d',
                            tickMinStep=1,
                            titleFontSize=AXIS_TITLE_FONT_SIZE,
                            labelFontSize=AXIS_LABEL_FONT_SIZE
                        )
                    ),
                    size=alt.Size('Device_QTY:Q', title='Device Count'),
                    color=alt.Color('Workflow:N', title='Workflow'),
                    tooltip=[
                        'Property:N',
                        'Workflow:N',
                        alt.Tooltip('Average_Days:Q', title='Avg Days Outstanding', format='d'),
                        'Device_QTY:Q'
                    ]
                )
            )

            threshold_line = alt.Chart(pd.DataFrame({'threshold': [10]})).mark_rule(
                color='red',
                strokeWidth=2,
                strokeDash=[5, 3] 
            ).encode(x='threshold:Q')

            priority_chart_with_line = (scatter_plot + threshold_line).properties(
                width='container', 
                height=320, # Adjusted height to ensure fit
                title=alt.TitleParams(
                    text='Prioritization: Aging vs Outstanding Quantity (>10 Day Breach)',
                    fontSize=TITLE_FONT_SIZE
                )
            )

            priority_filename = os.path.join(static_dir, 'priority_chart.html')
            priority_chart_with_line.save(priority_filename)
            print(f"Chart saved successfully to '{priority_filename}'")
            
            # Note: Unused charts (Outstanding Devices Bar Chart & Gantt Chart) have been removed.

        else:
            print(f"\nError: 'filtered_df' is missing one of the required columns: {columns_to_keep}")

    else:
        print("\nCould not retrieve data. The DataFrame is empty.")

if __name__ == '__main__':
    generate_charts()
