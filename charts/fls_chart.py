import pandas as pd
import sqlite3
import os
import altair as alt

def fls_df():
    """
    Connects to the QR_codes.db database, reads the 'new_device' table,
    and returns the data as a pandas DataFrame.

    Returns:
        pd.DataFrame: A DataFrame containing the data from the 'new_device' table.
                      Returns an empty DataFrame if an error occurs or the table is empty.
    """
    # --- Database Connection Setup ---
    # Use the absolute path to the database for consistency
    db_path = r"/home/developer/asset_capture_app_dev/data/QR_codes.db"

    if not os.path.exists(db_path):
        print(f"Error: Database file not found at '{db_path}'")
        return pd.DataFrame()

    conn = None  # Initialize connection to None
    try:
        # --- Data Retrieval ---
        # Connect to the SQLite database.
        conn = sqlite3.connect(db_path)

        # SQL query to select all data from the 'new_device' table
        query = "SELECT * FROM new_device"

        # Use pandas' highly efficient read_sql_query to execute the query
        # and load the results directly into a DataFrame.
        df = pd.read_sql_query(query, conn)

        print(f"Successfully loaded {len(df)} rows from the 'new_device' table.")
        return df

    except sqlite3.Error as e:
        # Handle potential SQL errors, such as "no such table: new_device"
        print(f"Database error: {e}")
        return pd.DataFrame() # Return an empty DataFrame on error
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return pd.DataFrame()
    finally:
        # --- Connection Teardown ---
        # Always ensure the database connection is closed, even if errors occurred.
        if conn:
            conn.close()
            print("Database connection closed.")

