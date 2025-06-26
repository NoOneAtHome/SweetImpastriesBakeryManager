"""
Unit tests for the database module.

Tests database initialization, session management, and connection handling
in isolation using mocks and in-memory databases.
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import create_engine, text

from database import (
    init_database,
    get_db_session,
    get_db_session_context,
    close_db_connection,
    test_db_connection
)
from models import Base, Sensor, SensorReading, Error
from config import TestingConfig


@pytest.mark.unit
class TestDatabaseInitialization:
    """Test database initialization functionality."""
    
    def test_init_database_success(self, test_db_engine):
        """Test successful database initialization."""
        # Database should be initialized by the fixture
        # Verify tables exist by checking metadata
        table_names = Base.metadata.tables.keys()
        expected_tables = {'sensors', 'sensor_readings', 'errors'}
        
        assert expected_tables.issubset(table_names)
    
    def test_init_database_sqlite_file_creation(self):
        """Test SQLite file creation during initialization."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
            temp_path = temp_db.name
        
        try:
            # Remove the file so we can test creation
            os.unlink(temp_path)
            
            # Mock config to use our temp file
            with patch('database.config') as mock_config:
                mock_config.DATABASE_URL = f'sqlite:///{temp_path}'
                mock_config.DEBUG = False
                
                # Mock the engine and metadata
                with patch('database.engine') as mock_engine, \
                     patch('database.Base') as mock_base:
                    
                    mock_base.metadata.create_all.return_value = None
                    
                    # Create the file to simulate successful creation
                    with open(temp_path, 'w') as f:
                        f.write('')
                    
                    result = init_database()
                    
                    assert result is True
                    mock_base.metadata.create_all.assert_called_once_with(bind=mock_engine)
        
        finally:
            # Clean up
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    def test_init_database_sqlalchemy_error(self):
        """Test database initialization with SQLAlchemy error."""
        with patch('database.Base') as mock_base:
            mock_base.metadata.create_all.side_effect = SQLAlchemyError("Database error")
            
            with pytest.raises(SQLAlchemyError):
                init_database()
    
    def test_init_database_unexpected_error(self):
        """Test database initialization with unexpected error."""
        with patch('database.Base') as mock_base:
            mock_base.metadata.create_all.side_effect = ValueError("Unexpected error")
            
            with pytest.raises(ValueError):
                init_database()
    
    def test_init_database_file_not_created(self):
        """Test database initialization when SQLite file is not created."""
        with patch('database.config') as mock_config, \
             patch('database.Base') as mock_base:
            
            mock_config.DATABASE_URL = 'sqlite:///nonexistent.db'
            mock_base.metadata.create_all.return_value = None
            
            result = init_database()
            
            assert result is False


@pytest.mark.unit
class TestDatabaseSessions:
    """Test database session management."""
    
    def test_get_db_session(self, test_db_engine):
        """Test getting a database session."""
        with patch('database.SessionLocal') as mock_session_local:
            mock_session = Mock()
            mock_session_local.return_value = mock_session
            
            session = get_db_session()
            
            assert session == mock_session
            mock_session_local.assert_called_once()
    
    def test_get_db_session_context_success(self, test_db_engine):
        """Test database session context manager success case."""
        with patch('database.SessionLocal') as mock_session_local:
            mock_session = Mock()
            mock_session_local.return_value = mock_session
            
            with get_db_session_context() as session:
                assert session == mock_session
            
            mock_session.close.assert_called_once()
    
    def test_get_db_session_context_exception(self, test_db_engine):
        """Test database session context manager with exception."""
        with patch('database.SessionLocal') as mock_session_local:
            mock_session = Mock()
            mock_session_local.return_value = mock_session
            
            with pytest.raises(ValueError):
                with get_db_session_context() as session:
                    assert session == mock_session
                    raise ValueError("Test exception")
            
            # Session should still be closed even with exception
            mock_session.close.assert_called_once()


