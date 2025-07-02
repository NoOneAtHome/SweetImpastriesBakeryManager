import click
import os
import sys

# Add the parent directory to the Python path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask.cli import with_appcontext
from database import get_db_session_context
from models import SensorReading
from config import get_config

@click.command('purge-data')
@click.option('--force', '-f', is_flag=True, help='Bypass confirmation prompt.')
def purge_sensor_data_command(force):
    """Purges all sensor data from the database."""
    
    # Import here to avoid circular imports
    from app import create_cli_app
    
    # Create CLI-specific app without background services
    app = create_cli_app()
    
    with app.app_context():
        # Add diagnostic logging
        config = get_config()
        click.echo(f"DEBUG: Using database URL: {config.DATABASE_URL}")
    
        # Check if database file exists for SQLite
        if config.DATABASE_URL.startswith('sqlite:///'):
            db_path = config.DATABASE_URL.replace('sqlite:///', '')
            abs_db_path = os.path.abspath(db_path)
            click.echo(f"DEBUG: Database file path: {abs_db_path}")
            click.echo(f"DEBUG: Database file exists: {os.path.exists(abs_db_path)}")
            if os.path.exists(abs_db_path):
                file_size = os.path.getsize(abs_db_path)
                click.echo(f"DEBUG: Database file size: {file_size} bytes")
        
        # Count existing records before deletion
        try:
            with get_db_session_context() as session:
                count_before = session.query(SensorReading).count()
                click.echo(f"DEBUG: Found {count_before} sensor readings before deletion")
        except Exception as e:
            click.echo(f"ERROR: Failed to count existing records: {e}", err=True)
            return
        
        click.echo("WARNING: This will delete ALL sensor data from the database.")
        
        if not force:
            click.echo("You must type 'yes' to confirm the deletion.")
            click.echo("NOTE: Background services are disabled for CLI commands.")
            try:
                # Use a more robust input method that can handle background noise
                import sys
                sys.stdout.flush()  # Ensure prompt is displayed
                confirmation = input("Are you sure you want to proceed? Type 'yes' to confirm: ").strip()
                click.echo(f"DEBUG: User input received: '{confirmation}'")
            except (EOFError, KeyboardInterrupt):
                click.echo("Operation cancelled by user.")
                return
            except Exception as e:
                click.echo(f"ERROR: Failed to get user input: {e}", err=True)
                click.echo("Use --force flag to bypass confirmation prompt.")
                return
        else:
            confirmation = 'yes'
            click.echo("Force flag detected. Bypassing confirmation.")

        if confirmation.lower() == 'yes':
            try:
                with get_db_session_context() as session:
                    click.echo("DEBUG: Starting deletion process...")
                    
                    # Count records again inside the transaction
                    count_in_transaction = session.query(SensorReading).count()
                    click.echo(f"DEBUG: Found {count_in_transaction} sensor readings in transaction")
                    
                    # Perform the deletion
                    num_deleted = session.query(SensorReading).delete()
                    click.echo(f"DEBUG: SQLAlchemy reports {num_deleted} records deleted")
                    
                    # Verify deletion worked
                    count_after_delete = session.query(SensorReading).count()
                    click.echo(f"DEBUG: Found {count_after_delete} sensor readings after delete (before commit)")
                    
                    # The context manager will commit automatically when exiting
                    click.echo("DEBUG: Exiting context manager (will auto-commit)...")
                    
                # Verify final state after commit
                with get_db_session_context() as session:
                    final_count = session.query(SensorReading).count()
                    click.echo(f"DEBUG: Final count after commit: {final_count} sensor readings")
                    
                click.echo(f"Successfully deleted {num_deleted} sensor readings.")
                
            except Exception as e:
                click.echo(f"An error occurred while purging data: {e}", err=True)
                import traceback
                click.echo(f"DEBUG: Full traceback: {traceback.format_exc()}", err=True)
        else:
            click.echo("Operation cancelled.")

