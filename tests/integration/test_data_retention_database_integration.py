"""
Integration tests for data retention service and database interaction.

Tests the integration between data retention functionality and database operations,
verifying data purging, retention statistics, and database consistency.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from data_retention import purge_old_readings
from models import Sensor, SensorReading, Error
from config import TestingConfig


@pytest.mark.integration
class TestDataRetentionDatabaseIntegration:
    """Test integration between data retention service and database."""
    
    def test_data_retention_service_with_real_database(self, test_db_session):
        """Test data retention service with real database operations."""
        # Create test sensors
        sensor1 = Sensor(
            sensor_id='RETENTION_TEST_001',
            name='Retention Test Sensor 1',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        sensor2 = Sensor(
            sensor_id='RETENTION_TEST_002',
            name='Retention Test Sensor 2',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add_all([sensor1, sensor2])
        
        # Create readings with different ages
        now = datetime.utcnow()
        readings_data = [
            # Recent readings (within 30 days)
            ('RETENTION_TEST_001', now - timedelta(days=1), 20.0, 40.0),
            ('RETENTION_TEST_001', now - timedelta(days=15), 21.0, 41.0),
            ('RETENTION_TEST_002', now - timedelta(days=20), 22.0, 42.0),
            
            # Old readings (older than 30 days)
            ('RETENTION_TEST_001', now - timedelta(days=35), 18.0, 38.0),
            ('RETENTION_TEST_001', now - timedelta(days=45), 19.0, 39.0),
            ('RETENTION_TEST_002', now - timedelta(days=40), 17.0, 37.0),
            ('RETENTION_TEST_002', now - timedelta(days=50), 16.0, 36.0),
        ]
        
        for sensor_id, timestamp, temp, humidity in readings_data:
            reading = SensorReading(
                sensor_id=sensor_id,
                timestamp=timestamp,
                temperature=temp,
                humidity=humidity
            )
            test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Initialize data retention service
        config = TestingConfig()
        config.DATA_RETENTION_DAYS = 30
        retention_service = DataRetentionService(config)
        
        # Verify initial state
        initial_count = test_db_session.query(SensorReading).count()
        assert initial_count == 7
        
        # Run data purging
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            stats = retention_service.purge_old_data()
        
        # Verify purging results
        remaining_count = test_db_session.query(SensorReading).count()
        assert remaining_count == 3  # Only recent readings should remain
        assert stats['readings_purged'] == 4
        assert stats['errors_purged'] == 0
        
        # Verify correct readings were kept
        remaining_readings = test_db_session.query(SensorReading).all()
        for reading in remaining_readings:
            days_old = (now - reading.timestamp).days
            assert days_old <= 30
    
    def test_data_retention_with_errors(self, test_db_session):
        """Test data retention service with error records."""
        # Create test errors with different ages
        now = datetime.utcnow()
        errors_data = [
            # Recent errors (within 30 days)
            (now - timedelta(days=5), 'Recent error 1', 'INFO'),
            (now - timedelta(days=15), 'Recent error 2', 'WARNING'),
            
            # Old errors (older than 30 days)
            (now - timedelta(days=35), 'Old error 1', 'ERROR'),
            (now - timedelta(days=45), 'Old error 2', 'CRITICAL'),
            (now - timedelta(days=60), 'Very old error', 'ERROR'),
        ]
        
        for timestamp, message, level in errors_data:
            error = Error(
                timestamp=timestamp,
                message=message,
                level=level,
                source='test'
            )
            test_db_session.add(error)
        
        test_db_session.commit()
        
        # Initialize data retention service
        config = TestingConfig()
        config.DATA_RETENTION_DAYS = 30
        retention_service = DataRetentionService(config)
        
        # Verify initial state
        initial_count = test_db_session.query(Error).count()
        assert initial_count == 5
        
        # Run data purging
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            stats = retention_service.purge_old_data()
        
        # Verify purging results
        remaining_count = test_db_session.query(Error).count()
        assert remaining_count == 2  # Only recent errors should remain
        assert stats['errors_purged'] == 3
        
        # Verify correct errors were kept
        remaining_errors = test_db_session.query(Error).all()
        for error in remaining_errors:
            days_old = (now - error.timestamp).days
            assert days_old <= 30
    
    def test_data_retention_statistics_accuracy(self, test_db_session):
        """Test accuracy of data retention statistics."""
        # Create test data with known quantities
        now = datetime.utcnow()
        
        # Create sensors
        for i in range(3):
            sensor = Sensor(
                sensor_id=f'STATS_SENSOR_{i:03d}',
                name=f'Stats Test Sensor {i}',
                active=True,
                min_temp=0.0,
                max_temp=50.0,
                min_humidity=0.0,
                max_humidity=100.0
            )
            test_db_session.add(sensor)
        
        # Create readings: 6 recent, 9 old
        for i in range(15):
            days_old = 25 if i < 6 else 35  # First 6 are recent, rest are old
            reading = SensorReading(
                sensor_id=f'STATS_SENSOR_{i % 3:03d}',
                timestamp=now - timedelta(days=days_old),
                temperature=20.0 + i,
                humidity=50.0 + i
            )
            test_db_session.add(reading)
        
        # Create errors: 3 recent, 5 old
        for i in range(8):
            days_old = 25 if i < 3 else 35  # First 3 are recent, rest are old
            error = Error(
                timestamp=now - timedelta(days=days_old),
                message=f'Test error {i}',
                level='INFO',
                source='test'
            )
            test_db_session.add(error)
        
        test_db_session.commit()
        
        # Initialize data retention service
        config = TestingConfig()
        config.DATA_RETENTION_DAYS = 30
        retention_service = DataRetentionService(config)
        
        # Run data purging
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            stats = retention_service.purge_old_data()
        
        # Verify statistics accuracy
        assert stats['readings_purged'] == 9
        assert stats['errors_purged'] == 5
        assert stats['total_purged'] == 14
        
        # Verify remaining counts
        remaining_readings = test_db_session.query(SensorReading).count()
        remaining_errors = test_db_session.query(Error).count()
        assert remaining_readings == 6
        assert remaining_errors == 3
    
    def test_data_retention_with_no_old_data(self, test_db_session):
        """Test data retention when no old data exists."""
        # Create only recent data
        now = datetime.utcnow()
        
        # Create sensor
        sensor = Sensor(
            sensor_id='NO_OLD_DATA_SENSOR',
            name='No Old Data Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        # Create only recent readings
        for i in range(5):
            reading = SensorReading(
                sensor_id='NO_OLD_DATA_SENSOR',
                timestamp=now - timedelta(days=i),  # 0-4 days old
                temperature=20.0 + i,
                humidity=50.0 + i
            )
            test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Initialize data retention service
        config = TestingConfig()
        config.DATA_RETENTION_DAYS = 30
        retention_service = DataRetentionService(config)
        
        # Run data purging
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            stats = retention_service.purge_old_data()
        
        # Verify no data was purged
        assert stats['readings_purged'] == 0
        assert stats['errors_purged'] == 0
        assert stats['total_purged'] == 0
        
        # Verify all data remains
        remaining_readings = test_db_session.query(SensorReading).count()
        assert remaining_readings == 5
    
    def test_data_retention_database_transaction_integrity(self, test_db_session):
        """Test that data retention operations maintain database transaction integrity."""
        # Create test data
        now = datetime.utcnow()
        
        sensor = Sensor(
            sensor_id='TRANSACTION_TEST_SENSOR',
            name='Transaction Test Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        # Create old readings
        for i in range(10):
            reading = SensorReading(
                sensor_id='TRANSACTION_TEST_SENSOR',
                timestamp=now - timedelta(days=35 + i),
                temperature=20.0 + i,
                humidity=50.0 + i
            )
            test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Initialize data retention service
        config = TestingConfig()
        config.DATA_RETENTION_DAYS = 30
        retention_service = DataRetentionService(config)
        
        # Mock database error during deletion
        original_delete = test_db_session.query(SensorReading).filter
        
        def mock_delete_with_error(*args, **kwargs):
            query = original_delete(*args, **kwargs)
            # Simulate error on delete operation
            original_delete_method = query.delete
            def error_delete(*args, **kwargs):
                if kwargs.get('synchronize_session', None) is not None:
                    raise Exception("Simulated database error")
                return original_delete_method(*args, **kwargs)
            query.delete = error_delete
            return query
        
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            # Patch the delete operation to simulate error
            with patch.object(test_db_session, 'query') as mock_query:
                mock_query.return_value.filter.return_value.delete.side_effect = Exception("Database error")
                
                # Run data purging - should handle error gracefully
                stats = retention_service.purge_old_data()
        
        # Verify error was handled and no partial deletion occurred
        remaining_readings = test_db_session.query(SensorReading).count()
        assert remaining_readings == 10  # All readings should still exist
        assert stats['readings_purged'] == 0
        assert stats['errors_purged'] == 0


@pytest.mark.integration
class TestDataRetentionServiceIntegration:
    """Test data retention service integration with other components."""
    
    def test_data_retention_service_initialization(self, test_db_session):
        """Test data retention service initialization with database."""
        config = TestingConfig()
        config.DATA_RETENTION_DAYS = 45
        
        retention_service = DataRetentionService(config)
        
        assert retention_service.retention_days == 45
        assert retention_service.config == config
    
    def test_data_retention_get_statistics_integration(self, test_db_session):
        """Test get_statistics method with real database."""
        # Create test data
        now = datetime.utcnow()
        
        # Create sensor
        sensor = Sensor(
            sensor_id='STATS_INTEGRATION_SENSOR',
            name='Stats Integration Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        # Create readings with different ages
        readings_data = [
            (now - timedelta(days=10), 20.0),  # Recent
            (now - timedelta(days=20), 21.0),  # Recent
            (now - timedelta(days=40), 18.0),  # Old
            (now - timedelta(days=50), 19.0),  # Old
        ]
        
        for timestamp, temp in readings_data:
            reading = SensorReading(
                sensor_id='STATS_INTEGRATION_SENSOR',
                timestamp=timestamp,
                temperature=temp,
                humidity=50.0
            )
            test_db_session.add(reading)
        
        # Create errors with different ages
        errors_data = [
            (now - timedelta(days=5), 'Recent error'),
            (now - timedelta(days=35), 'Old error'),
        ]
        
        for timestamp, message in errors_data:
            error = Error(
                timestamp=timestamp,
                message=message,
                level='INFO',
                source='test'
            )
            test_db_session.add(error)
        
        test_db_session.commit()
        
        # Initialize data retention service
        config = TestingConfig()
        config.DATA_RETENTION_DAYS = 30
        retention_service = DataRetentionService(config)
        
        # Get statistics
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            stats = retention_service.get_statistics()
        
        # Verify statistics
        assert stats['total_readings'] == 4
        assert stats['total_errors'] == 2
        assert stats['old_readings'] == 2
        assert stats['old_errors'] == 1
        assert stats['retention_days'] == 30
        assert 'cutoff_date' in stats
    
    def test_data_retention_with_different_retention_periods(self, test_db_session):
        """Test data retention with different retention periods."""
        # Create test data spanning different time periods
        now = datetime.utcnow()
        
        sensor = Sensor(
            sensor_id='PERIOD_TEST_SENSOR',
            name='Period Test Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        # Create readings at different ages
        readings_ages = [5, 15, 25, 35, 45, 65, 95]  # Days old
        for i, age in enumerate(readings_ages):
            reading = SensorReading(
                sensor_id='PERIOD_TEST_SENSOR',
                timestamp=now - timedelta(days=age),
                temperature=20.0 + i,
                humidity=50.0 + i
            )
            test_db_session.add(reading)
        
        test_db_session.commit()
        
        # Test with 30-day retention
        config_30 = TestingConfig()
        config_30.DATA_RETENTION_DAYS = 30
        retention_service_30 = DataRetentionService(config_30)
        
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            stats_30 = retention_service_30.get_statistics()
        
        assert stats_30['old_readings'] == 4  # Ages 35, 45, 65, 95
        
        # Test with 60-day retention
        config_60 = TestingConfig()
        config_60.DATA_RETENTION_DAYS = 60
        retention_service_60 = DataRetentionService(config_60)
        
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            stats_60 = retention_service_60.get_statistics()
        
        assert stats_60['old_readings'] == 2  # Ages 65, 95
    
    def test_data_retention_edge_cases(self, test_db_session):
        """Test data retention edge cases."""
        now = datetime.utcnow()
        
        # Create sensor
        sensor = Sensor(
            sensor_id='EDGE_CASE_SENSOR',
            name='Edge Case Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        # Create reading exactly at retention boundary
        config = TestingConfig()
        config.DATA_RETENTION_DAYS = 30
        
        boundary_time = now - timedelta(days=30)
        reading = SensorReading(
            sensor_id='EDGE_CASE_SENSOR',
            timestamp=boundary_time,
            temperature=20.0,
            humidity=50.0
        )
        test_db_session.add(reading)
        test_db_session.commit()
        
        retention_service = DataRetentionService(config)
        
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            stats = retention_service.get_statistics()
        
        # Reading exactly at boundary should be considered old
        assert stats['old_readings'] == 1
        
        # Test purging
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            purge_stats = retention_service.purge_old_data()
        
        assert purge_stats['readings_purged'] == 1
        
        # Verify reading was purged
        remaining_readings = test_db_session.query(SensorReading).count()
        assert remaining_readings == 0


@pytest.mark.integration
class TestDataRetentionErrorHandling:
    """Test error handling in data retention database integration."""
    
    def test_data_retention_database_connection_error(self):
        """Test data retention handling of database connection errors."""
        config = TestingConfig()
        retention_service = DataRetentionService(config)
        
        # Mock database connection error
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.side_effect = Exception("Database connection failed")
            
            # Should handle error gracefully
            stats = retention_service.get_statistics()
            
            # Should return empty stats on error
            assert stats['total_readings'] == 0
            assert stats['total_errors'] == 0
            assert stats['old_readings'] == 0
            assert stats['old_errors'] == 0
    
    def test_data_retention_purge_database_error(self):
        """Test data retention purge handling of database errors."""
        config = TestingConfig()
        retention_service = DataRetentionService(config)
        
        # Mock database error during purge
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock query to raise error
            mock_session.query.side_effect = Exception("Database query failed")
            
            # Should handle error gracefully
            stats = retention_service.purge_old_data()
            
            # Should return zero stats on error
            assert stats['readings_purged'] == 0
            assert stats['errors_purged'] == 0
            assert stats['total_purged'] == 0
    
    def test_data_retention_partial_failure_handling(self, test_db_session):
        """Test data retention handling of partial failures."""
        # Create test data
        now = datetime.utcnow()
        
        sensor = Sensor(
            sensor_id='PARTIAL_FAIL_SENSOR',
            name='Partial Fail Sensor',
            active=True,
            min_temp=0.0,
            max_temp=50.0,
            min_humidity=0.0,
            max_humidity=100.0
        )
        test_db_session.add(sensor)
        
        # Create old readings and errors
        for i in range(3):
            reading = SensorReading(
                sensor_id='PARTIAL_FAIL_SENSOR',
                timestamp=now - timedelta(days=35 + i),
                temperature=20.0 + i,
                humidity=50.0 + i
            )
            test_db_session.add(reading)
            
            error = Error(
                timestamp=now - timedelta(days=35 + i),
                message=f'Old error {i}',
                level='INFO',
                source='test'
            )
            test_db_session.add(error)
        
        test_db_session.commit()
        
        config = TestingConfig()
        retention_service = DataRetentionService(config)
        
        # Mock partial failure - readings succeed, errors fail
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_context.return_value.__enter__.return_value = test_db_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock error deletion to fail
            original_query = test_db_session.query
            def mock_query(model):
                query_result = original_query(model)
                if model == Error:
                    # Make error deletion fail
                    query_result.filter = Mock()
                    query_result.filter.return_value.delete = Mock(side_effect=Exception("Error deletion failed"))
                return query_result
            
            with patch.object(test_db_session, 'query', side_effect=mock_query):
                stats = retention_service.purge_old_data()
        
        # Should handle partial failure gracefully
        # Readings should be purged, errors should remain due to failure
        remaining_readings = test_db_session.query(SensorReading).count()
        remaining_errors = test_db_session.query(Error).count()
        
        assert remaining_readings == 0  # Readings were successfully purged
        assert remaining_errors == 3    # Errors remain due to failure
        assert stats['readings_purged'] == 3
        assert stats['errors_purged'] == 0  # Failed to purge errors