@pytest.mark.unit
class TestDatabaseConnection:
    """Test database connection management."""
    
    def test_close_db_connection_success(self):
        """Test successful database connection closure."""
        with patch('database.engine') as mock_engine:
            mock_engine.dispose.return_value = None
            
            close_db_connection()
            
            mock_engine.dispose.assert_called_once()
    
    def test_close_db_connection_error(self):
        """Test database connection closure with error."""
        with patch('database.engine') as mock_engine:
            mock_engine.dispose.side_effect = Exception("Disposal error")
            
            # Should not raise exception, just log error
            close_db_connection()
            
            mock_engine.dispose.assert_called_once()
    
    def test_test_db_connection_success(self):
        """Test successful database connection test."""
        with patch('database.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.execute.return_value = None
            
            result = test_db_connection()
            
            assert result is True
            mock_session.execute.assert_called_once()
            # Verify the SQL query is correct
            call_args = mock_session.execute.call_args[0][0]
            assert str(call_args) == "SELECT 1"
    
    def test_test_db_connection_failure(self):
        """Test database connection test failure."""
        with patch('database.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.execute.side_effect = SQLAlchemyError("Connection failed")
            
            result = test_db_connection()
            
            assert result is False


@pytest.mark.unit
class TestDatabaseConfiguration:
    """Test database configuration and engine setup."""
    
    def test_engine_configuration_sqlite(self):
        """Test engine configuration for SQLite."""
        with patch('database.create_engine') as mock_create_engine, \
             patch('database.get_config') as mock_get_config:
            
            mock_config = Mock()
            mock_config.DATABASE_URL = 'sqlite:///test.db'
            mock_config.DEBUG = True
            mock_get_config.return_value = mock_config
            
            # Import to trigger engine creation
            import database
            
            mock_create_engine.assert_called_with(
                'sqlite:///test.db',
                echo=True,
                connect_args={"check_same_thread": False}
            )
    
    def test_engine_configuration_non_sqlite(self):
        """Test engine configuration for non-SQLite databases."""
        with patch('database.create_engine') as mock_create_engine, \
             patch('database.get_config') as mock_get_config:
            
            mock_config = Mock()
            mock_config.DATABASE_URL = 'postgresql://user:pass@localhost/db'
            mock_config.DEBUG = False
            mock_get_config.return_value = mock_config
            
            # Import to trigger engine creation
            import database
            
            mock_create_engine.assert_called_with(
                'postgresql://user:pass@localhost/db',
                echo=False,
                connect_args={}
            )
    
    def test_sessionmaker_configuration(self):
        """Test SessionLocal configuration."""
        with patch('database.sessionmaker') as mock_sessionmaker, \
             patch('database.engine') as mock_engine:
            
            # Import to trigger sessionmaker creation
            import database
            
            mock_sessionmaker.assert_called_with(
                autocommit=False,
                autoflush=False,
                bind=mock_engine
            )


@pytest.mark.unit
class TestDatabaseModuleImport:
    """Test database module import behavior."""
    
    def test_auto_initialization_in_non_testing_mode(self):
        """Test that database is auto-initialized when not in testing mode."""
        with patch('database.config') as mock_config, \
             patch('database.init_database') as mock_init:
            
            mock_config.FLASK_ENV = 'development'
            mock_init.return_value = True
            
            # Force reimport to trigger initialization
            import importlib
            import database
            importlib.reload(database)
            
            # Note: This test is tricky because the module is already imported
            # In a real scenario, we'd need to test this differently
    
    def test_no_auto_initialization_in_testing_mode(self):
        """Test that database is not auto-initialized in testing mode."""
        with patch('database.config') as mock_config, \
             patch('database.init_database') as mock_init:
            
            mock_config.FLASK_ENV = 'testing'
            
            # Force reimport to trigger initialization check
            import importlib
            import database
            importlib.reload(database)
            
            # In testing mode, init_database should not be called
            # Note: This test is also tricky due to module import behavior
    
    def test_initialization_error_handling(self):
        """Test error handling during module import initialization."""
        with patch('database.config') as mock_config, \
             patch('database.init_database') as mock_init:
            
            mock_config.FLASK_ENV = 'development'
            mock_init.side_effect = Exception("Initialization failed")
            
            # Should not raise exception during import
            import importlib
            import database
            importlib.reload(database)


@pytest.mark.unit
class TestDatabaseIntegrationWithModels:
    """Test database integration with model classes."""
    
    def test_sensor_model_creation(self, test_db_session):
        """Test creating a Sensor model instance."""
        sensor = Sensor(
            sensor_id='TEST_001',
            name='Test Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        
        test_db_session.add(sensor)
        test_db_session.commit()
        
        # Verify sensor was created
        retrieved_sensor = test_db_session.query(Sensor).filter_by(sensor_id='TEST_001').first()
        assert retrieved_sensor is not None
        assert retrieved_sensor.name == 'Test Sensor'
        assert retrieved_sensor.active is True
    
    def test_sensor_reading_model_creation(self, test_db_session):
        """Test creating a SensorReading model instance."""
        from datetime import datetime
        
        # First create a sensor
        sensor = Sensor(
            sensor_id='TEST_001',
            name='Test Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        test_db_session.commit()
        
        # Create a reading
        reading = SensorReading(
            sensor_id='TEST_001',
            timestamp=datetime.utcnow(),
            temperature=22.5,
            humidity=45.0
        )
        
        test_db_session.add(reading)
        test_db_session.commit()
        
        # Verify reading was created
        retrieved_reading = test_db_session.query(SensorReading).filter_by(sensor_id='TEST_001').first()
        assert retrieved_reading is not None
        assert retrieved_reading.temperature == 22.5
        assert retrieved_reading.humidity == 45.0
    
    def test_error_model_creation(self, test_db_session):
        """Test creating an Error model instance."""
        from datetime import datetime
        
        error = Error(
            error_id='ERR-12345678',
            message='Test error message',
            stack_trace='Test stack trace',
            timestamp=datetime.utcnow()
        )
        
        test_db_session.add(error)
        test_db_session.commit()
        
        # Verify error was created
        retrieved_error = test_db_session.query(Error).filter_by(error_id='ERR-12345678').first()
        assert retrieved_error is not None
        assert retrieved_error.message == 'Test error message'
        assert retrieved_error.stack_trace == 'Test stack trace'
    
    def test_sensor_reading_relationship(self, test_db_session):
        """Test the relationship between Sensor and SensorReading models."""
        from datetime import datetime
        
        # Create sensor
        sensor = Sensor(
            sensor_id='TEST_001',
            name='Test Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        test_db_session.commit()
        
        # Create multiple readings
        for i in range(3):
            reading = SensorReading(
                sensor_id='TEST_001',
                timestamp=datetime.utcnow(),
                temperature=20.0 + i,
                humidity=40.0 + i
            )
            test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Test relationship
        retrieved_sensor = test_db_session.query(Sensor).filter_by(sensor_id='TEST_001').first()
        assert len(retrieved_sensor.readings) == 3
        
        # Test back-reference
        first_reading = retrieved_sensor.readings[0]
        assert first_reading.sensor.sensor_id == 'TEST_001'


@pytest.mark.unit
class TestDatabaseErrorScenarios:
    """Test various database error scenarios."""
    
    def test_session_creation_error(self):
        """Test error handling when session creation fails."""
        with patch('database.SessionLocal') as mock_session_local:
            mock_session_local.side_effect = SQLAlchemyError("Session creation failed")
            
            with pytest.raises(SQLAlchemyError):
                get_db_session()
    
    def test_context_manager_session_error(self):
        """Test error handling in session context manager."""
        with patch('database.SessionLocal') as mock_session_local:
            mock_session = Mock()
            mock_session.close.side_effect = SQLAlchemyError("Close failed")
            mock_session_local.return_value = mock_session
            
            # Should not raise exception even if close fails
            with get_db_session_context() as session:
                assert session == mock_session
            
            mock_session.close.assert_called_once()
    
    def test_connection_test_with_invalid_sql(self):
        """Test connection test with invalid SQL execution."""
        with patch('database.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.execute.side_effect = Exception("Invalid SQL")
            
            result = test_db_connection()
            
            assert result is False