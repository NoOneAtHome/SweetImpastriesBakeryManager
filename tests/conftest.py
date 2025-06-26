"""
Test configuration and fixtures for the BakerySensors test suite.

This module provides pytest fixtures for database setup, API mocking,
and other common test utilities.
"""

import os
import pytest
import tempfile
import logging
from datetime import datetime, timedelta, UTC
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Set testing environment before importing application modules
os.environ['FLASK_ENV'] = 'testing'

from config import TestingConfig
from database import Base
from models import Sensor, SensorReading, Error
from app import create_app
from sensorpush_api import SensorPushAPI
from polling_service import PollingService


@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration."""
    # Ensure dummy values are set directly on the TestingConfig class
    TestingConfig.SENSORPUSH_USERNAME = 'test_user'
    TestingConfig.SENSORPUSH_PASSWORD = 'test_password'
    return TestingConfig


@pytest.fixture(scope="function")
def test_db_engine(test_config):
    """Create a test database engine with in-memory SQLite."""
    engine = create_engine(
        test_config.DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False}
    )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    yield engine
    
    # Clean up
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db_session(test_db_engine):
    """Create a test database session."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)
    session = SessionLocal()
    
    yield session
    
    session.close()


@pytest.fixture(scope="function")
def sample_sensor_data():
    """Provide sample sensor data for testing."""
    return {
        'sensor_id': 'TEST_SENSOR_001',
        'name': 'Test Sensor 1',
        'active': True,
        'min_temp': 0.0,
        'max_temp': 50.0,
        'min_humidity': 0.0,
        'max_humidity': 100.0
    }


@pytest.fixture(scope="function")
def sample_reading_data():
    """Provide sample sensor reading data for testing."""
    return {
        'sensor_id': 'TEST_SENSOR_001',
        'timestamp': datetime.now(UTC),
        'temperature': 22.5,
        'humidity': 45.0
    }


@pytest.fixture(scope="function")
def mock_sensorpush_api_response():
    """Provide mock SensorPush API response data."""
    return {
        'sensors': {
            'TEST_SENSOR_001': [
                {
                    'observed': '2025-01-01T12:00:00Z',
                    'temperature': 22.5,
                    'humidity': 45.0
                },
                {
                    'observed': '2025-01-01T12:10:00Z',
                    'temperature': 23.0,
                    'humidity': 46.0
                }
            ],
            'TEST_SENSOR_002': [
                {
                    'observed': '2025-01-01T12:00:00Z',
                    'temperature': 20.0,
                    'humidity': 50.0
                }
            ]
        }
    }


@pytest.fixture(scope="function")
def mock_sensorpush_status_response():
    """Provide mock SensorPush status API response data."""
    return {
        "sensors": {
            "TEST_SENSOR_001": {
                "temperature": 4.3,
                "humidity": 72.5,
                "battery": 3.1,
                "signal_strength": -65,
                "status": "active"
            },
            "TEST_SENSOR_002": {
                "temperature": 22.1,
                "humidity": 45.2,
                "battery": 3.2,
                "signal_strength": -52,
                "status": "active"
            }
        },
        "gateway_connected": True,
        "timestamp": 1673220000
    }


