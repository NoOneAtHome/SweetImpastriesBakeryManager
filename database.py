"""
Database initialization and ORM setup for the Bakery Sensors application.

This module manages database connections, sessions, and initialization.
It provides functions to initialize the SQLite database and get SQLAlchemy sessions.
"""

import os
from contextlib import contextmanager
from sqlalchemy import create_engine
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
    using the Base from models.py.
    
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
            
        return True
        
    except SQLAlchemyError as e:
        print(f"Error initializing database: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error during database initialization: {e}")
        raise


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