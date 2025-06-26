"""
End-to-end tests for complete data flow in the BakerySensors project.

Tests the entire pipeline from API polling to web interface display,
verifying data integrity and system behavior under real-world conditions.
"""

import pytest
import json
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from threading import Event

from sensorpush_api import SensorPushAPI
from polling_service import PollingService
from data_retention import purge_old_readings
from models import Sensor, SensorReading, Error
from config import TestingConfig
from app import create_app


@pytest.mark.e2e
class TestCompleteDataFlow:
    """Test complete data flow from API to web interface."""
    
    def test_full_pipeline_api_to_web(self, test_db_session, flask_client, mock_api_responses):
        """Test complete pipeline: API polling -> Database -> Web interface."""
        # Setup test configuration
        config = TestingConfig()
        config.POLLING_INTERVAL = 1  # Fast polling for testing
        
        # Mock API responses
        mock_samples_response = {
            'sensors': {
                'E2E_SENSOR_001': {
                    'name': 'E2E Test Sensor 1',
                    'active': True,
                    'battery_voltage': 3.2
                }
            },
            'samples': [
                {
                    'sensor': 'E2E_SENSOR_001',
                    'observed': '2025-01-01T12:00:00.000Z',
                    'temperature': 22.5,
                    'humidity': 45.0
                },
                {
                    'sensor': 'E2E_SENSOR_001',
                    'observed': '2025-01-01T12:05:00.000Z',
                    'temperature': 22.7,
                    'humidity': 45.2
                }
            ]
        }
        
        # Step 1: Initialize and run polling service
        with patch('sensorpush_api.requests.post') as mock_post, \
             patch('sensorpush_api.requests.get') as mock_get, \
             patch('polling_service.get_db_session_context') as mock_db_context:
            
            # Mock authentication
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'access_token': 'test_token'}
            
            # Mock samples API call
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_samples_response
            
            # Mock database context
            mock_db_context.return_value.__enter__.return_value = test_db_session
            mock_db_context.return_value.__exit__.return_value = None
            
            # Initialize services
            api_client = SensorPushAPI(config)
            polling_service = PollingService(config, api_client)
            
            # Run one polling cycle
            polling_service.poll_and_store_data()
        
        # Step 2: Verify data was stored in database
        sensors = test_db_session.query(Sensor).all()
        assert len(sensors) == 1
        assert sensors[0].sensor_id == 'E2E_SENSOR_001'
        assert sensors[0].name == 'E2E Test Sensor 1'
        
        readings = test_db_session.query(SensorReading).all()
        assert len(readings) == 2
        assert all(r.sensor_id == 'E2E_SENSOR_001' for r in readings)
        assert readings[0].temperature == 22.5
        assert readings[1].temperature == 22.7
        
        # Step 3: Test web interface displays the data
        # Test dashboard
        response = flask_client.get('/')
        assert response.status_code == 200
        assert b'E2E_SENSOR_001' in response.data
        assert b'E2E Test Sensor 1' in response.data
        assert b'22.7' in response.data  # Latest temperature
        
        # Test sensor detail page
        response = flask_client.get('/sensor/E2E_SENSOR_001')
        assert response.status_code == 200
        assert b'E2E Test Sensor 1' in response.data
        assert b'22.5' in response.data
        assert b'22.7' in response.data
        
        # Step 4: Test API endpoints
        response = flask_client.get('/api/sensors')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 1
        assert data['data'][0]['sensor_id'] == 'E2E_SENSOR_001'
        
        response = flask_client.get('/api/sensors/latest')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 1
        assert data['data'][0]['temperature'] == 22.7  # Latest reading
    
    def test_error_propagation_through_pipeline(self, test_db_session, flask_client):
        """Test error handling and propagation through the complete pipeline."""
        config = TestingConfig()
        
        # Step 1: Simulate API error during polling
        with patch('sensorpush_api.requests.post') as mock_post, \
             patch('polling_service.get_db_session_context') as mock_db_context, \
             patch('error_handling.get_db_session_context') as mock_error_context:
            
            # Mock authentication failure
            mock_post.return_value.status_code = 401
            mock_post.return_value.json.return_value = {'error': 'Invalid credentials'}
            
            # Mock database contexts
            mock_db_context.return_value.__enter__.return_value = test_db_session
            mock_db_context.return_value.__exit__.return_value = None
            mock_error_context.return_value.__enter__.return_value = test_db_session
            mock_error_context.return_value.__exit__.return_value = None
            
            # Initialize services
            api_client = SensorPushAPI(config)
            polling_service = PollingService(config, api_client)
            
            # Run polling - should handle error gracefully
            polling_service.poll_and_store_data()
        
        # Step 2: Verify error was logged to database
        errors = test_db_session.query(Error).all()
        assert len(errors) > 0
        
        # Find authentication error
        auth_error = next((e for e in errors if 'authentication' in e.message.lower()), None)
        assert auth_error is not None
        assert auth_error.level in ['ERROR', 'CRITICAL']
        
        # Step 3: Verify web interface handles missing data gracefully
        response = flask_client.get('/')
        assert response.status_code == 200
        # Should display empty dashboard without crashing
        assert b'No sensors found' in response.data or b'Sensor Dashboard' in response.data
        
        # Step 4: Verify API endpoints handle empty data
        response = flask_client.get('/api/sensors')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['count'] == 0
    
    def test_data_retention_in_complete_flow(self, test_db_session, flask_client):
        """Test data retention as part of complete data flow."""
        config = TestingConfig()
        config.DATA_RETENTION_DAYS = 7  # Short retention for testing
        
        # Step 1: Create test data with different ages
        now = datetime.utcnow()
        
        # Create sensor
        sensor = Sensor(
            sensor_id='RETENTION_E2E_SENSOR',
            name='Retention E2E Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        # Create readings: some recent, some old
        readings_data = [
            (now - timedelta(days=1), 20.0, 40.0),   # Recent
            (now - timedelta(days=3), 21.0, 41.0),   # Recent
            (now - timedelta(days=10), 18.0, 38.0),  # Old
            (now - timedelta(days=15), 19.0, 39.0),  # Old
        ]
        
        for timestamp, temp, humidity in readings_data:
            reading = SensorReading(
                sensor_id='RETENTION_E2E_SENSOR',
                timestamp=timestamp,
                temperature=temp,
                humidity=humidity
            )
            test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Step 2: Verify initial state in web interface
        response = flask_client.get('/sensor/RETENTION_E2E_SENSOR')
        assert response.status_code == 200
        assert b'20.0' in response.data  # Recent reading
        assert b'18.0' in response.data  # Old reading (should be visible initially)
        
        # Step 3: Run data retention
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            retention_service = DataRetentionService(config)
            stats = retention_service.purge_old_data()
        
        # Verify retention worked
        assert stats['readings_purged'] == 2
        
        # Step 4: Verify web interface reflects retention
        response = flask_client.get('/sensor/RETENTION_E2E_SENSOR')
        assert response.status_code == 200
        assert b'20.0' in response.data  # Recent reading still visible
        assert b'18.0' not in response.data  # Old reading should be gone
        
        # Step 5: Verify API reflects retention
        response = flask_client.get('/api/sensors/history?sensor_id=RETENTION_E2E_SENSOR&time_slice=30d')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['count'] == 2  # Only recent readings remain
    
    def test_concurrent_operations_data_integrity(self, test_db_session):
        """Test data integrity under concurrent operations."""
        config = TestingConfig()
        
        # Mock concurrent polling and retention operations
        mock_samples_response = {
            'sensors': {
                'CONCURRENT_SENSOR': {
                    'name': 'Concurrent Test Sensor',
                    'active': True,
                    'battery_voltage': 3.2
                }
            },
            'samples': [
                {
                    'sensor': 'CONCURRENT_SENSOR',
                    'observed': '2025-01-01T12:00:00.000Z',
                    'temperature': 22.5,
                    'humidity': 45.0
                }
            ]
        }
        
        # Create some existing old data
        now = datetime.utcnow()
        sensor = Sensor(
            sensor_id='CONCURRENT_SENSOR',
            name='Concurrent Test Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        old_reading = SensorReading(
            sensor_id='CONCURRENT_SENSOR',
            timestamp=now - timedelta(days=35),
            temperature=18.0,
            humidity=38.0
        )
        test_db_session.add(old_reading)
        test_db_session.commit()
        
        # Simulate concurrent operations
        with patch('sensorpush_api.requests.post') as mock_post, \
             patch('sensorpush_api.requests.get') as mock_get, \
             patch('polling_service.get_db_session_context') as mock_poll_context, \
             patch('data_retention.get_db_session_context') as mock_retention_context:
            
            # Mock API responses
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'access_token': 'test_token'}
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_samples_response
            
            # Mock database contexts
            mock_poll_context.return_value.__enter__.return_value = test_db_session
            mock_poll_context.return_value.__exit__.return_value = None
            mock_retention_context.return_value.__enter__.return_value = test_db_session
            mock_retention_context.return_value.__exit__.return_value = None
            
            # Initialize services
            api_client = SensorPushAPI(config)
            polling_service = PollingService(config, api_client)
            retention_service = DataRetentionService(config)
            
            # Run operations
            polling_service.poll_and_store_data()  # Add new data
            retention_stats = retention_service.purge_old_data()  # Remove old data
        
        # Verify data integrity
        sensors = test_db_session.query(Sensor).filter_by(sensor_id='CONCURRENT_SENSOR').all()
        assert len(sensors) == 1  # Sensor should exist
        
        readings = test_db_session.query(SensorReading).filter_by(sensor_id='CONCURRENT_SENSOR').all()
        assert len(readings) == 1  # Only new reading should remain
        assert readings[0].temperature == 22.5  # New reading
        assert retention_stats['readings_purged'] == 1  # Old reading was purged


