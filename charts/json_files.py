import os
import pandas as pd
from datetime import datetime
import sqlite3

def process_files_by_name_and_metadata(path):
    """
    Identifies files in a path, extracts a 'code' from the first 10
    characters of the filename, gets the creation date from file
    properties, removes duplicates keeping the most recent file,
    and returns a DataFrame.
    """
    # 1. Verify that the path actually exists
    if not os.path.exists(path):
        print(f"--- ERROR ---")
        print(f"The specified path does not exist. Please check for typos.")
        print(f"Path provided: {path}")
        return pd.DataFrame(columns=["code", "create_date"])

    data_list = []

    print("--- Starting to process files... ---")

    # 2. Loop through every item in the directory
    for filename in os.listdir(path):
        # 3. Only process files that end with .json
        if filename.endswith(".json"):
            file_path = os.path.join(path, filename)
            
            try:
                # Get code from the first 10 characters of the filename.
                code = filename[:10]

                # Get the date from the file's metadata (last modified time).
                timestamp = os.path.getmtime(file_path)
                modification_date = datetime.fromtimestamp(timestamp)

                # 4. Add the extracted data to our list
                data_list.append({
                    "code": code,
                    "create_date": modification_date
                })

            except Exception as e:
                print(f"An unexpected error occurred with file '{filename}': {e}")
    
    if not data_list:
        print("--- No JSON files were found or processed. ---")
        return pd.DataFrame(columns=["code", "create_date"])

    # 5. Create the pandas DataFrame from the collected data
    print("\n--- File processing complete. Creating DataFrame. ---")
    json_files = pd.DataFrame(data_list)
    
    # 6. Ensure the date column is in the correct format
    json_files['create_date'] = pd.to_datetime(json_files['create_date'])

    # --- Remove Duplicates ---
    print(f"Found {len(json_files)} total entries. Checking for duplicates...")
    
    # 7. Sort by date in descending order (newest first)
    json_files = json_files.sort_values(by='create_date', ascending=False)
    
    # 8. Drop duplicates based on the 'code' column
    initial_count = len(json_files)
    json_files = json_files.drop_duplicates(subset=['code'], keep='first')
    final_count = len(json_files)
    
    print(f"Removed {initial_count - final_count} duplicate(s). Final count: {final_count}.")

    # 9. Reset the DataFrame index for a clean look
    json_files = json_files.reset_index(drop=True)
    
    return json_files

def save_to_sqlite(df, db_path, table_name):
    """Saves a DataFrame to an SQLite database table."""
    print(f"\n--- Connecting to database: {db_path} ---")
    try:
        # Establish a connection to the SQLite database
        conn = sqlite3.connect(db_path)
        print("Connection successful.")

        # Save the DataFrame to the specified table.
        # if_exists='replace': Drops the table first if it exists, then creates a new one.
        # This is useful for re-running the script to get a fresh table.
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        
        print(f"Successfully saved {len(df)} rows to table '{table_name}'.")

    except sqlite3.Error as e:
        print(f"--- Database Error ---")
        print(f"An error occurred: {e}")
    finally:
        # Make sure to close the connection
        if 'conn' in locals() and conn:
            conn.close()
            print("Database connection closed.")

# --- Execution ---
# Define paths
directory_path = r"/home/developer/Output_jason_api"
database_path = r"/home/developer/asset_capture_app_dev/data/QR_codes.db"

# 1. Process files and create the DataFrame
json_files = process_files_by_name_and_metadata(directory_path)

# 2. Display the DataFrame in the console
print("\n--- Resulting DataFrame (Duplicates Removed) ---")
print(json_files)
print("\n--- DataFrame Info ---")
json_files.info()

# 3. Save the DataFrame to the SQLite database
if not json_files.empty:
    save_to_sqlite(json_files, database_path, "json_files")