@pytest.fixture(scope="function")
def mock_api_client(mock_sensorpush_api_response, mock_sensorpush_status_response):
    """Create a mock SensorPush API client."""
    mock_client = Mock(spec=SensorPushAPI)
    mock_client.authenticate.return_value = True
    mock_client.is_token_valid.return_value = True
    mock_client.ensure_valid_token.return_value = True
    mock_client.get_samples.return_value = mock_sensorpush_api_response
    mock_client.get_status.return_value = mock_sensorpush_status_response
    mock_client.get_token_info.return_value = {
        'has_token': True,
        'is_valid': True,
        'expires_at': (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        'token_type': 'Bearer'
    }
    return mock_client


@pytest.fixture(scope="function")
def flask_app(test_config):
    """Create a Flask application for testing."""
    app = create_app('testing')
    app.config.from_object(test_config)
    
    with app.app_context():
        yield app


@pytest.fixture(scope="function")
def flask_client(flask_app):
    """Create a Flask test client."""
    return flask_app.test_client()


@pytest.fixture(scope="function")
def populated_test_db(test_db_session, sample_sensor_data, sample_reading_data):
    """Create a test database with sample data."""
    # Create test sensor
    sensor = Sensor(**sample_sensor_data)
    test_db_session.add(sensor)
    
    # Create test readings
    for i in range(5):
        reading_data = sample_reading_data.copy()
        reading_data['timestamp'] = datetime.now(UTC) - timedelta(minutes=i*10)
        reading_data['temperature'] = 20.0 + i
        reading_data['humidity'] = 40.0 + i
        
        reading = SensorReading(**reading_data)
        test_db_session.add(reading)
    
    # Create another sensor
    sensor2_data = sample_sensor_data.copy()
    sensor2_data['sensor_id'] = 'TEST_SENSOR_002'
    sensor2_data['name'] = 'Test Sensor 2'
    sensor2 = Sensor(**sensor2_data)
    test_db_session.add(sensor2)
    
    # Create readings for second sensor
    for i in range(3):
        reading_data = sample_reading_data.copy()
        reading_data['sensor_id'] = 'TEST_SENSOR_002'
        reading_data['timestamp'] = datetime.now(UTC) - timedelta(minutes=i*15)
        reading_data['temperature'] = 18.0 + i
        reading_data['humidity'] = 35.0 + i
        
        reading = SensorReading(**reading_data)
        test_db_session.add(reading)
    
    test_db_session.commit()
    yield test_db_session


@pytest.fixture(scope="function")
def mock_polling_service(mock_api_client, test_config):
    """Create a mock polling service for testing."""
    with patch('polling_service.SensorPushAPI') as mock_api_class:
        mock_api_class.return_value = mock_api_client
        service = PollingService(config_class=test_config, api_client=mock_api_client)
        yield service


@pytest.fixture(scope="function")
def old_test_data(test_db_session):
    """Create old test data for data retention testing."""
    # Create sensor
    sensor = Sensor(
        sensor_id='OLD_SENSOR',
        name='Old Test Sensor',
        active=True,
        min_temp=0.0,
        max_temp=50.0,
        min_humidity=0.0,
        max_humidity=100.0
    )
    test_db_session.add(sensor)
    
    # Create old readings (older than 6 months)
    old_date = datetime.now(UTC) - timedelta(days=200)  # ~6.5 months ago
    for i in range(10):
        reading = SensorReading(
            sensor_id='OLD_SENSOR',
            timestamp=old_date - timedelta(hours=i),
            temperature=20.0 + i,
            humidity=50.0 + i
        )
        test_db_session.add(reading)
    
    # Create recent readings (within 6 months)
    recent_date = datetime.now(UTC) - timedelta(days=30)  # 1 month ago
    for i in range(5):
        reading = SensorReading(
            sensor_id='OLD_SENSOR',
            timestamp=recent_date - timedelta(hours=i),
            temperature=25.0 + i,
            humidity=55.0 + i
        )
        test_db_session.add(reading)
    
    test_db_session.commit()
    yield test_db_session


@pytest.fixture(scope="function")
def mock_requests():
    """Mock requests module for API testing."""
    with patch('requests.Session') as mock_session_class:
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        # Mock successful authentication response
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {'authorization': 'test_auth_code'}
        auth_response.raise_for_status.return_value = None
        
        # Mock successful token response
        token_response = Mock()
        token_response.status_code = 200
        token_response.json.return_value = {'accesstoken': 'test_access_token', 'expires_in': 3600}
        token_response.raise_for_status.return_value = None
        
        # Configure mock session to return appropriate responses
        mock_session.post.side_effect = [auth_response, token_response]
        
        yield mock_session


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Automatically set up test environment for all tests."""
    # Store original environment values
    original_env = {}
    test_env_vars = ['FLASK_ENV', 'TESTING', 'SENSORPUSH_USERNAME', 'SENSORPUSH_PASSWORD']
    
    for var in test_env_vars:
        original_env[var] = os.environ.get(var)
    
    # Only set environment for non-config tests
    # Config tests need to control their own environment
    test_file = os.environ.get('PYTEST_CURRENT_TEST', '')
    if 'test_config.py' not in test_file:
        # Ensure we're in testing mode
        os.environ['FLASK_ENV'] = 'testing'
        os.environ['TESTING'] = 'true'
        
        # Set SensorPush API credentials for testing
        os.environ['SENSORPUSH_USERNAME'] = 'test_user'
        os.environ['SENSORPUSH_PASSWORD'] = 'test_password'
        logger.info("Set SENSORPUSH_USERNAME and SENSORPUSH_PASSWORD for testing.")

    # Disable database auto-initialization during tests
    with patch('database.init_database'):
        yield
    
    # Restore original environment
    for var, value in original_env.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


@pytest.fixture(scope="function")
def temp_log_file():
    """Create a temporary log file for testing."""
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.log', delete=False) as f:
        temp_path = f.name
    
    yield temp_path
    
    # Clean up
    try:
        os.unlink(temp_path)
    except OSError:
        pass


@pytest.fixture(scope="function")
def error_test_data():
    """Provide test data for error handling tests."""
    return {
        'test_exception': ValueError("Test error message"),
        'test_context': "Test context",
        'test_additional_data': {"key": "value", "number": 42}
    }


# Utility functions for tests
def create_test_sensor(session, sensor_id="TEST_SENSOR", name="Test Sensor"):
    """Utility function to create a test sensor."""
    sensor = Sensor(
        sensor_id=sensor_id,
        name=name,
        active=True,
        min_temp=0.0,
        max_temp=50.0,
        min_humidity=0.0,
        max_humidity=100.0
    )
    session.add(sensor)
    session.commit()
    return sensor


def create_test_reading(session, sensor_id="TEST_SENSOR", temperature=20.0, humidity=50.0, timestamp=None):
    """Utility function to create a test sensor reading."""
    if timestamp is None:
        timestamp = datetime.now(UTC)
    
    reading = SensorReading(
        sensor_id=sensor_id,
        timestamp=timestamp,
        temperature=temperature,
        humidity=humidity
    )
    session.add(reading)
    session.commit()
    return reading