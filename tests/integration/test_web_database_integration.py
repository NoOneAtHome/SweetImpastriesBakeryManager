"""
Integration tests for web interface and database interaction.

Tests the integration between Flask web routes and database operations,
verifying data retrieval and display functionality.
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from app import create_app
from models import Sensor, SensorReading, Error
from config import TestingConfig


@pytest.mark.integration
class TestWebDatabaseIntegration:
    """Test integration between web interface and database."""
    
    def test_sensors_api_endpoint_with_database(self, populated_test_db, flask_client):
        """Test /api/sensors endpoint with real database data."""
        response = flask_client.get('/api/sensors')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['success'] is True
        assert data['count'] == 2  # From populated_test_db fixture
        assert len(data['data']) == 2
        
        # Verify sensor data structure
        sensor_data = data['data'][0]
        assert 'sensor_id' in sensor_data
        assert 'name' in sensor_data
        assert 'active' in sensor_data
        assert 'min_temp' in sensor_data
        assert 'max_temp' in sensor_data
        assert 'min_humidity' in sensor_data
        assert 'max_humidity' in sensor_data
    
    def test_latest_readings_api_endpoint_with_database(self, populated_test_db, flask_client):
        """Test /api/sensors/latest endpoint with real database data."""
        response = flask_client.get('/api/sensors/latest')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['success'] is True
        assert data['count'] == 2  # Two active sensors
        assert len(data['data']) == 2
        
        # Verify reading data structure
        reading_data = data['data'][0]
        assert 'id' in reading_data
        assert 'sensor_id' in reading_data
        assert 'timestamp' in reading_data
        assert 'temperature' in reading_data
        assert 'humidity' in reading_data
        assert 'sensor_name' in reading_data
    
    def test_sensor_history_api_endpoint_with_database(self, populated_test_db, flask_client):
        """Test /api/sensors/history endpoint with real database data."""
        response = flask_client.get('/api/sensors/history?sensor_id=TEST_SENSOR_001&time_slice=24h')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['success'] is True
        assert 'data' in data
        assert 'sensor' in data['data']
        assert 'readings' in data['data']
        assert 'time_slice' in data['data']
        assert 'start_time' in data['data']
        assert 'count' in data['data']
        
        # Verify sensor information
        sensor_info = data['data']['sensor']
        assert sensor_info['sensor_id'] == 'TEST_SENSOR_001'
        assert sensor_info['name'] == 'Test Sensor 1'
        
        # Verify readings
        readings = data['data']['readings']
        assert len(readings) > 0
        assert data['data']['count'] == len(readings)
    
    def test_sensor_history_api_invalid_sensor(self, populated_test_db, flask_client):
        """Test /api/sensors/history endpoint with invalid sensor ID."""
        response = flask_client.get('/api/sensors/history?sensor_id=INVALID_SENSOR&time_slice=24h')
        
        assert response.status_code == 404
        data = json.loads(response.data)
        
        assert data['success'] is False
        assert 'Sensor not found' in data['error']
    
    def test_sensor_history_api_missing_parameters(self, populated_test_db, flask_client):
        """Test /api/sensors/history endpoint with missing parameters."""
        # Missing sensor_id
        response = flask_client.get('/api/sensors/history?time_slice=24h')
        assert response.status_code == 400
        
        # Missing time_slice
        response = flask_client.get('/api/sensors/history?sensor_id=TEST_SENSOR_001')
        assert response.status_code == 400
    
    def test_sensor_history_api_invalid_time_slice(self, populated_test_db, flask_client):
        """Test /api/sensors/history endpoint with invalid time slice."""
        response = flask_client.get('/api/sensors/history?sensor_id=TEST_SENSOR_001&time_slice=invalid')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        
        assert data['success'] is False
        assert 'Invalid time_slice' in data['error']
    
    def test_historical_data_api_endpoint_with_database(self, populated_test_db, flask_client):
        """Test /api/historical_data endpoint with real database data."""
        # Test with default time range (24 hours)
        response = flask_client.get('/api/historical_data?sensor_id=TEST_SENSOR_001')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Should return an array of objects
        assert isinstance(data, list)
        if len(data) > 0:
            # Verify data structure
            reading = data[0]
            assert 'timestamp' in reading
            assert 'temperature' in reading
            assert 'humidity' in reading
    
    def test_historical_data_api_with_time_range(self, populated_test_db, flask_client):
        """Test /api/historical_data endpoint with specific time range."""
        # Use a specific time range
        start_time = '2025-01-01T00:00:00Z'
        end_time = '2025-01-02T00:00:00Z'
        
        response = flask_client.get(f'/api/historical_data?sensor_id=TEST_SENSOR_001&start_time={start_time}&end_time={end_time}')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Should return an array
        assert isinstance(data, list)
        # Data might be empty if no readings in that time range, which is valid
    
    def test_historical_data_api_invalid_sensor(self, populated_test_db, flask_client):
        """Test /api/historical_data endpoint with invalid sensor ID."""
        response = flask_client.get('/api/historical_data?sensor_id=INVALID_SENSOR')
        
        assert response.status_code == 404
        data = json.loads(response.data)
        
        assert data['success'] is False
        assert 'Sensor not found' in data['error']
    
    def test_historical_data_api_missing_sensor_id(self, populated_test_db, flask_client):
        """Test /api/historical_data endpoint with missing sensor_id parameter."""
        response = flask_client.get('/api/historical_data')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        
        assert data['success'] is False
        assert 'Missing required parameter: sensor_id' in data['error']
    
    def test_historical_data_api_invalid_time_format(self, populated_test_db, flask_client):
        """Test /api/historical_data endpoint with invalid time format."""
        response = flask_client.get('/api/historical_data?sensor_id=TEST_SENSOR_001&start_time=invalid-time')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        
        assert data['success'] is False
        assert 'Invalid start_time format' in data['error']
    
    def test_historical_data_api_invalid_time_range(self, populated_test_db, flask_client):
        """Test /api/historical_data endpoint with invalid time range (start >= end)."""
        start_time = '2025-01-02T00:00:00Z'
        end_time = '2025-01-01T00:00:00Z'  # End before start
        
        response = flask_client.get(f'/api/historical_data?sensor_id=TEST_SENSOR_001&start_time={start_time}&end_time={end_time}')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        
        assert data['success'] is False
        assert 'start_time must be before end_time' in data['error']
    
    def test_historical_data_api_no_data_found(self, populated_test_db, flask_client):
        """Test /api/historical_data endpoint when no data is found."""
        # Use a time range in the far future where no data exists
        start_time = '2030-01-01T00:00:00Z'
        end_time = '2030-01-02T00:00:00Z'
        
        response = flask_client.get(f'/api/historical_data?sensor_id=TEST_SENSOR_001&start_time={start_time}&end_time={end_time}')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Should return empty array when no data found
        assert isinstance(data, list)
        assert len(data) == 0
    
    def test_dashboard_web_interface_with_database(self, populated_test_db, flask_client):
        """Test dashboard web interface with real database data."""
        response = flask_client.get('/')
        
        assert response.status_code == 200
        assert b'Sensor Dashboard' in response.data
        assert b'TEST_SENSOR_001' in response.data
        assert b'TEST_SENSOR_002' in response.data
        assert b'Test Sensor 1' in response.data
        assert b'Test Sensor 2' in response.data
    
    def test_sensor_detail_web_interface_with_database(self, populated_test_db, flask_client):
        """Test sensor detail web interface with real database data."""
        response = flask_client.get('/sensor/TEST_SENSOR_001')
        
        assert response.status_code == 200
        assert b'Test Sensor 1' in response.data
        assert b'TEST_SENSOR_001' in response.data
        assert b'Temperature' in response.data
        assert b'Humidity' in response.data
    
    def test_sensor_detail_web_interface_invalid_sensor(self, populated_test_db, flask_client):
        """Test sensor detail web interface with invalid sensor."""
        response = flask_client.get('/sensor/INVALID_SENSOR')
        
        assert response.status_code == 404
        assert b'not found' in response.data
    
    def test_web_interface_error_handling(self, flask_client):
        """Test web interface error handling."""
        # Test 404 error
        response = flask_client.get('/nonexistent-endpoint')
        assert response.status_code == 404
        
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'not found' in data['error']
    
    def test_api_endpoints_with_empty_database(self, test_db_session, flask_client):
        """Test API endpoints with empty database."""
        # Test sensors endpoint
        response = flask_client.get('/api/sensors')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 0
        assert len(data['data']) == 0
        
        # Test latest readings endpoint
        response = flask_client.get('/api/sensors/latest')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 0
        assert len(data['data']) == 0


@pytest.mark.integration
class TestWebDatabaseErrorHandling:
    """Test error handling in web-database integration."""
    
    def test_api_endpoint_database_error(self, flask_client):
        """Test API endpoint handling of database errors."""
        with patch('app.get_db_session_context') as mock_context:
            mock_context.side_effect = Exception("Database connection failed")
            
            response = flask_client.get('/api/sensors')
            
            assert response.status_code == 500
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'error_id' in data
    
    def test_web_interface_database_error(self, flask_client):
        """Test web interface handling of database errors."""
        with patch('app.get_db_session_context') as mock_context:
            mock_context.side_effect = Exception("Database connection failed")
            
            response = flask_client.get('/')
            
            assert response.status_code == 500
            assert b'Failed to load dashboard' in response.data
    
    def test_sensor_detail_database_error(self, flask_client):
        """Test sensor detail page handling of database errors."""
        with patch('app.get_db_session_context') as mock_context:
            mock_context.side_effect = Exception("Database connection failed")
            
            response = flask_client.get('/sensor/TEST_SENSOR_001')
            
            assert response.status_code == 500
            assert b'Failed to load sensor details' in response.data


@pytest.mark.integration
class TestWebDatabaseDataFlow:
    """Test data flow from database to web interface."""
    
    def test_sensor_data_serialization(self, test_db_session, flask_client):
        """Test sensor data serialization from database to API."""
        # Create test sensor with specific values
        sensor = Sensor(
            sensor_id='SERIALIZE_TEST',
            name='Serialization Test Sensor',
            active=True,
            min_temp=10.5,
            max_temp=30.5,
            min_humidity=20.0,
            max_humidity=80.0
        )
        test_db_session.add(sensor)
        test_db_session.commit()
        
        response = flask_client.get('/api/sensors')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        sensor_data = next(s for s in data['data'] if s['sensor_id'] == 'SERIALIZE_TEST')
        
        assert sensor_data['sensor_id'] == 'SERIALIZE_TEST'
        assert sensor_data['name'] == 'Serialization Test Sensor'
        assert sensor_data['active'] is True
        assert sensor_data['min_temp'] == 10.5
        assert sensor_data['max_temp'] == 30.5
        assert sensor_data['min_humidity'] == 20.0
        assert sensor_data['max_humidity'] == 80.0
    
    def test_sensor_reading_serialization(self, test_db_session, flask_client):
        """Test sensor reading serialization from database to API."""
        # Create test sensor and reading
        sensor = Sensor(
            sensor_id='READING_TEST',
            name='Reading Test Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        test_time = datetime(2025, 1, 1, 12, 0, 0)
        reading = SensorReading(
            sensor_id='READING_TEST',
            timestamp=test_time,
            temperature=22.5,
            humidity=45.0
        )
        test_db_session.add(reading)
        test_db_session.commit()
        
        response = flask_client.get('/api/sensors/latest')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        reading_data = next(r for r in data['data'] if r['sensor_id'] == 'READING_TEST')
        
        assert reading_data['sensor_id'] == 'READING_TEST'
        assert reading_data['temperature'] == 22.5
        assert reading_data['humidity'] == 45.0
        assert reading_data['sensor_name'] == 'Reading Test Sensor'
        assert test_time.isoformat() in reading_data['timestamp']
    
    def test_time_slice_filtering(self, test_db_session, flask_client):
        """Test time slice filtering in sensor history."""
        # Create test sensor
        sensor = Sensor(
            sensor_id='TIME_TEST',
            name='Time Test Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        # Create readings at different times
        now = datetime.utcnow()
        readings_data = [
            (now - timedelta(hours=2), 20.0, 40.0),  # Within 24h
            (now - timedelta(hours=12), 21.0, 41.0),  # Within 24h
            (now - timedelta(days=2), 19.0, 39.0),   # Outside 24h
            (now - timedelta(days=8), 18.0, 38.0),   # Outside 7d
        ]
        
        for timestamp, temp, humidity in readings_data:
            reading = SensorReading(
                sensor_id='TIME_TEST',
                timestamp=timestamp,
                temperature=temp,
                humidity=humidity
            )
            test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Test 24h filter
        response = flask_client.get('/api/sensors/history?sensor_id=TIME_TEST&time_slice=24h')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['count'] == 2  # Only 2 readings within 24h
        
        # Test 7d filter
        response = flask_client.get('/api/sensors/history?sensor_id=TIME_TEST&time_slice=7d')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['count'] == 3  # 3 readings within 7d
    
    def test_sensor_reading_ordering(self, test_db_session, flask_client):
        """Test that sensor readings are properly ordered by timestamp."""
        # Create test sensor
        sensor = Sensor(
            sensor_id='ORDER_TEST',
            name='Order Test Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        # Create readings in non-chronological order
        base_time = datetime.utcnow()
        readings_data = [
            (base_time - timedelta(hours=1), 20.0),  # Second newest
            (base_time - timedelta(hours=3), 18.0),  # Oldest
            (base_time, 22.0),                       # Newest
            (base_time - timedelta(hours=2), 19.0),  # Second oldest
        ]
        
        for timestamp, temp in readings_data:
            reading = SensorReading(
                sensor_id='ORDER_TEST',
                timestamp=timestamp,
                temperature=temp,
                humidity=50.0
            )
            test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Test latest reading endpoint
        response = flask_client.get('/api/sensors/latest')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        order_reading = next(r for r in data['data'] if r['sensor_id'] == 'ORDER_TEST')
        assert order_reading['temperature'] == 22.0  # Should be the newest reading
        
        # Test history endpoint ordering
        response = flask_client.get('/api/sensors/history?sensor_id=ORDER_TEST&time_slice=24h')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        readings = data['data']['readings']
        temperatures = [r['temperature'] for r in readings]
        assert temperatures == [22.0, 20.0, 19.0, 18.0]  # Descending order by timestamp


@pytest.mark.integration
class TestWebDatabasePerformance:
    """Test performance aspects of web-database integration."""
    
    def test_large_dataset_api_performance(self, test_db_session, flask_client):
        """Test API performance with larger datasets."""
        # Create multiple sensors with many readings
        sensors_count = 10
        readings_per_sensor = 50
        
        for i in range(sensors_count):
            sensor = Sensor(
                sensor_id=f'PERF_SENSOR_{i:03d}',
                name=f'Performance Test Sensor {i}',
                active=True,
                min_temp=0.0,
                max_temp=50.0,
                min_humidity=0.0,
                max_humidity=100.0
            )
            test_db_session.add(sensor)
            
            # Add readings for each sensor
            base_time = datetime.utcnow()
            for j in range(readings_per_sensor):
                reading = SensorReading(
                    sensor_id=f'PERF_SENSOR_{i:03d}',
                    timestamp=base_time - timedelta(minutes=j),
                    temperature=20.0 + i + j * 0.1,
                    humidity=50.0 + i + j * 0.1
                )
                test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Test sensors endpoint
        response = flask_client.get('/api/sensors')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['count'] == sensors_count
        
        # Test latest readings endpoint
        response = flask_client.get('/api/sensors/latest')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['count'] == sensors_count
        
        # Test history endpoint for one sensor
        response = flask_client.get('/api/sensors/history?sensor_id=PERF_SENSOR_000&time_slice=24h')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['count'] == readings_per_sensor
    
    def test_web_interface_with_many_sensors(self, test_db_session, flask_client):
        """Test web interface performance with many sensors."""
        # Create many sensors with latest readings
        sensors_count = 20
        
        for i in range(sensors_count):
            sensor = Sensor(
                sensor_id=f'WEB_SENSOR_{i:03d}',
                name=f'Web Test Sensor {i}',
                active=True,
                min_temp=0.0,
                max_temp=50.0,
                min_humidity=0.0,
                max_humidity=100.0
            )
            test_db_session.add(sensor)
            
            # Add latest reading
            reading = SensorReading(
                sensor_id=f'WEB_SENSOR_{i:03d}',
                timestamp=datetime.utcnow(),
                temperature=20.0 + i,
                humidity=50.0 + i
            )
            test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Test dashboard loads successfully
        response = flask_client.get('/')
        assert response.status_code == 200
        
        # Verify some sensors are displayed
        assert b'WEB_SENSOR_000' in response.data
        assert b'WEB_SENSOR_010' in response.data
        assert b'Web Test Sensor' in response.data