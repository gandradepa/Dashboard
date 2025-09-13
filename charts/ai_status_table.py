import pandas as pd
import sqlite3
import os

def read_and_process_asset_codes():
    """
    Connects to a SQLite database, reads and processes asset data.

    This function performs several steps:
    1. Reads data from 'QR_code_assets', 'sdi_dataset', and 'sdi_dataset_EL'.
    2. Splits the main 'code_assets' column.
    3. Creates an 'ai_status' column based on whether a QR_code_ID exists
       in the sdi tables ('1' for exists, '0' for not).
    4. Removes duplicates.
    5. Filters to keep only rows where 'ai_status' is '0'.
    6. Merges with the 'Buildings' table to add building names and renames the column to 'Property'.
    7. Renames asset type abbreviations to full names.
    8. Returns the final processed pandas DataFrame.
    """
    db_path = r"/home/developer/asset_capture_app_dev/data/QR_codes.db"

    if not os.path.exists(db_path):
        print(f"Error: Database file not found at path: {db_path}")
        return None

    try:
        conn = sqlite3.connect(db_path)

        # --- Load and process data in sequential steps ---

        # Load comparison QR codes
        qr_codes_to_check = set()
        try:
            sdi_ds = pd.read_sql_query('SELECT "QR Code" FROM sdi_dataset', conn)
            sdi_el = pd.read_sql_query('SELECT "QR Code" FROM sdi_dataset_EL', conn)
            sdi_ds_codes = set(sdi_ds['QR Code'].dropna().astype(str))
            sdi_el_codes = set(sdi_el['QR Code'].dropna().astype(str))
            qr_codes_to_check = sdi_ds_codes.union(sdi_el_codes)
        except (sqlite3.Error, pd.io.sql.DatabaseError, KeyError):
            pass  # Fail silently if comparison tables are missing

        # Load and split main asset data
        ai_asset_outstanding = pd.read_sql_query("SELECT code_assets FROM QR_code_assets", conn)
        split_data = ai_asset_outstanding['code_assets'].str.split(' ', expand=True)
        ai_asset_outstanding['QR_code_ID'] = split_data[0]
        ai_asset_outstanding['Code'] = split_data[1]
        ai_asset_outstanding['type_of_asset'] = split_data[2]
        ai_asset_outstanding.drop(columns=['code_assets'], inplace=True)

        # Create status column
        if qr_codes_to_check:
            ai_asset_outstanding['ai_status'] = ai_asset_outstanding['QR_code_ID'].apply(
                lambda qr_id: '1' if qr_id in qr_codes_to_check else '0'
            )

        # Clean and filter data
        ai_asset_outstanding.drop_duplicates(inplace=True)
        if 'ai_status' in ai_asset_outstanding.columns:
            ai_asset_outstanding = ai_asset_outstanding[ai_asset_outstanding['ai_status'] == '0'].copy()

        # Merge with Buildings data and rename the column
        try:
            buildings_df = pd.read_sql_query('SELECT "Code", "Name" FROM Buildings', conn)
            ai_asset_outstanding = pd.merge(ai_asset_outstanding, buildings_df, on='Code', how='left')
            ai_asset_outstanding.rename(columns={'Name': 'Property'}, inplace=True)
        except (sqlite3.Error, pd.io.sql.DatabaseError, KeyError):
            pass # Fail silently if Buildings table is missing

        # Rename asset types
        rename_map = {"ME": "Mechanical", "BF": "Backflow", "EL": "Electrical"}
        ai_asset_outstanding['type_of_asset'] = ai_asset_outstanding['type_of_asset'].replace(rename_map)

        return ai_asset_outstanding

    except (sqlite3.Error, Exception) as e:
        print(f"An unexpected error occurred: {e}")
        return None
    finally:
        if 'conn' in locals() and conn:
            conn.close()


if __name__ == '__main__':
    # Get the processed data
    ai_asset_outstanding = read_and_process_asset_codes()

    # Create the grouped dataset and print it
    if ai_asset_outstanding is not None and not ai_asset_outstanding.empty:
        ai_asset_outstanding_group = ai_asset_outstanding.groupby('Property').size().reset_index(name='Pendency QTY')
        print(ai_asset_outstanding_group)
    elif ai_asset_outstanding is not None:
        print("The final DataFrame is empty after processing.")

