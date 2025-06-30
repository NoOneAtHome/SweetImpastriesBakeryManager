#!/usr/bin/env python3
"""
Database migration script to add the 'category' column to the sensors table.

This script adds a new 'category' column to the existing sensors table to support
categorized sensor charts (freezer, refrigerator, ambient).
"""

import sys
import os
from sqlalchemy import text
from database import get_db_session_context
from config import get_config

def add_category_column():
    """Add the category column to the sensors table."""
    try:
        print("Starting database migration: Adding 'category' column to sensors table...")
        
        with get_db_session_context() as session:
            # Check if the column already exists
            result = session.execute(text("PRAGMA table_info(sensors)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'category' in columns:
                print("✓ Category column already exists in sensors table.")
                return True
            
            # Add the category column
            print("Adding 'category' column to sensors table...")
            session.execute(text("ALTER TABLE sensors ADD COLUMN category TEXT"))
            session.commit()
            
            print("✓ Successfully added 'category' column to sensors table.")
            
            # Optionally set some default categories based on sensor names
            print("Setting default categories based on sensor names...")
            
            # Get all sensors
            result = session.execute(text("SELECT sensor_id, name FROM sensors"))
            sensors = result.fetchall()
            
            updated_count = 0
            for sensor_id, name in sensors:
                category = None
                name_lower = name.lower()
                
                # Simple heuristic to categorize sensors based on name
                if any(keyword in name_lower for keyword in ['freezer', 'freeze', 'frozen']):
                    category = 'freezer'
                elif any(keyword in name_lower for keyword in ['fridge', 'refrigerator', 'refrig', 'cooler']):
                    category = 'refrigerator'
                elif any(keyword in name_lower for keyword in ['ambient', 'room', 'office', 'kitchen', 'dining']):
                    category = 'ambient'
                
                if category:
                    session.execute(
                        text("UPDATE sensors SET category = :category WHERE sensor_id = :sensor_id"),
                        {"category": category, "sensor_id": sensor_id}
                    )
                    updated_count += 1
                    print(f"  - Set sensor '{name}' ({sensor_id}) to category '{category}'")
            
            session.commit()
            
            if updated_count > 0:
                print(f"✓ Updated {updated_count} sensors with default categories.")
            else:
                print("ℹ No sensors were automatically categorized. You can set categories manually through the manager interface.")
            
            return True
            
    except Exception as e:
        print(f"✗ Error during migration: {str(e)}")
        return False

def main():
    """Main migration function."""
    print("=" * 60)
    print("Database Migration: Add Category Column to Sensors Table")
    print("=" * 60)
    
    # Load configuration
    config = get_config()
    print(f"Using database: {config.DATABASE_URL}")
    
    # Run migration
    success = add_category_column()
    
    if success:
        print("\n✓ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Restart the Flask application")
        print("2. Use the manager interface to assign categories to sensors")
        print("3. Categories available: 'freezer', 'refrigerator', 'ambient'")
    else:
        print("\n✗ Migration failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()