@pytest.mark.e2e
class TestSystemResilience:
    """Test system resilience and recovery under various failure conditions."""
    
    def test_database_recovery_after_failure(self, test_db_session, flask_client):
        """Test system recovery after database failures."""
        config = TestingConfig()
        
        # Step 1: Simulate database failure during polling
        with patch('polling_service.get_db_session_context') as mock_context:
            mock_context.side_effect = Exception("Database connection failed")
            
            api_client = SensorPushAPI(config)
            polling_service = PollingService(config, api_client)
            
            # Should handle database failure gracefully
            polling_service.poll_and_store_data()
        
        # Step 2: Verify web interface handles database unavailability
        with patch('app.get_db_session_context') as mock_context:
            mock_context.side_effect = Exception("Database connection failed")
            
            response = flask_client.get('/')
            assert response.status_code == 500
            assert b'Failed to load dashboard' in response.data
        
        # Step 3: Simulate database recovery
        # Create test data to simulate recovered database
        sensor = Sensor(
            sensor_id='RECOVERY_SENSOR',
            name='Recovery Test Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        reading = SensorReading(
            sensor_id='RECOVERY_SENSOR',
            timestamp=datetime.utcnow(),
            temperature=22.0,
            humidity=45.0
        )
        test_db_session.add(reading)
        test_db_session.commit()
        
        # Step 4: Verify system works normally after recovery
        response = flask_client.get('/')
        assert response.status_code == 200
        assert b'RECOVERY_SENSOR' in response.data
        assert b'Recovery Test Sensor' in response.data
    
    def test_api_failure_and_recovery(self, test_db_session, flask_client):
        """Test system behavior during API failures and recovery."""
        config = TestingConfig()
        
        # Step 1: Simulate API failure
        with patch('sensorpush_api.requests.post') as mock_post, \
             patch('polling_service.get_db_session_context') as mock_context, \
             patch('error_handling.get_db_session_context') as mock_error_context:
            
            # Mock API failure
            mock_post.side_effect = Exception("API connection timeout")
            
            # Mock database contexts
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            mock_error_context.return_value.__enter__.return_value = test_db_session
            mock_error_context.return_value.__exit__.return_value = None
            
            api_client = SensorPushAPI(config)
            polling_service = PollingService(config, api_client)
            
            # Should handle API failure gracefully
            polling_service.poll_and_store_data()
        
        # Step 2: Verify error was logged
        errors = test_db_session.query(Error).all()
        api_errors = [e for e in errors if 'API' in e.message or 'timeout' in e.message]
        assert len(api_errors) > 0
        
        # Step 3: Verify web interface still works with existing data
        response = flask_client.get('/')
        assert response.status_code == 200
        # Should display dashboard even without new data
        
        # Step 4: Simulate API recovery with new data
        mock_samples_response = {
            'sensors': {
                'RECOVERY_API_SENSOR': {
                    'name': 'API Recovery Sensor',
                    'active': True,
                    'battery_voltage': 3.2
                }
            },
            'samples': [
                {
                    'sensor': 'RECOVERY_API_SENSOR',
                    'observed': '2025-01-01T12:00:00.000Z',
                    'temperature': 23.0,
                    'humidity': 46.0
                }
            ]
        }
        
        with patch('sensorpush_api.requests.post') as mock_post, \
             patch('sensorpush_api.requests.get') as mock_get, \
             patch('polling_service.get_db_session_context') as mock_context:
            
            # Mock successful API calls
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'access_token': 'test_token'}
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_samples_response
            
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            # Should work normally after recovery
            polling_service.poll_and_store_data()
        
        # Step 5: Verify new data appears in web interface
        response = flask_client.get('/')
        assert response.status_code == 200
        assert b'RECOVERY_API_SENSOR' in response.data
        assert b'API Recovery Sensor' in response.data
    
    def test_partial_system_failure_isolation(self, test_db_session, flask_client):
        """Test that failures in one component don't affect others."""
        config = TestingConfig()
        
        # Create some existing data
        sensor = Sensor(
            sensor_id='ISOLATION_SENSOR',
            name='Isolation Test Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        reading = SensorReading(
            sensor_id='ISOLATION_SENSOR',
            timestamp=datetime.utcnow(),
            temperature=22.0,
            humidity=45.0
        )
        test_db_session.add(reading)
        test_db_session.commit()
        
        # Step 1: Simulate polling service failure
        with patch('polling_service.PollingService.poll_and_store_data') as mock_poll:
            mock_poll.side_effect = Exception("Polling service crashed")
            
            # Web interface should still work
            response = flask_client.get('/')
            assert response.status_code == 200
            assert b'ISOLATION_SENSOR' in response.data
            
            # API endpoints should still work
            response = flask_client.get('/api/sensors')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['count'] == 1
        
        # Step 2: Simulate data retention service failure
        with patch('data_retention.DataRetentionService.purge_old_data') as mock_retention:
            mock_retention.side_effect = Exception("Retention service crashed")
            
            # Web interface should still work
            response = flask_client.get('/sensor/ISOLATION_SENSOR')
            assert response.status_code == 200
            assert b'Isolation Test Sensor' in response.data
            
            # Polling should still work (if API is available)
            with patch('sensorpush_api.requests.post') as mock_post, \
                 patch('sensorpush_api.requests.get') as mock_get, \
                 patch('polling_service.get_db_session_context') as mock_context:
                
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {'access_token': 'test_token'}
                mock_get.return_value.status_code = 200
                mock_get.return_value.json.return_value = {
                    'sensors': {},
                    'samples': []
                }
                mock_context.return_value.__enter__.return_value = test_db_session
                mock_context.return_value.__exit__.return_value = None
                
                api_client = SensorPushAPI(config)
                polling_service = PollingService(config, api_client)
                
                # Should work despite retention service failure
                polling_service.poll_and_store_data()


