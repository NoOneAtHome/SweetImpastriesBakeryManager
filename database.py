"""
Database initialization and ORM setup for the Bakery Sensors application.

This module manages database connections, sessions, and initialization.
It provides functions to initialize the SQLite database and get SQLAlchemy sessions.
"""

import os
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from config import get_config
from models import Base

# Get configuration
config = get_config()

# Create SQLAlchemy engine using DATABASE_URL from config
engine = create_engine(
    config.DATABASE_URL,
    echo=config.DEBUG,  # Enable SQL logging in debug mode
    connect_args={"check_same_thread": False} if config.DATABASE_URL.startswith('sqlite') else {}
)

# Create sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_database():
    """
    Initialize the SQLite database.
    
    Creates the database file and all defined tables if they do not already exist,
    using the Base from models.py. Also runs database migrations to ensure
    schema is up to date.
    
    Returns:
        bool: True if initialization was successful, False otherwise
        
    Raises:
        SQLAlchemyError: If there's an error during database initialization
    """
    try:
        # Create all tables defined in the models
        Base.metadata.create_all(bind=engine)
        
        # If using SQLite, ensure the database file was created
        if config.DATABASE_URL.startswith('sqlite:///'):
            db_path = config.DATABASE_URL.replace('sqlite:///', '')
            if os.path.exists(db_path):
                print(f"Database initialized successfully at: {db_path}")
            else:
                print(f"Warning: Database file not found at expected path: {db_path}")
                return False
        else:
            print("Database tables initialized successfully")
        
        # Run database migrations to ensure schema is up to date
        migration_success = migrate_database()
        if not migration_success:
            print("Warning: Database migrations failed")
            return False
            
        return True
        
    except SQLAlchemyError as e:
        print(f"Error initializing database: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error during database initialization: {e}")
        raise


def migrate_database():
    """
    Perform database migrations to ensure schema is up to date.
    
    This function checks for missing columns and adds them if needed.
    Currently handles:
    - Adding battery_voltage column to sensor_readings table if missing
    - Adding level column to errors table if missing
    
    Returns:
        bool: True if migrations completed successfully, False otherwise
    """
    try:
        with get_db_session_context() as session:
            migrations_performed = []
            
            # Check if battery_voltage column exists in sensor_readings table
            try:
                session.execute(text("SELECT battery_voltage FROM sensor_readings LIMIT 1"))
                print("Database schema check: battery_voltage column exists")
            except Exception:
                # Column doesn't exist, need to add it
                print("Adding missing battery_voltage column to sensor_readings table...")
                session.execute(text("ALTER TABLE sensor_readings ADD COLUMN battery_voltage FLOAT"))
                migrations_performed.append("Added battery_voltage column to sensor_readings")
            
            # Check if level column exists in errors table
            try:
                session.execute(text("SELECT level FROM errors LIMIT 1"))
                print("Database schema check: level column exists in errors table")
            except Exception:
                # Column doesn't exist, need to add it
                print("Adding missing level column to errors table...")
                session.execute(text("ALTER TABLE errors ADD COLUMN level STRING DEFAULT 'ERROR'"))
                migrations_performed.append("Added level column to errors")
            
            # Check if source column exists in errors table
            try:
                session.execute(text("SELECT source FROM errors LIMIT 1"))
                print("Database schema check: source column exists in errors table")
            except Exception:
                # Column doesn't exist, need to add it
                print("Adding missing source column to errors table...")
                session.execute(text("ALTER TABLE errors ADD COLUMN source STRING DEFAULT 'application'"))
                migrations_performed.append("Added source column to errors")
            
            # Commit all migrations
            if migrations_performed:
                session.commit()
                print(f"Successfully completed migrations: {', '.join(migrations_performed)}")
            else:
                print("Database schema is up to date - no migrations needed")
            
            return True
                
    except SQLAlchemyError as e:
        print(f"Error during database migration: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error during database migration: {e}")
        return False


def get_db_session() -> Session:
    """
    Get a new SQLAlchemy session.
    
    Returns:
        Session: A new SQLAlchemy session instance
        
    Note:
        The caller is responsible for closing the session when done.
        Use in a try/finally block or context manager for proper cleanup.
    """
    return SessionLocal()


@contextmanager
def get_db_session_context():
    """
    Get a database session as a context manager.
    
    Yields:
        Session: A SQLAlchemy session that will be automatically closed
        
    Example:
        with get_db_session_context() as session:
            # Use session here
            sensors = session.query(Sensor).all()
            # Session is automatically closed when exiting the context
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def close_db_connection():
    """
    Close the database engine and all connections.
    
    This should be called when shutting down the application
    to ensure proper cleanup of database resources.
    """
    try:
        engine.dispose()
        print("Database connections closed successfully")
    except Exception as e:
        print(f"Error closing database connections: {e}")


def test_db_connection():
    """
    Test the database connection.
    
    Returns:
        bool: True if connection is successful, False otherwise
    """
    try:
        with get_db_session_context() as session:
            # Try to execute a simple query
            from sqlalchemy import text
            session.execute(text("SELECT 1"))
            return True
    except Exception as e:
        print(f"Database connection test failed: {e}")
        return False


# Initialize database on module import if not in testing mode
if config.FLASK_ENV != 'testing':
    try:
        init_database()
    except Exception as e:
        print(f"Failed to initialize database on module import: {e}")