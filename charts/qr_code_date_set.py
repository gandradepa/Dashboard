import os
import pandas as pd
from datetime import datetime
import sqlite3

# --- PART 1: GENERATE DATAFRAME FROM PHOTOS ---
directory_path = r"S:\MaintOpsPlan\AssetMgt\Asset Management Process\Database\8. New Assets\Git_control\API Picture Test\fixed_photos"
file_ids = []
creation_dates = []

df = pd.DataFrame()

if os.path.exists(directory_path):
    for filename in os.listdir(directory_path):
        if filename.lower().endswith(('.jpg', '.jpeg')):
            base_name = os.path.splitext(filename)[0]
            qr_code_id = base_name[:10]
            file_ids.append(qr_code_id)
            
            full_file_path = os.path.join(directory_path, filename)
            creation_timestamp = os.path.getctime(full_file_path)
            creation_datetime = datetime.fromtimestamp(creation_timestamp)
            creation_dates.append(creation_datetime)

    data = {'QR_code_ID': file_ids, 'date_set': creation_dates}
    df = pd.DataFrame(data)
    print("✅ DataFrame created successfully from photos.")
    print(df.head())
else:
    print(f"❌ Error: The photo directory '{directory_path}' was not found.")

print("-" * 40)

# --- PART 2: UPDATE THE SQLITE DATABASE ---
if not df.empty:
    
    # ===================================================================
    # FIX: Convert the 'date_set' column from Timestamp to string format.
    # This ensures compatibility with the SQLite driver.
    df['date_set'] = df['date_set'].astype(str)
    # ===================================================================

    db_path = r"S:\MaintOpsPlan\AssetMgt\Asset Management Process\Database\8. New Assets\Git_control\API Picture Test\QR_codes.db"
    connection = None

    try:
        print(f"🔄 Connecting to database at '{db_path}'...")
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        sql_update_query = """
        UPDATE QR_codes
        SET date_set = ?
        WHERE QR_code_ID = ?
        """

        print("🚀 Starting database update process...")
        for index, row in df.iterrows():
            # The 'date_set' value is now a string, which SQLite understands
            cursor.execute(sql_update_query, (row['date_set'], row['QR_code_ID']))
        
        connection.commit()
        print(f"\n✅ Success! Updated {len(df)} records in the database.")

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        print("No changes were saved. The transaction has been rolled back.")

    finally:
        if connection:
            connection.close()
            print("🔌 Database connection closed.")