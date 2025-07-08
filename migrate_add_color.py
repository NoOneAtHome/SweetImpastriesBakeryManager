#!/usr/bin/env python3
"""
Database migration script to add the 'color' column to the sensors table.

This script adds a new 'color' column to the existing sensors table to support
color-coded sensor visualization.
"""

import sys
import os
from sqlalchemy import text
from database import get_db_session_context
from config import get_config

def add_color_column():
    """Add the color column to the sensors table."""
    try:
        print("Starting database migration: Adding 'color' column to sensors table...")
        
        with get_db_session_context() as session:
            # Check if the column already exists
            result = session.execute(text("PRAGMA table_info(sensors)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'color' in columns:
                print("✓ Color column already exists in sensors table.")
                return True
            
            # Add the color column
            print("Adding 'color' column to sensors table...")
            session.execute(text("ALTER TABLE sensors ADD COLUMN color TEXT"))
            session.commit()
            
            print("✓ Successfully added 'color' column to sensors table.")
            
            return True
            
    except Exception as e:
        print(f"✗ Error during migration: {str(e)}")
        return False

def main():
    """Main migration function."""
    print("=" * 60)
    print("Database Migration: Add Color Column to Sensors Table")
    print("=" * 60)
    
    # Load configuration
    config = get_config()
    print(f"Using database: {config.DATABASE_URL}")
    
    # Run migration
    success = add_color_column()
    
    if success:
        print("\n✓ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Restart the Flask application")
        print("2. Use the manager interface to assign colors to sensors")
        print("3. Colors can be any valid CSS color value (e.g., '#FF0000', 'red', 'rgb(255,0,0)')")
    else:
        print("\n✗ Migration failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()