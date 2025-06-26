"""
Unit tests for the data retention module.

Tests data purging logic, retention statistics, and configuration validation
in isolation using mocks.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.exc import SQLAlchemyError

from data_retention import (
    DataRetentionError,
    DataRetentionService,
    purge_old_readings,
    get_data_retention_stats,
    validate_retention_config
)
from config import TestingConfig


@pytest.mark.unit
class TestPurgeOldReadings:
    """Test the purge_old_readings function."""
    
    def test_purge_old_readings_success(self, test_config):
        """Test successful purging of old readings."""
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock query results
            mock_session.query.return_value.filter.return_value.count.return_value = 50
            mock_session.query.return_value.filter.return_value.delete.return_value = 50
            
            result = purge_old_readings(test_config)
            
            assert result['success'] is True
            assert result['records_deleted'] == 50
            assert result['retention_months'] >= 6  # Should enforce minimum
            assert result['error_message'] is None
            mock_session.commit.assert_called_once()
    
    def test_purge_old_readings_no_records_to_delete(self, test_config):
        """Test purging when no old records exist."""
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock no records to delete
            mock_session.query.return_value.filter.return_value.count.return_value = 0
            
            result = purge_old_readings(test_config)
            
            assert result['success'] is True
            assert result['records_deleted'] == 0
            assert result['error_message'] is None
            # Should not call delete or commit if no records
            mock_session.commit.assert_not_called()
    
    def test_purge_old_readings_minimum_retention_enforced(self):
        """Test that minimum 6-month retention is enforced."""
        # Create config with low retention
        with patch('data_retention.Config') as mock_config:
            mock_config.DATA_RETENTION_MONTHS = 3  # Below minimum
            
            with patch('data_retention.get_db_session_context') as mock_context:
                mock_session = Mock()
                mock_context.return_value.__enter__.return_value = mock_session
                mock_context.return_value.__exit__.return_value = None
                mock_session.query.return_value.filter.return_value.count.return_value = 0
                
                result = purge_old_readings(mock_config)
                
                # Should use 6 months instead of 3
                assert result['retention_months'] == 6
    
    def test_purge_old_readings_high_retention_allowed(self):
        """Test that high retention values are allowed."""
        with patch('data_retention.Config') as mock_config:
            mock_config.DATA_RETENTION_MONTHS = 24  # 2 years
            
            with patch('data_retention.get_db_session_context') as mock_context:
                mock_session = Mock()
                mock_context.return_value.__enter__.return_value = mock_session
                mock_context.return_value.__exit__.return_value = None
                mock_session.query.return_value.filter.return_value.count.return_value = 0
                
                result = purge_old_readings(mock_config)
                
                assert result['retention_months'] == 24
    
    def test_purge_old_readings_database_error(self, test_config):
        """Test purging with database error."""
        with patch('data_retention.get_db_session_context') as mock_context, \
             patch('data_retention.handle_polling_error') as mock_handle_error:
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.query.side_effect = SQLAlchemyError("Database error")
            mock_handle_error.return_value = 'ERR-12345678'
            
            result = purge_old_readings(test_config)
            
            assert result['success'] is False
            assert result['records_deleted'] == 0
            assert 'Database error' in result['error_message']
            mock_handle_error.assert_called_once()
    
    def test_purge_old_readings_unexpected_error(self, test_config):
        """Test purging with unexpected error."""
        with patch('data_retention.get_db_session_context') as mock_context, \
             patch('data_retention.handle_polling_error') as mock_handle_error:
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.query.side_effect = ValueError("Unexpected error")
            mock_handle_error.return_value = 'ERR-87654321'
            
            result = purge_old_readings(test_config)
            
            assert result['success'] is False
            assert result['records_deleted'] == 0
            assert 'Unexpected error' in result['error_message']
            mock_handle_error.assert_called_once()
    
    def test_purge_old_readings_cutoff_date_calculation(self, test_config):
        """Test that cutoff date is calculated correctly."""
        test_config.DATA_RETENTION_MONTHS = 12
        
        with patch('data_retention.get_db_session_context') as mock_context, \
             patch('data_retention.datetime') as mock_datetime:
            
            # Mock current time
            mock_now = datetime(2025, 6, 25, 12, 0, 0)
            mock_datetime.utcnow.return_value = mock_now
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.query.return_value.filter.return_value.count.return_value = 0
            
            result = purge_old_readings(test_config)
            
            # Cutoff should be approximately 12 months ago
            expected_cutoff = mock_now - timedelta(days=12 * 30)
            assert abs((result['cutoff_date'] - expected_cutoff).total_seconds()) < 60  # Within 1 minute


@pytest.mark.unit
class TestGetDataRetentionStats:
    """Test the get_data_retention_stats function."""
    
    def test_get_data_retention_stats_success(self, test_config):
        """Test successful retrieval of retention statistics."""
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock query results
            mock_session.query.return_value.scalar.side_effect = [
                1000,  # total records
                datetime(2024, 1, 1),  # oldest record
                datetime(2025, 6, 25)  # newest record
            ]
            mock_session.query.return_value.filter.return_value.count.return_value = 100  # eligible for purge
            
            result = get_data_retention_stats(test_config)
            
            assert result['total_records'] == 1000
            assert result['oldest_record_date'] == datetime(2024, 1, 1)
            assert result['newest_record_date'] == datetime(2025, 6, 25)
            assert result['records_eligible_for_purge'] == 100
            assert result['retention_months'] == test_config.DATA_RETENTION_MONTHS
            assert result['effective_retention_months'] >= 6
    
    def test_get_data_retention_stats_empty_database(self, test_config):
        """Test statistics with empty database."""
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock empty database
            mock_session.query.return_value.scalar.side_effect = [0, None, None]
            mock_session.query.return_value.filter.return_value.count.return_value = 0
            
            result = get_data_retention_stats(test_config)
            
            assert result['total_records'] == 0
            assert result['oldest_record_date'] is None
            assert result['newest_record_date'] is None
            assert result['records_eligible_for_purge'] == 0
    
    def test_get_data_retention_stats_minimum_retention_enforced(self):
        """Test that minimum retention is enforced in statistics."""
        with patch('data_retention.Config') as mock_config:
            mock_config.DATA_RETENTION_MONTHS = 3  # Below minimum
            
            with patch('data_retention.get_db_session_context') as mock_context:
                mock_session = Mock()
                mock_context.return_value.__enter__.return_value = mock_session
                mock_context.return_value.__exit__.return_value = None
                mock_session.query.return_value.scalar.side_effect = [0, None, None]
                mock_session.query.return_value.filter.return_value.count.return_value = 0
                
                result = get_data_retention_stats(mock_config)
                
                assert result['retention_months'] == 3  # Original config value
                assert result['effective_retention_months'] == 6  # Enforced minimum
        with patch('data_retention.Config') as mock_config:
            mock_config.DATA_RETENTION_MONTHS = 3  # Below minimum
            
            with patch('data_retention.get_db_session_context') as mock_context:
                mock_session = Mock()
                mock_context.return_value.__enter__.return_value = mock_session
                mock_context.return_value.__exit__.return_value = None
                mock_session.query.return_value.scalar.side_effect = [0, None, None]
                mock_session.query.return_value.filter.return_value.count.return_value = 0
                
                result = get_data_retention_stats(mock_config)
                
                assert result['retention_months'] == 3  # Original config value
                assert result['effective_retention_months'] == 6  # Enforced minimum
    
    def test_get_data_retention_stats_database_error(self, test_config):
        """Test statistics with database error."""
        with patch('data_retention.get_db_session_context') as mock_context, \
             patch('data_retention.handle_polling_error') as mock_handle_error:
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.query.side_effect = SQLAlchemyError("Database error")
            mock_handle_error.return_value = 'ERR-12345678'
            
            with pytest.raises(DataRetentionError, match="Failed to get retention stats"):
                get_data_retention_stats(test_config)
            
            mock_handle_error.assert_called_once()
    
    def test_get_data_retention_stats_unexpected_error(self, test_config):
        """Test statistics with unexpected error."""
        with patch('data_retention.get_db_session_context') as mock_context, \
             patch('data_retention.handle_polling_error') as mock_handle_error:
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.query.side_effect = ValueError("Unexpected error")
            mock_handle_error.return_value = 'ERR-87654321'
            
            with pytest.raises(DataRetentionError, match="Failed to get retention stats"):
                get_data_retention_stats(test_config)
            
            mock_handle_error.assert_called_once()


@pytest.mark.unit
class TestValidateRetentionConfig:
    """Test the validate_retention_config function."""
    
    def test_validate_retention_config_valid_config(self):
        """Test validation with valid configuration."""
        with patch('data_retention.Config') as mock_config:
            mock_config.DATA_RETENTION_MONTHS = 12
            
            result = validate_retention_config(mock_config)
            
            assert result['is_valid'] is True
            assert result['configured_months'] == 12
            assert result['effective_months'] == 12
            assert len(result['warnings']) == 0
    
    def test_validate_retention_config_below_minimum(self):
        """Test validation with below minimum configuration."""
        with patch('data_retention.Config') as mock_config:
            mock_config.DATA_RETENTION_MONTHS = 3
            
            result = validate_retention_config(mock_config)
            
            assert result['is_valid'] is True  # Still valid due to enforcement
            assert result['configured_months'] == 3
            assert result['effective_months'] == 6
            assert len(result['warnings']) == 1
            assert 'below minimum' in result['warnings'][0]
    
    def test_validate_retention_config_very_high(self):
        """Test validation with very high configuration."""
        with patch('data_retention.Config') as mock_config:
            mock_config.DATA_RETENTION_MONTHS = 72  # 6 years
            
            result = validate_retention_config(mock_config)
            
            assert result['is_valid'] is True
            assert result['configured_months'] == 72
            assert result['effective_months'] == 72
            assert len(result['warnings']) == 1
            assert 'very high' in result['warnings'][0]
    
    def test_validate_retention_config_at_minimum(self):
        """Test validation with exactly minimum configuration."""
        with patch('data_retention.Config') as mock_config:
            mock_config.DATA_RETENTION_MONTHS = 6
            
            result = validate_retention_config(mock_config)
            
            assert result['is_valid'] is True
            assert result['configured_months'] == 6
            assert result['effective_months'] == 6
            assert len(result['warnings']) == 0
    
    def test_validate_retention_config_at_warning_threshold(self):
        """Test validation at the high warning threshold."""
        with patch('data_retention.Config') as mock_config:
            mock_config.DATA_RETENTION_MONTHS = 60  # Exactly at threshold
            
            result = validate_retention_config(mock_config)
            
            assert result['is_valid'] is True
            assert result['configured_months'] == 60
            assert result['effective_months'] == 60
            assert len(result['warnings']) == 0  # Should not warn at exactly 60
    
    def test_validate_retention_config_just_above_threshold(self):
        """Test validation just above the high warning threshold."""
        with patch('data_retention.Config') as mock_config:
            mock_config.DATA_RETENTION_MONTHS = 61  # Just above threshold
            
            result = validate_retention_config(mock_config)
            
            assert result['is_valid'] is True
            assert result['configured_months'] == 61
            assert result['effective_months'] == 61
            assert len(result['warnings']) == 1
            assert 'very high' in result['warnings'][0]
    
    def test_validate_retention_config_multiple_warnings(self):
        """Test validation that could trigger multiple warnings (edge case)."""
        # This is more of a theoretical test since current logic doesn't
        # have overlapping warning conditions, but tests the structure
        with patch('data_retention.Config') as mock_config:
            mock_config.DATA_RETENTION_MONTHS = 1  # Below minimum
            
            result = validate_retention_config(mock_config)
            
            assert result['is_valid'] is True
            assert len(result['warnings']) == 1  # Only one warning for below minimum


@pytest.mark.unit
class TestDataRetentionErrorHandling:
    """Test error handling in data retention module."""
    
    def test_data_retention_error_inheritance(self):
        """Test that DataRetentionError is a proper exception."""
        error = DataRetentionError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"
    
    def test_purge_old_readings_with_commit_error(self, test_config):
        """Test purging when commit fails."""
        with patch('data_retention.get_db_session_context') as mock_context, \
             patch('data_retention.handle_polling_error') as mock_handle_error:
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock successful count and delete, but failed commit
            mock_session.query.return_value.filter.return_value.count.return_value = 10
            mock_session.query.return_value.filter.return_value.delete.return_value = 10
            mock_session.commit.side_effect = SQLAlchemyError("Commit failed")
            mock_handle_error.return_value = 'ERR-12345678'
            
            result = purge_old_readings(test_config)
            
            assert result['success'] is False
            assert 'Database error' in result['error_message']
    
    def test_get_data_retention_stats_partial_failure(self, test_config):
        """Test statistics when some queries fail."""
        with patch('data_retention.get_db_session_context') as mock_context, \
             patch('data_retention.handle_polling_error') as mock_handle_error:
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # First query succeeds, second fails
            mock_session.query.return_value.scalar.side_effect = [1000, SQLAlchemyError("Query failed")]
            mock_handle_error.return_value = 'ERR-12345678'
            
            with pytest.raises(DataRetentionError):
                get_data_retention_stats(test_config)


@pytest.mark.unit
class TestDataRetentionUtilityFunctions:
    """Test utility aspects of data retention module."""
    
    def test_cutoff_date_calculation_precision(self):
        """Test that cutoff date calculation is precise."""
        from data_retention import datetime, timedelta
        
        # Test with known values
        retention_months = 12
        test_time = datetime(2025, 6, 25, 15, 30, 45)
        
        with patch('data_retention.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = test_time
            
            # Calculate expected cutoff
            expected_cutoff = test_time - timedelta(days=retention_months * 30)
            
            with patch('data_retention.get_db_session_context') as mock_context:
                mock_session = Mock()
                mock_context.return_value.__enter__.return_value = mock_session
                mock_context.return_value.__exit__.return_value = None
                mock_session.query.return_value.filter.return_value.count.return_value = 0
                
                result = purge_old_readings()
                
                # Should be exactly the expected cutoff
                assert result['cutoff_date'] == expected_cutoff
    
    def test_retention_months_boundary_conditions(self):
        """Test boundary conditions for retention months."""
        test_cases = [
            (0, 6),    # Zero should become 6
            (1, 6),    # Below minimum should become 6
            (5, 6),    # Just below minimum should become 6
            (6, 6),    # Exactly minimum should stay 6
            (7, 7),    # Above minimum should stay as-is
            (100, 100) # Very high should stay as-is
        ]
        
        for input_months, expected_months in test_cases:
            with patch('data_retention.Config') as mock_config:
                mock_config.DATA_RETENTION_MONTHS = input_months
                
                with patch('data_retention.get_db_session_context') as mock_context:
                    mock_session = Mock()
                    mock_context.return_value.__enter__.return_value = mock_session
                    mock_context.return_value.__exit__.return_value = None
                    mock_session.query.return_value.filter.return_value.count.return_value = 0
                    
                    result = purge_old_readings(mock_config)
                    
                    assert result['retention_months'] == expected_months, \
                        f"Input {input_months} should result in {expected_months}, got {result['retention_months']}"
    
    def test_default_config_usage(self):
        """Test that functions use default config when none provided."""
        with patch('data_retention.Config') as mock_default_config:
            mock_default_config.DATA_RETENTION_MONTHS = 12
            
            with patch('data_retention.get_db_session_context') as mock_context:
                mock_session = Mock()
                mock_context.return_value.__enter__.return_value = mock_session
                mock_context.return_value.__exit__.return_value = None
                mock_session.query.return_value.filter.return_value.count.return_value = 0
                
                # Call without config parameter
                result = purge_old_readings()
                
                assert result['retention_months'] == 12
            
            # Test stats function
            with patch('data_retention.get_db_session_context') as mock_context:
                mock_session = Mock()
                mock_context.return_value.__enter__.return_value = mock_session
                mock_context.return_value.__exit__.return_value = None
                mock_session.query.return_value.scalar.side_effect = [0, None, None]
                mock_session.query.return_value.filter.return_value.count.return_value = 0
                
                result = get_data_retention_stats()
                
                assert result['retention_months'] == 12
            
            # Test validation function
            result = validate_retention_config()
            
            assert result['configured_months'] == 12
@pytest.mark.unit
class TestDataRetentionService:
    """Test the DataRetentionService class."""
    
    def test_service_initialization_default_config(self):
        """Test service initialization with default config."""
        service = DataRetentionService()
        assert service.config is not None
        assert hasattr(service, 'logger')
    
    def test_service_initialization_custom_config(self, test_config):
        """Test service initialization with custom config."""
        service = DataRetentionService(test_config)
        assert service.config == test_config
    
    def test_service_purge_old_readings_delegation(self, test_config):
        """Test that service purge method delegates to module function."""
        with patch('data_retention.purge_old_readings') as mock_purge:
            mock_purge.return_value = {'success': True, 'records_deleted': 10}
            
            service = DataRetentionService(test_config)
            result = service.purge_old_readings()
            
            mock_purge.assert_called_once_with(test_config)
            assert result['success'] is True
            assert result['records_deleted'] == 10
    
    def test_service_get_retention_stats_delegation(self, test_config):
        """Test that service stats method delegates to module function."""
        with patch('data_retention.get_data_retention_stats') as mock_stats:
            mock_stats.return_value = {'total_records': 100}
            
            service = DataRetentionService(test_config)
            result = service.get_retention_stats()
            
            mock_stats.assert_called_once_with(test_config)
            assert result['total_records'] == 100
    
    def test_service_validate_config_delegation(self, test_config):
        """Test that service validation method delegates to module function."""
        with patch('data_retention.validate_retention_config') as mock_validate:
            mock_validate.return_value = {'is_valid': True}
            
            service = DataRetentionService(test_config)
            result = service.validate_config()
            
            mock_validate.assert_called_once_with(test_config)
            assert result['is_valid'] is True
    
    def test_delete_readings_by_sensor_success(self, test_config):
        """Test successful deletion of readings by sensor ID."""
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock query chain
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.count.return_value = 25
            mock_query.delete.return_value = 25
            
            service = DataRetentionService(test_config)
            result = service.delete_readings_by_sensor('sensor123')
            
            assert result['success'] is True
            assert result['records_deleted'] == 25
            assert result['sensor_id'] == 'sensor123'
            assert result['error_message'] is None
            mock_session.commit.assert_called_once()
    
    def test_delete_readings_by_sensor_with_date_range(self, test_config):
        """Test deletion of readings by sensor with date range."""
        start_date = datetime(2025, 1, 1)
        end_date = datetime(2025, 6, 1)
        
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.count.return_value = 15
            mock_query.delete.return_value = 15
            
            service = DataRetentionService(test_config)
            result = service.delete_readings_by_sensor('sensor123', start_date, end_date)
            
            assert result['success'] is True
            assert result['records_deleted'] == 15
            assert result['sensor_id'] == 'sensor123'
            assert result['date_range']['start_date'] == start_date
            assert result['date_range']['end_date'] == end_date
    
    def test_delete_readings_by_sensor_no_records(self, test_config):
        """Test deletion when no records match criteria."""
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.count.return_value = 0
            
            service = DataRetentionService(test_config)
            result = service.delete_readings_by_sensor('sensor123')
            
            assert result['success'] is True
            assert result['records_deleted'] == 0
            mock_session.commit.assert_not_called()
    
    def test_delete_readings_by_sensor_database_error(self, test_config):
        """Test deletion with database error."""
        with patch('data_retention.get_db_session_context') as mock_context, \
             patch('data_retention.handle_polling_error') as mock_handle_error:
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.query.side_effect = SQLAlchemyError("Database error")
            mock_handle_error.return_value = 'ERR-12345678'
            
            service = DataRetentionService(test_config)
            result = service.delete_readings_by_sensor('sensor123')
            
            assert result['success'] is False
            assert result['records_deleted'] == 0
            assert 'Database error' in result['error_message']
    
    def test_delete_readings_by_date_range_success(self, test_config):
        """Test successful deletion by date range."""
        start_date = datetime(2025, 1, 1)
        end_date = datetime(2025, 6, 1)
        
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.count.return_value = 50
            mock_query.delete.return_value = 50
            
            service = DataRetentionService(test_config)
            result = service.delete_readings_by_date_range(start_date, end_date)
            
            assert result['success'] is True
            assert result['records_deleted'] == 50
            assert result['date_range']['start_date'] == start_date
            assert result['date_range']['end_date'] == end_date
            assert result['sensor_ids'] is None
    
    def test_delete_readings_by_date_range_with_sensor_filter(self, test_config):
        """Test deletion by date range with sensor ID filter."""
        start_date = datetime(2025, 1, 1)
        end_date = datetime(2025, 6, 1)
        sensor_ids = ['sensor1', 'sensor2']
        
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.count.return_value = 30
            mock_query.delete.return_value = 30
            
            service = DataRetentionService(test_config)
            result = service.delete_readings_by_date_range(start_date, end_date, sensor_ids)
            
            assert result['success'] is True
            assert result['records_deleted'] == 30
            assert result['sensor_ids'] == sensor_ids
    
    def test_delete_readings_by_date_range_no_records(self, test_config):
        """Test date range deletion when no records match."""
        start_date = datetime(2025, 1, 1)
        end_date = datetime(2025, 6, 1)
        
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.count.return_value = 0
            
            service = DataRetentionService(test_config)
            result = service.delete_readings_by_date_range(start_date, end_date)
            
            assert result['success'] is True
            assert result['records_deleted'] == 0
            mock_session.commit.assert_not_called()
    
    def test_delete_readings_by_date_range_database_error(self, test_config):
        """Test date range deletion with database error."""
        start_date = datetime(2025, 1, 1)
        end_date = datetime(2025, 6, 1)
        
        with patch('data_retention.get_db_session_context') as mock_context, \
             patch('data_retention.handle_polling_error') as mock_handle_error:
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.query.side_effect = SQLAlchemyError("Database error")
            mock_handle_error.return_value = 'ERR-12345678'
            
            service = DataRetentionService(test_config)
            result = service.delete_readings_by_date_range(start_date, end_date)
            
            assert result['success'] is False
            assert result['records_deleted'] == 0
            assert 'Database error' in result['error_message']
    
    def test_get_sensor_data_summary_success(self, test_config):
        """Test successful retrieval of sensor data summary."""
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock query results
            oldest_date = datetime(2024, 1, 1)
            newest_date = datetime(2025, 6, 25)
            mock_session.query.return_value.filter.return_value.scalar.side_effect = [
                100,  # total records
                oldest_date,  # oldest record
                newest_date   # newest record
            ]
            
            service = DataRetentionService(test_config)
            result = service.get_sensor_data_summary('sensor123')
            
            assert result['sensor_id'] == 'sensor123'
            assert result['total_records'] == 100
            assert result['oldest_record_date'] == oldest_date
            assert result['newest_record_date'] == newest_date
            assert result['date_range_days'] == (newest_date - oldest_date).days
    
    def test_get_sensor_data_summary_empty_sensor(self, test_config):
        """Test sensor summary for sensor with no data."""
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            mock_session.query.return_value.filter.return_value.scalar.side_effect = [0, None, None]
            
            service = DataRetentionService(test_config)
            result = service.get_sensor_data_summary('sensor123')
            
            assert result['sensor_id'] == 'sensor123'
            assert result['total_records'] == 0
            assert result['oldest_record_date'] is None
            assert result['newest_record_date'] is None
            assert result['date_range_days'] == 0
    
    def test_get_sensor_data_summary_database_error(self, test_config):
        """Test sensor summary with database error."""
        with patch('data_retention.get_db_session_context') as mock_context, \
             patch('data_retention.handle_polling_error') as mock_handle_error:
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.query.side_effect = SQLAlchemyError("Database error")
            mock_handle_error.return_value = 'ERR-12345678'
            
            service = DataRetentionService(test_config)
            
            with pytest.raises(DataRetentionError, match="Failed to get sensor summary"):
                service.get_sensor_data_summary('sensor123')
    
    def test_get_sensor_data_summary_unexpected_error(self, test_config):
        """Test sensor summary with unexpected error."""
        with patch('data_retention.get_db_session_context') as mock_context, \
             patch('data_retention.handle_polling_error') as mock_handle_error:
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.query.side_effect = ValueError("Unexpected error")
            mock_handle_error.return_value = 'ERR-87654321'
            
            service = DataRetentionService(test_config)
            
            with pytest.raises(DataRetentionError, match="Failed to get sensor summary"):
                service.get_sensor_data_summary('sensor123')


@pytest.mark.unit
class TestDataRetentionServiceIntegration:
    """Test integration scenarios for DataRetentionService."""
    
    def test_service_workflow_purge_then_stats(self, test_config):
        """Test typical workflow: purge old data then get stats."""
        with patch('data_retention.purge_old_readings') as mock_purge, \
             patch('data_retention.get_data_retention_stats') as mock_stats:
            
            mock_purge.return_value = {'success': True, 'records_deleted': 50}
            mock_stats.return_value = {'total_records': 950, 'records_eligible_for_purge': 0}
            
            service = DataRetentionService(test_config)
            
            # First purge old data
            purge_result = service.purge_old_readings()
            assert purge_result['success'] is True
            assert purge_result['records_deleted'] == 50
            
            # Then get updated stats
            stats_result = service.get_retention_stats()
            assert stats_result['total_records'] == 950
            assert stats_result['records_eligible_for_purge'] == 0
    
    def test_service_on_demand_deletion_workflow(self, test_config):
        """Test on-demand deletion workflow."""
        with patch('data_retention.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock different query results for different calls
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            
            # First call: delete by sensor
            mock_query.count.return_value = 20
            mock_query.delete.return_value = 20
            
            service = DataRetentionService(test_config)
            
            # Delete specific sensor data
            result = service.delete_readings_by_sensor('old_sensor')
            assert result['success'] is True
            assert result['records_deleted'] == 20
            
            # Reset mocks for second call
            mock_query.reset_mock()
            mock_query.count.return_value = 100
            mock_query.delete.return_value = 100
            
            # Delete by date range
            start_date = datetime(2024, 1, 1)
            end_date = datetime(2024, 12, 31)
            result = service.delete_readings_by_date_range(start_date, end_date)
            assert result['success'] is True
            assert result['records_deleted'] == 100