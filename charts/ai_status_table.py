import pandas as pd
import sqlite3
import os

def read_and_process_asset_codes():
    """
    Connects to a SQLite database, reads and processes asset data.
    This version includes more robust error handling and logging.
    """
    db_path = r"/home/developer/asset_capture_app_dev/data/QR_codes.db"

    if not os.path.exists(db_path):
        print(f"Error: Database file not found at path: {db_path}")
        return None

    try:
        conn = sqlite3.connect(db_path)

        # --- Load and split main asset data first ---
        try:
            ai_asset_outstanding = pd.read_sql_query("SELECT code_assets FROM QR_code_assets", conn)
            if ai_asset_outstanding.empty:
                print("Warning: The 'QR_code_assets' table is empty. No assets to process.")
                return pd.DataFrame() # Return an empty DataFrame
        except (sqlite3.Error, pd.io.sql.DatabaseError) as e:
            print(f"CRITICAL ERROR: Could not read from 'QR_code_assets' table: {e}")
            return None

        split_data = ai_asset_outstanding['code_assets'].str.split(' ', expand=True)
        ai_asset_outstanding['QR_code_ID'] = split_data[0]
        ai_asset_outstanding['Code'] = split_data[1]
        ai_asset_outstanding['type_of_asset'] = split_data[2]
        ai_asset_outstanding.drop(columns=['code_assets'], inplace=True)
        ai_asset_outstanding.drop_duplicates(inplace=True)

        # --- Load comparison QR codes with clear feedback ---
        qr_codes_to_check = set()
        try:
            sdi_ds = pd.read_sql_query('SELECT "QR Code" FROM sdi_dataset', conn)
            sdi_ds_codes = set(sdi_ds['QR Code'].dropna().astype(str))
            qr_codes_to_check.update(sdi_ds_codes)
            print(f"Successfully loaded {len(sdi_ds_codes)} codes from sdi_dataset.")
        except (sqlite3.Error, pd.io.sql.DatabaseError, KeyError):
            print("Warning: Could not load data from 'sdi_dataset' table. It may be missing.")

        try:
            sdi_el = pd.read_sql_query('SELECT "QR Code" FROM sdi_dataset_EL', conn)
            sdi_el_codes = set(sdi_el['QR Code'].dropna().astype(str))
            qr_codes_to_check.update(sdi_el_codes)
            print(f"Successfully loaded {len(sdi_el_codes)} codes from sdi_dataset_EL.")
        except (sqlite3.Error, pd.io.sql.DatabaseError, KeyError):
            print("Warning: Could not load data from 'sdi_dataset_EL' table. It may be missing.")

        # --- Create status column and filter ---
        # If the set of codes to check is empty, all assets are considered pending ('0')
        if not qr_codes_to_check:
            print("No processed QR codes found. All assets from QR_code_assets will be marked as pending.")
            ai_asset_outstanding['ai_status'] = '0'
        else:
            ai_asset_outstanding['ai_status'] = ai_asset_outstanding['QR_code_ID'].apply(
                lambda qr_id: '1' if qr_id in qr_codes_to_check else '0'
            )
        
        # Filter to keep only pending assets
        pending_assets = ai_asset_outstanding[ai_asset_outstanding['ai_status'] == '0'].copy()
        print(f"Found {len(pending_assets)} pending assets after filtering.")


        # --- Merge with Buildings data ---
        if not pending_assets.empty:
            try:
                buildings_df = pd.read_sql_query('SELECT "Code", "Name" FROM Buildings', conn)
                pending_assets = pd.merge(pending_assets, buildings_df, on='Code', how='left')
                pending_assets.rename(columns={'Name': 'Property'}, inplace=True)
            except (sqlite3.Error, pd.io.sql.DatabaseError, KeyError):
                print("Warning: Could not merge with 'Buildings' table. 'Property' column will be missing.")
                pending_assets['Property'] = 'Unknown'
        
            # Rename asset types
            rename_map = {"ME": "Mechanical", "BF": "Backflow", "EL": "Electrical"}
            pending_assets['type_of_asset'] = pending_assets['type_of_asset'].replace(rename_map)

        return pending_assets

    except Exception as e:
        print(f"An unexpected error occurred in read_and_process_asset_codes: {e}")
        return None
    finally:
        if 'conn' in locals() and conn:
            conn.close()


def get_pending_assets():
    """
    Processes asset data and returns both a detailed list and a summary.
    This is the main function to be called from the Flask application.
    """
    ai_asset_outstanding = read_and_process_asset_codes()

    if ai_asset_outstanding is None or ai_asset_outstanding.empty:
        return None, None
    
    ai_asset_outstanding_group = ai_asset_outstanding.groupby('Property').size().reset_index(name='Pendency QTY')
    
    return ai_asset_outstanding_group, ai_asset_outstanding

