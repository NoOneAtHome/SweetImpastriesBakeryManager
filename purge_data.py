#!/usr/bin/env python3
"""
Standalone script to purge sensor data from the database.

This script operates independently of Flask and any running applications,
providing a clean interface for data purging operations.
"""

import os
import sys
import sqlite3
from pathlib import Path

def get_database_path():
    """Get the path to the database file."""
    # Get the script directory and find the database
    script_dir = Path(__file__).parent
    db_path = script_dir / "db" / "sensor_dashboard.db"
    
    if not db_path.exists():
        print(f"ERROR: Database file not found at {db_path}")
        print("Make sure you're running this script from the project root directory.")
        sys.exit(1)
    
    return str(db_path)

def get_sensor_reading_count(db_path):
    """Get the current count of sensor readings."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sensor_readings")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except sqlite3.Error as e:
        print(f"ERROR: Failed to query database: {e}")
        sys.exit(1)

def purge_sensor_data(db_path):
    """Purge all sensor data from the database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Delete all sensor readings
        cursor.execute("DELETE FROM sensor_readings")
        deleted_count = cursor.rowcount
        
        # Commit the changes
        conn.commit()
        conn.close()
        
        return deleted_count
    except sqlite3.Error as e:
        print(f"ERROR: Failed to purge data: {e}")
        sys.exit(1)

def main():
    """Main function to handle the purge operation."""
    print("=" * 60)
    print("BAKERY SENSORS - DATA PURGE UTILITY")
    print("=" * 60)
    
    # Get database path
    db_path = get_database_path()
    print(f"Database: {db_path}")
    
    # Get current data count
    current_count = get_sensor_reading_count(db_path)
    print(f"Current sensor readings: {current_count}")
    
    if current_count == 0:
        print("\nNo sensor data to purge.")
        return
    
    # Confirmation prompt
    print(f"\n⚠️  WARNING: This will permanently delete ALL {current_count} sensor readings!")
    print("This action cannot be undone.")
    
    while True:
        response = input("\nType 'yes' to confirm deletion, or 'no' to cancel: ").strip().lower()
        
        if response == 'yes':
            print("\nPurging sensor data...")
            deleted_count = purge_sensor_data(db_path)
            print(f"✅ Successfully deleted {deleted_count} sensor readings.")
            break
        elif response == 'no':
            print("❌ Operation cancelled.")
            break
        else:
            print("Please type 'yes' or 'no'.")

if __name__ == "__main__":
    main()