def purge_sensor_data_standalone(force=False):
    """Standalone function to purge all sensor data from the database."""
    
    # Import here to avoid circular imports
    from app import create_cli_app
    
    # Create CLI-specific app without background services
    app = create_cli_app()
    
    with app.app_context():
        # Add diagnostic logging
        config = get_config()
        print(f"DEBUG: Using database URL: {config.DATABASE_URL}")
    
        # Check if database file exists for SQLite
        if config.DATABASE_URL.startswith('sqlite:///'):
            db_path = config.DATABASE_URL.replace('sqlite:///', '')
            abs_db_path = os.path.abspath(db_path)
            print(f"DEBUG: Database file path: {abs_db_path}")
            print(f"DEBUG: Database file exists: {os.path.exists(abs_db_path)}")
            if os.path.exists(abs_db_path):
                file_size = os.path.getsize(abs_db_path)
                print(f"DEBUG: Database file size: {file_size} bytes")
        
        # Count existing records before deletion
        try:
            with get_db_session_context() as session:
                count_before = session.query(SensorReading).count()
                print(f"DEBUG: Found {count_before} sensor readings before deletion")
        except Exception as e:
            print(f"ERROR: Failed to count existing records: {e}")
            return
        
        if count_before == 0:
            print("No sensor data found to purge.")
            return
        
        print("WARNING: This will delete ALL sensor data from the database.")
        
        if not force:
            print("You must type 'yes' to confirm the deletion.")
            print("NOTE: Background services are disabled for CLI commands.")
            try:
                # Use a more robust input method that can handle background noise
                import sys
                sys.stdout.flush()  # Ensure prompt is displayed
                confirmation = input("Are you sure you want to proceed? Type 'yes' to confirm: ").strip()
                print(f"DEBUG: User input received: '{confirmation}'")
            except (EOFError, KeyboardInterrupt):
                print("Operation cancelled by user.")
                return
            except Exception as e:
                print(f"ERROR: Failed to get user input: {e}")
                print("Use --force flag to bypass confirmation prompt.")
                return
        else:
            confirmation = 'yes'
            print("Force flag detected. Bypassing confirmation.")

        if confirmation.lower() == 'yes':
            try:
                with get_db_session_context() as session:
                    print("DEBUG: Starting deletion process...")
                    
                    # Count records again inside the transaction
                    count_in_transaction = session.query(SensorReading).count()
                    print(f"DEBUG: Found {count_in_transaction} sensor readings in transaction")
                    
                    # Perform the deletion
                    num_deleted = session.query(SensorReading).delete()
                    print(f"DEBUG: SQLAlchemy reports {num_deleted} records deleted")
                    
                    # Verify deletion worked
                    count_after_delete = session.query(SensorReading).count()
                    print(f"DEBUG: Found {count_after_delete} sensor readings after delete (before commit)")
                    
                    # The context manager will commit automatically when exiting
                    print("DEBUG: Exiting context manager (will auto-commit)...")
                    
                # Verify final state after commit
                with get_db_session_context() as session:
                    final_count = session.query(SensorReading).count()
                    print(f"DEBUG: Final count after commit: {final_count} sensor readings")
                    
                print(f"Successfully deleted {num_deleted} sensor readings.")
                
            except Exception as e:
                print(f"An error occurred while purging data: {e}")
                import traceback
                print(f"DEBUG: Full traceback: {traceback.format_exc()}")
        else:
            print("Operation cancelled.")

if __name__ == '__main__':
    # This block allows the script to be run directly as a standalone script
    # without the Flask CLI, which avoids background service interference
    import sys
    
    print("DEBUG: Starting standalone script execution")
    
    # Parse command line arguments
    force = '--force' in sys.argv or '-f' in sys.argv
    print(f"DEBUG: Force mode: {force}")
    
    # Call the standalone function (not the Click command)
    print("DEBUG: Calling purge_sensor_data_standalone...")
    purge_sensor_data_standalone(force)
    print("DEBUG: Script execution completed")