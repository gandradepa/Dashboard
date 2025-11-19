#!/usr/bin/env python3
"""
Script to add test assets to the new_device table for testing Edit Asset functionality
"""

import sqlite3
from datetime import datetime

DB_PATH = '/home/developer/Dashboard/QR_codes.db'

# Test assets to add
test_assets = [
    {
        'Work Order': 'WO-001',
        'Asset Tag': 'TEST-001',
        'Asset Group': 'Addressable Modules',
        'Description': '',  # Will be auto-populated from lookup
        'Property': 'Main Campus',
        'Space': 'Building A - Floor 1',
        'Space Details': 'Room 101',
        'Attribute Set': '',  # Will be auto-populated from lookup
        'Device Address': '',  # Will be auto-populated from lookup
        'Device Type': '',  # Will be auto-populated from lookup
        'UN Account Number': '',
        'Planon Code': '',
        'Creation Date': datetime.now().strftime('%m/%d/%Y'),
        'Status': '0',
        'Workflow': 'Asset Management'
    },
    {
        'Work Order': 'WO-002',
        'Asset Tag': 'TEST-002',
        'Asset Group': 'Beam Detectors',
        'Description': '',
        'Property': 'Main Campus',
        'Space': 'Building A - Floor 2',
        'Space Details': 'Room 201',
        'Attribute Set': '',
        'Device Address': '',
        'Device Type': '',
        'UN Account Number': '',
        'Planon Code': '',
        'Creation Date': datetime.now().strftime('%m/%d/%Y'),
        'Status': '0',
        'Workflow': 'Asset Management'
    },
    {
        'Work Order': 'WO-003',
        'Asset Tag': 'TEST-003',
        'Asset Group': 'Bells',
        'Description': '',
        'Property': 'Main Campus',
        'Space': 'Building B - Floor 1',
        'Space Details': 'Hallway',
        'Attribute Set': '',
        'Device Address': '',
        'Device Type': '',
        'UN Account Number': '',
        'Planon Code': '',
        'Creation Date': datetime.now().strftime('%m/%d/%Y'),
        'Status': '0',
        'Workflow': 'Asset Management'
    }
]

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get column names from table
    cursor.execute("PRAGMA table_info(new_device)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Database columns: {columns}")
    
    for asset in test_assets:
        # Build the insert query with only the columns that exist
        insert_cols = []
        insert_vals = []
        for key, value in asset.items():
            if key in columns:
                insert_cols.append(f'"{key}"')
                insert_vals.append(value)
        
        placeholders = ','.join(['?' for _ in insert_vals])
        query = f"INSERT INTO new_device ({','.join(insert_cols)}) VALUES ({placeholders})"
        
        print(f"Inserting: {asset['Asset Tag']}")
        cursor.execute(query, insert_vals)
    
    conn.commit()
    
    # Verify insertion
    cursor.execute("SELECT COUNT(*) FROM new_device")
    count = cursor.fetchone()[0]
    print(f"\nSuccess! Total assets in database: {count}")
    
    # Show what was inserted
    cursor.execute("SELECT 'Asset Tag', 'Asset Group' FROM new_device ORDER BY 'Asset Tag'")
    print("\nInserted assets:")
    for row in cursor.execute("SELECT \"Asset Tag\", \"Asset Group\" FROM new_device ORDER BY \"Asset Tag\""):
        print(f"  - {row[0]}: {row[1]}")
    
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