def generate_charts():
    """
    Generates all Altair charts and saves them as HTML files in the 'static' directory.
    """
    # --- Setup Paths ---
    basedir = os.path.abspath(os.path.dirname(__file__))
    # Go one level up from 'charts' to get the main app directory
    app_dir = os.path.dirname(basedir)
    # Set the static_dir relative to the app_dir
    static_dir = os.path.join(app_dir, 'static')
    
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
        print(f"Created static directory at: {static_dir}")

    # Call the function to get the DataFrame
    new_device_dataframe = fls_df()

    # Check if the DataFrame is not empty before trying to display it
    if not new_device_dataframe.empty:
        print("\n--- Original DataFrame Head (First 5 Rows) ---")
        print(new_device_dataframe.head())

        # --- [FIX 1] Rename [Creation Date] column to 'Creation Date' ---
        if '[Creation Date]' in new_device_dataframe.columns:
            new_device_dataframe.rename(columns={'[Creation Date]': 'Creation Date'}, inplace=True)
            print("Successfully renamed '[Creation Date]' to 'Creation Date'.")
        elif 'Creation Date' not in new_device_dataframe.columns:
            print("Error: 'Creation Date' or '[Creation Date]' column not found. Cannot proceed.")
            return

        # --- [FIX 2] Normalize 'Workflow' column ---
        if 'Workflow' in new_device_dataframe.columns:
            new_device_dataframe['Workflow'] = new_device_dataframe['Workflow'].fillna('New').astype(str)
            new_device_dataframe['Workflow_Normalized'] = new_device_dataframe['Workflow'].str.strip().str.lower()
            print("Successfully normalized 'Workflow' column.")
        else:
            print("\nWarning: 'Workflow' column not found. Cannot create charts.")
            return 

        # --- [FIX 3] Use normalized column for filtering ---
        filtered_df = new_device_dataframe[~new_device_dataframe['Workflow_Normalized'].str.startswith('complete')].copy()
        print(f"Filtered out completed tasks. New DF has {len(filtered_df)} rows.")


        columns_to_keep = ["Property", "Status", "Workflow", "Creation Date"]
        
        if all(col in filtered_df.columns for col in columns_to_keep):
            fls_df1 = filtered_df[columns_to_keep].copy()

            fls_df1['Creation Date'] = pd.to_datetime(fls_df1['Creation Date'], errors='coerce').dt.normalize()
            
            today = pd.to_datetime('today').normalize()
            fls_df1['QTY of Days'] = (today - fls_df1['Creation Date']).dt.days

            fls_df1.dropna(subset=['QTY of Days'], inplace=True)
            fls_df1['QTY of Days'] = fls_df1['QTY of Days'].astype(int)

            print(f"\nOriginal DataFrame has {len(new_device_dataframe)} rows.")
            print(f"Filtered DataFrame 'fls_df1' has {len(fls_df1)} rows and {len(fls_df1.columns)} columns.")

            print("\n--- Final DataFrame 'fls_df1' Head (First 5 Rows) ---")
            print(fls_df1.head())

            fls_df2 = fls_df1.drop(columns=['Creation Date'])

            print("\n--- DataFrame 'fls_df2' Head (First 5 Rows) ---")
            print(fls_df2.head())

            summary_df = fls_df2.groupby(["Property", "Status", "Workflow"]).agg(
                Average_Days=('QTY of Days', 'mean'),
                Device_QTY=('Status', 'size') 
            ).reset_index() 

            print("\n--- Summarized DataFrame (Grouped by Property, Status, and Workflow) ---")
            print(summary_df)

            # --- Create Altair Chart ---
            bar_outstanding = (
                alt.Chart(summary_df)
                .mark_bar()
                .encode(
                    y=alt.Y('Property:N', sort='-x', title='Property'),
                    x=alt.X('sum(Device_QTY):Q', title='Outstanding Devices'),
                    color=alt.Color('Workflow:N', title='Workflow'),
                    tooltip=[
                        'Property:N',
                        'Workflow:N',
                        alt.Tooltip('sum(Device_QTY):Q', title='Devices'),
                        alt.Tooltip('Average_Days:Q', title='Avg Days for this Group', format='.1f')
                    ]
                )
                .properties(
                    # --- THIS IS THE FIX ---
                    width='container', # Changed from width=600
                    height=300,
                    title='Outstanding Devices by Property & Workflow'
                )
            )
            
            chart_filename = os.path.join(static_dir, 'outstanding_devices_chart.html')
            bar_outstanding.save(chart_filename)
            print(f"\nChart saved successfully to '{chart_filename}'")
            
            # --- Create Prioritization Bubble Chart with Threshold ---
            scatter_plot = (
                alt.Chart(summary_df)
                .mark_circle()
                .encode(
                    x=alt.X('Average_Days:Q', title='Average Days Outstanding'),
                    y=alt.Y('Device_QTY:Q', title='Outstanding Devices'),
                    size=alt.Size('Device_QTY:Q', title='Device Count'),
                    color=alt.Color('Workflow:N', title='Workflow'),
                    tooltip=[
                        'Property:N',
                        'Workflow:N',
                        alt.Tooltip('Average_Days:Q', title='Avg Days Outstanding', format='.1f'),
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
                # --- THIS IS THE FIX ---
                width='container', # Changed from width=500
                height=350,
                title='Prioritization: Aging vs Outstanding Quantity (>10 Day Breach)'
            )

            priority_filename = os.path.join(static_dir, 'priority_chart.html')
            priority_chart_with_line.save(priority_filename)
            print(f"Chart saved successfully to '{priority_filename}'")

            # --- Prepare Data for New Charts ---
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
            
            print("\n--- Workflow Stats DataFrame (for new charts) ---")
            print(workflow_stats_df)
            
            # --- Create Workflow Funnel Chart ("Devices in Process - Monitor") ---
            workflow_order = ['New', 'Assigned', 'In Progress', 'Pending', 'Complete']
            funnel_chart = alt.Chart(workflow_stats_df).mark_bar().encode(
                x=alt.X('Device_QTY:Q', title='Number of Devices', stack='center'),
                y=alt.Y('Workflow:N', title='Workflow Stage', sort=workflow_order),
                color=alt.Color('Workflow:N', legend=None, sort=workflow_order),
                tooltip=[
                    alt.Tooltip('Workflow:N', title='Stage'),
                    alt.Tooltip('Device_QTY:Q', title='Device Count'),
                    alt.Tooltip('Average_Days:Q', title='Avg Days in Stage', format='.1f')
                ]
            ).properties(
                title='Devices in Process - Monitor',
                # --- THIS IS ALSO FIXED ---
                width='container', # Changed from width=500
                height=300
            )
            funnel_filename = os.path.join(static_dir, 'devices_in_process_monitor.html')
            funnel_chart.save(funnel_filename)
            print(f"Chart saved successfully to '{funnel_filename}'")


            # --- Create Workflow Gantt Chart ("Device Administration") ---
            gantt_df = filtered_df.copy()
            gantt_df['Creation Date'] = pd.to_datetime(gantt_df['Creation Date'], errors='coerce')
            gantt_df.dropna(subset=['Creation Date'], inplace=True) 
            gantt_df['End Date'] = pd.to_datetime('today')
            
            if 'QR_code_ID' in gantt_df.columns:
                 gantt_df['Device Label'] = gantt_df['Property'] + ' (' + gantt_df['QR_code_ID'].astype(str) + ')'
            else:
                 gantt_df['Device Label'] = gantt_df['Property'] + ' (N/A)'


            gantt_chart = alt.Chart(gantt_df).mark_bar(size=15).encode(
                x=alt.X('Creation Date:T', title='Timeline'),
                x2='End Date:T',
                y=alt.Y('Device Label:N', title='Device', sort=alt.SortField(field="Creation Date", order="ascending")),
                color=alt.Color('Workflow:N', title='Current Workflow'),
                tooltip=[
                    'Property:N',
                    'Status:N',
                    'Workflow:N',
                    alt.Tooltip('Creation Date:T', title='Start Date'),
                    alt.Tooltip('QTY of Days:Q', title='Days Active')
                ]
            ).properties(
                title='Device Administration (Active Timelines)',
                # --- THIS IS ALSO FIXED ---
                width='container', # Changed from width=600
                height=400
            )
            gantt_filename = os.path.join(static_dir, 'device_administration.html')
            gantt_chart.save(gantt_filename)
            print(f"Chart saved successfully to '{gantt_filename}'")

        else:
            print(f"\nError: 'filtered_df' is missing one of the required columns: {columns_to_keep}")
            print(f"Available columns: {list(filtered_df.columns)}")

    else:
        print("\nCould not retrieve data. The DataFrame is empty.")


if __name__ == '__main__':
    generate_charts()