@pytest.mark.e2e
class TestPerformanceAndScalability:
    """Test system performance and scalability under load."""
    
    def test_large_dataset_performance(self, test_db_session, flask_client):
        """Test system performance with large datasets."""
        # Create many sensors and readings
        sensors_count = 50
        readings_per_sensor = 100
        
        # Create sensors
        for i in range(sensors_count):
            sensor = Sensor(
                sensor_id=f'PERF_SENSOR_{i:03d}',
                name=f'Performance Sensor {i}',
                active=True,
                min_temp=0.0,
                max_temp=50.0,
                min_humidity=0.0,
                max_humidity=100.0
            )
            test_db_session.add(sensor)
        
        # Create readings
        base_time = datetime.utcnow()
        for i in range(sensors_count):
            for j in range(readings_per_sensor):
                reading = SensorReading(
                    sensor_id=f'PERF_SENSOR_{i:03d}',
                    timestamp=base_time - timedelta(minutes=j),
                    temperature=20.0 + i + j * 0.01,
                    humidity=50.0 + i + j * 0.01
                )
                test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Test dashboard performance
        start_time = time.time()
        response = flask_client.get('/')
        dashboard_time = time.time() - start_time
        
        assert response.status_code == 200
        assert dashboard_time < 5.0  # Should load within 5 seconds
        
        # Test API performance
        start_time = time.time()
        response = flask_client.get('/api/sensors')
        api_time = time.time() - start_time
        
        assert response.status_code == 200
        assert api_time < 3.0  # Should respond within 3 seconds
        
        data = json.loads(response.data)
        assert data['count'] == sensors_count
        
        # Test latest readings performance
        start_time = time.time()
        response = flask_client.get('/api/sensors/latest')
        latest_time = time.time() - start_time
        
        assert response.status_code == 200
        assert latest_time < 3.0  # Should respond within 3 seconds
        
        data = json.loads(response.data)
        assert data['count'] == sensors_count
    
    def test_data_retention_performance(self, test_db_session):
        """Test data retention performance with large datasets."""
        config = TestingConfig()
        config.DATA_RETENTION_DAYS = 30
        
        # Create large amount of old data
        sensors_count = 20
        old_readings_per_sensor = 200
        
        now = datetime.utcnow()
        
        # Create sensors
        for i in range(sensors_count):
            sensor = Sensor(
                sensor_id=f'RETENTION_PERF_SENSOR_{i:03d}',
                name=f'Retention Performance Sensor {i}',
                active=True,
                min_temp=0.0,
                max_temp=50.0,
                min_humidity=0.0,
                max_humidity=100.0
            )
            test_db_session.add(sensor)
        
        # Create old readings (to be purged)
        for i in range(sensors_count):
            for j in range(old_readings_per_sensor):
                reading = SensorReading(
                    sensor_id=f'RETENTION_PERF_SENSOR_{i:03d}',
                    timestamp=now - timedelta(days=35 + j // 10),
                    temperature=20.0 + i + j * 0.01,
                    humidity=50.0 + i + j * 0.01
                )
                test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Test retention performance
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            retention_service = DataRetentionService(config)
            
            start_time = time.time()
            stats = retention_service.purge_old_data()
            retention_time = time.time() - start_time
        
        # Should complete within reasonable time
        assert retention_time < 10.0  # Should complete within 10 seconds
        assert stats['readings_purged'] == sensors_count * old_readings_per_sensor
        
        # Verify data was actually purged
        remaining_readings = test_db_session.query(SensorReading).count()
        assert remaining_readings == 0


@pytest.mark.e2e
class TestRealWorldScenarios:
    """Test real-world usage scenarios."""
    
    def test_typical_daily_operation(self, test_db_session, flask_client):
        """Test typical daily operation scenario."""
        config = TestingConfig()
        
        # Simulate a day of operations
        base_time = datetime.utcnow()
        
        # Create sensors as they would be discovered
        sensors_data = [
            ('DAILY_SENSOR_001', 'Kitchen Sensor'),
            ('DAILY_SENSOR_002', 'Living Room Sensor'),
            ('DAILY_SENSOR_003', 'Bedroom Sensor'),
        ]
        
        for sensor_id, name in sensors_data:
            sensor = Sensor(
                sensor_id=sensor_id,
                name=name,
                active=True,
                min_temp=15.0,
                max_temp=30.0,
                min_humidity=30.0,
                max_humidity=70.0
            )
            test_db_session.add(sensor)
        
        # Simulate hourly readings throughout the day
        for hour in range(24):
            for sensor_id, _ in sensors_data:
                # Simulate realistic temperature and humidity variations
                temp_base = 20.0 + (sensor_id[-1:] == '1') * 2  # Kitchen slightly warmer
                humidity_base = 45.0 + (sensor_id[-1:] == '3') * 5  # Bedroom slightly more humid
                
                # Add some realistic variation
                temp_variation = 2.0 * (hour - 12) / 12  # Warmer in afternoon
                humidity_variation = 5.0 * (1 if hour > 18 or hour < 6 else 0)  # Higher at night
                
                reading = SensorReading(
                    sensor_id=sensor_id,
                    timestamp=base_time - timedelta(hours=23-hour),
                    temperature=temp_base + temp_variation + (hour % 3 - 1) * 0.5,
                    humidity=humidity_base + humidity_variation + (hour % 2) * 2
                )
                test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Test dashboard shows current state
        response = flask_client.get('/')
        assert response.status_code == 200
        assert b'Kitchen Sensor' in response.data
        assert b'Living Room Sensor' in response.data
        assert b'Bedroom Sensor' in response.data
        
        # Test individual sensor views
        for sensor_id, name in sensors_data:
            response = flask_client.get(f'/sensor/{sensor_id}')
            assert response.status_code == 200
            assert name.encode() in response.data
        
        # Test API provides comprehensive data
        response = flask_client.get('/api/sensors/latest')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['count'] == 3
        
        # Test historical data access
        response = flask_client.get(f'/api/sensors/history?sensor_id=DAILY_SENSOR_001&time_slice=24h')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data']['count'] == 24  # 24 hours of data
    
    def test_sensor_maintenance_scenario(self, test_db_session, flask_client):
        """Test scenario where sensors go offline and come back online."""
        config = TestingConfig()
        base_time = datetime.utcnow()
        
        # Create sensor with normal operation
        sensor = Sensor(
            sensor_id='MAINTENANCE_SENSOR',
            name='Maintenance Test Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        # Normal readings before maintenance
        for i in range(10):
            reading = SensorReading(
                sensor_id='MAINTENANCE_SENSOR',
                timestamp=base_time - timedelta(hours=20-i),
                temperature=20.0 + i * 0.1,
                humidity=45.0 + i * 0.2
            )
            test_db_session.add(reading)
        
# Gap in readings (sensor offline for maintenance)
        # No readings for 5 hours
        
        # Readings after maintenance
        for i in range(5):
            reading = SensorReading(
                sensor_id='MAINTENANCE_SENSOR',
                timestamp=base_time - timedelta(hours=5-i),
                temperature=20.5 + i * 0.1,
                humidity=46.0 + i * 0.2
            )
            test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Test that web interface handles gaps gracefully
        response = flask_client.get('/sensor/MAINTENANCE_SENSOR')
        assert response.status_code == 200
        assert b'Maintenance Test Sensor' in response.data
        
        # Test API shows data with gaps
        response = flask_client.get('/api/sensors/history?sensor_id=MAINTENANCE_SENSOR&time_slice=24h')
        assert response.status_code == 200
        data = json.loads(response.data)
        
        # Should have readings before and after maintenance gap
        assert data['data']['count'] == 15  # 10 before + 5 after
        
        # Verify latest reading is from after maintenance
        latest_response = flask_client.get('/api/sensors/latest')
        assert latest_response.status_code == 200
        latest_data = json.loads(latest_response.data)
        
        maintenance_sensor_data = next(
            (s for s in latest_data['data'] if s['sensor_id'] == 'MAINTENANCE_SENSOR'),
            None
        )
        assert maintenance_sensor_data is not None
        assert maintenance_sensor_data['temperature'] > 20.5  # From after maintenance
    
    def test_system_upgrade_scenario(self, test_db_session, flask_client):
        """Test scenario simulating system upgrade with data migration."""
        # Create legacy data format (simulated)
        legacy_sensors = [
            ('LEGACY_SENSOR_001', 'Legacy Kitchen Sensor'),
            ('LEGACY_SENSOR_002', 'Legacy Bathroom Sensor'),
        ]
        
        base_time = datetime.utcnow()
        
        # Create sensors and readings
        for sensor_id, name in legacy_sensors:
            sensor = Sensor(
                sensor_id=sensor_id,
                name=name,
                active=True,
                min_temp=0.0,
                max_temp=50.0,
                min_humidity=0.0,
                max_humidity=100.0
            )
            test_db_session.add(sensor)
            
            # Add historical readings
            for i in range(20):
                reading = SensorReading(
                    sensor_id=sensor_id,
                    timestamp=base_time - timedelta(hours=20-i),
                    temperature=19.0 + i * 0.1 + (sensor_id[-1:] == '2') * 3,  # Bathroom warmer
                    humidity=40.0 + i * 0.5 + (sensor_id[-1:] == '2') * 10   # Bathroom more humid
                )
                test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Test that all legacy data is accessible
        response = flask_client.get('/')
        assert response.status_code == 200
        assert b'Legacy Kitchen Sensor' in response.data
        assert b'Legacy Bathroom Sensor' in response.data
        
        # Test API provides all legacy data
        response = flask_client.get('/api/sensors')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['count'] == 2
        
        # Test individual sensor access
        for sensor_id, name in legacy_sensors:
            response = flask_client.get(f'/sensor/{sensor_id}')
            assert response.status_code == 200
            assert name.encode() in response.data
            
            # Test historical data access
            response = flask_client.get(f'/api/sensors/history?sensor_id={sensor_id}&time_slice=24h')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['data']['count'] == 20
        # Gap