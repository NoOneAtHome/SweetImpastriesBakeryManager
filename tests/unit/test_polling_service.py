"""
Unit tests for the polling service module.

Tests polling logic, data processing, scheduler management, and error handling
in isolation using mocks.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call
from apscheduler.events import JobExecutionEvent

from polling_service import (
    PollingService,
    PollingServiceError,
    create_polling_service
)
from sensorpush_api import SensorPushAPIError, AuthenticationError, APIConnectionError
from data_retention import DataRetentionError
from config import TestingConfig


@pytest.mark.unit
class TestPollingServiceInitialization:
    """Test polling service initialization."""
    
    def test_init_with_default_config(self, mock_api_client):
        """Test polling service initialization with default config."""
        with patch('polling_service.Config') as mock_config:
            mock_config.DEFAULT_POLLING_INTERVAL = 5
            mock_config.validate_required_config.return_value = []
            
            service = PollingService(api_client=mock_api_client)
            
            assert service.config == mock_config
            assert service.api_client == mock_api_client
            assert service._is_running is False
            assert service._job_id == 'sensorpush_polling_job'
            assert service._purge_job_id == 'data_retention_purge_job'
    
    def test_init_with_custom_config(self, test_config, mock_api_client):
        """Test polling service initialization with custom config."""
        service = PollingService(config_class=test_config, api_client=mock_api_client)
        
        assert service.config == test_config
        assert service.api_client == mock_api_client
    
    def test_init_creates_api_client_if_not_provided(self, test_config):
        """Test that API client is created if not provided."""
        with patch('polling_service.SensorPushAPI') as mock_api_class:
            mock_api_instance = Mock()
            mock_api_class.return_value = mock_api_instance
            
            service = PollingService(config_class=test_config)
            
            assert service.api_client == mock_api_instance
            mock_api_class.assert_called_once_with(test_config)
    
    def test_init_sets_up_scheduler(self, test_config, mock_api_client):
        """Test that scheduler is properly set up during initialization."""
        with patch('polling_service.BackgroundScheduler') as mock_scheduler_class:
            mock_scheduler = Mock()
            mock_scheduler_class.return_value = mock_scheduler
            
            service = PollingService(config_class=test_config, api_client=mock_api_client)
            
            assert service.scheduler == mock_scheduler
            mock_scheduler.add_listener.assert_called_once()


@pytest.mark.unit
class TestPollingServiceJobListener:
    """Test polling service job event listener."""
    
    def test_job_listener_success(self, mock_polling_service):
        """Test job listener handling successful job execution."""
        service = mock_polling_service
        
        # Create mock event for successful job
        event = Mock(spec=JobExecutionEvent)
        event.job_id = service._job_id
        event.exception = None
        
        service._job_listener(event)
        
        assert service._successful_polls == 1
        assert service._failed_polls == 0
    
    def test_job_listener_failure(self, mock_polling_service):
        """Test job listener handling failed job execution."""
        service = mock_polling_service
        
        # Create mock event for failed job
        event = Mock(spec=JobExecutionEvent)
        event.job_id = service._job_id
        event.exception = Exception("Job failed")
        
        with patch('polling_service.handle_polling_error') as mock_handle_error:
            mock_handle_error.return_value = 'ERR-12345678'
            
            service._job_listener(event)
            
            assert service._successful_polls == 0
            assert service._failed_polls == 1
            mock_handle_error.assert_called_once_with(event.exception, f"APScheduler job execution ({service._job_id})")
    
    def test_job_listener_purge_job_success(self, mock_polling_service):
        """Test job listener handling successful purge job."""
        service = mock_polling_service
        
        event = Mock(spec=JobExecutionEvent)
        event.job_id = service._purge_job_id
        event.exception = None
        
        service._job_listener(event)
        
        assert service._successful_purges == 1
        assert service._failed_purges == 0
    
    def test_job_listener_purge_job_failure(self, mock_polling_service):
        """Test job listener handling failed purge job."""
        service = mock_polling_service
        
        event = Mock(spec=JobExecutionEvent)
        event.job_id = service._purge_job_id
        event.exception = Exception("Purge failed")
        
        with patch('polling_service.handle_polling_error') as mock_handle_error:
            mock_handle_error.return_value = 'ERR-87654321'
            
            service._job_listener(event)
            
            assert service._successful_purges == 0
            assert service._failed_purges == 1


@pytest.mark.unit
class TestPollingServiceMainJob:
    """Test the main polling job functionality."""
    
    def test_polling_job_success(self, mock_polling_service, mock_sensorpush_api_response, mock_sensorpush_status_response):
        """Test successful polling job execution."""
        service = mock_polling_service
        service.api_client.get_samples.return_value = mock_sensorpush_api_response
        service.api_client.get_status.return_value = mock_sensorpush_status_response
        
        with patch.object(service, '_process_samples_data') as mock_process_samples, \
             patch.object(service, '_process_status_data') as mock_process_status:
            
            service._polling_job()
            
            service.api_client.get_samples.assert_called_once()
            service.api_client.get_status.assert_called_once()
            mock_process_samples.assert_called_once_with(mock_sensorpush_api_response)
            mock_process_status.assert_called_once_with(mock_sensorpush_status_response)
            assert service._last_poll_time is not None
    
    def test_polling_job_samples_api_error(self, mock_polling_service):
        """Test polling job with samples API error."""
        service = mock_polling_service
        service.api_client.get_samples.side_effect = SensorPushAPIError("API error")
        
        with patch('polling_service.handle_polling_error') as mock_handle_error:
            mock_handle_error.return_value = 'ERR-12345678'
            
            with pytest.raises(SensorPushAPIError):
                service._polling_job()
            
            mock_handle_error.assert_called()
    
    def test_polling_job_samples_processing_error(self, mock_polling_service, mock_sensorpush_api_response):
        """Test polling job with samples processing error."""
        service = mock_polling_service
        service.api_client.get_samples.return_value = mock_sensorpush_api_response
        
        with patch.object(service, '_process_samples_data') as mock_process_samples, \
             patch('polling_service.handle_polling_error') as mock_handle_error:
            
            mock_process_samples.side_effect = Exception("Processing error")
            mock_handle_error.return_value = 'ERR-12345678'
            
            # Should not raise exception, should continue to status processing
            service._polling_job()
            
            mock_handle_error.assert_called()
            service.api_client.get_status.assert_called_once()
    
    def test_polling_job_authentication_error(self, mock_polling_service):
        """Test polling job with authentication error."""
        service = mock_polling_service
        service.api_client.get_samples.side_effect = AuthenticationError("Auth failed")
        
        with patch('polling_service.handle_polling_error') as mock_handle_error:
            mock_handle_error.return_value = 'ERR-12345678'
            
            # Should not raise exception for auth errors
            service._polling_job()
            
            mock_handle_error.assert_called()
    
    def test_polling_job_connection_error(self, mock_polling_service):
        """Test polling job with connection error."""
        service = mock_polling_service
        service.api_client.get_samples.side_effect = APIConnectionError("Connection failed")
        
        with patch('polling_service.handle_polling_error') as mock_handle_error:
            mock_handle_error.return_value = 'ERR-12345678'
            
            # Should not raise exception for connection errors
            service._polling_job()
            
            mock_handle_error.assert_called()
    
    def test_polling_job_unexpected_error(self, mock_polling_service):
        """Test polling job with unexpected error."""
        service = mock_polling_service
        service.api_client.get_samples.side_effect = ValueError("Unexpected error")
        
        with patch('polling_service.handle_polling_error') as mock_handle_error:
            mock_handle_error.return_value = 'ERR-12345678'
            
            # Should re-raise unexpected errors
            with pytest.raises(ValueError):
                service._polling_job()
            
            mock_handle_error.assert_called()


@pytest.mark.unit
class TestPollingServiceDataPurgeJob:
    """Test the data purge job functionality."""
    
    def test_data_purge_job_success(self, mock_polling_service):
        """Test successful data purge job execution."""
        service = mock_polling_service
        
        purge_result = {
            'success': True,
            'records_deleted': 100,
            'retention_months': 12,
            'cutoff_date': datetime.utcnow() - timedelta(days=365)
        }
        
        with patch('polling_service.purge_old_readings') as mock_purge:
            mock_purge.return_value = purge_result
            
            service._data_purge_job()
            
            mock_purge.assert_called_once_with(service.config)
            assert service._last_purge_time is not None
    
    def test_data_purge_job_failure(self, mock_polling_service):
        """Test data purge job with failure."""
        service = mock_polling_service
        
        purge_result = {
            'success': False,
            'records_deleted': 0,
            'retention_months': 12,
            'cutoff_date': datetime.utcnow() - timedelta(days=365),
            'error_message': 'Purge failed'
        }
        
        with patch('polling_service.purge_old_readings') as mock_purge:
            mock_purge.return_value = purge_result
            
            with pytest.raises(DataRetentionError):
                service._data_purge_job()
    
    def test_data_purge_job_exception(self, mock_polling_service):
        """Test data purge job with exception."""
        service = mock_polling_service
        
        with patch('polling_service.purge_old_readings') as mock_purge, \
             patch('polling_service.handle_polling_error') as mock_handle_error:
            
            mock_purge.side_effect = Exception("Unexpected error")
            mock_handle_error.return_value = 'ERR-12345678'
            
            with pytest.raises(Exception):
                service._data_purge_job()
            
            mock_handle_error.assert_called()


@pytest.mark.unit
class TestPollingServiceDataProcessing:
    """Test data processing methods."""
    
    def test_process_samples_data_success(self, mock_polling_service, mock_sensorpush_api_response):
        """Test successful samples data processing."""
        service = mock_polling_service
        
        with patch('polling_service.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock existing sensor query
            mock_session.query.return_value.filter.return_value.first.return_value = None
            
            service._process_samples_data(mock_sensorpush_api_response)
            
            # Verify session operations
            assert mock_session.add.call_count > 0  # Should add sensors and readings
            mock_session.commit.assert_called_once()
    
    def test_process_samples_data_with_existing_sensor(self, mock_polling_service, mock_sensorpush_api_response):
        """Test samples data processing with existing sensor."""
        service = mock_polling_service
        
        with patch('polling_service.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock existing sensor
            existing_sensor = Mock()
            mock_session.query.return_value.filter.return_value.first.return_value = existing_sensor
            
            # Mock duplicate reading check
            mock_session.query.return_value.filter.return_value.first.side_effect = [existing_sensor, None, None, None]
            
            service._process_samples_data(mock_sensorpush_api_response)
            
            mock_session.commit.assert_called_once()
    
    def test_process_samples_data_with_duplicate_readings(self, mock_polling_service, mock_sensorpush_api_response):
        """Test samples data processing with duplicate readings."""
        service = mock_polling_service
        
        with patch('polling_service.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock existing sensor and duplicate readings
            existing_sensor = Mock()
            duplicate_reading = Mock()
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                existing_sensor, duplicate_reading, duplicate_reading, duplicate_reading
            ]
            
            service._process_samples_data(mock_sensorpush_api_response)
            
            # Should still commit even with duplicates
            mock_session.commit.assert_called_once()
    
    def test_process_samples_data_invalid_reading_format(self, mock_polling_service):
        """Test samples data processing with invalid reading format."""
        service = mock_polling_service
        
        invalid_response = {
            'sensors': {
                'TEST_SENSOR_001': [
                    {
                        'observed': '2025-01-01T12:00:00Z',
                        'temperature': None,  # Invalid
                        'humidity': 45.0
                    }
                ]
            }
        }
        
        with patch('polling_service.get_db_session_context') as mock_context, \
             patch('polling_service.handle_polling_error') as mock_handle_error:
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.query.return_value.filter.return_value.first.return_value = None
            mock_handle_error.return_value = 'ERR-12345678'
            
            service._process_samples_data(invalid_response)
            
            # Should continue processing despite invalid readings
            mock_session.commit.assert_called_once()
    
    def test_process_samples_data_database_error(self, mock_polling_service, mock_sensorpush_api_response):
        """Test samples data processing with database error."""
        service = mock_polling_service
        
        with patch('polling_service.get_db_session_context') as mock_context, \
             patch('polling_service.handle_polling_error') as mock_handle_error:
            
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.commit.side_effect = Exception("Database error")
            mock_handle_error.return_value = 'ERR-12345678'
            
            with pytest.raises(Exception):
                service._process_samples_data(mock_sensorpush_api_response)
            
            mock_handle_error.assert_called()
    
    def test_process_status_data_success(self, mock_polling_service, mock_sensorpush_status_response):
        """Test successful status data processing."""
        service = mock_polling_service
        
        with patch('polling_service.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock existing sensor
            existing_sensor = Mock()
            existing_sensor.name = 'Old Name'
            existing_sensor.active = False
            mock_session.query.return_value.filter.return_value.first.return_value = existing_sensor
            
            service._process_status_data(mock_sensorpush_status_response)
            
            mock_session.commit.assert_called_once()
    
    def test_process_status_data_create_new_sensor(self, mock_polling_service, mock_sensorpush_status_response):
        """Test status data processing creating new sensor."""
        service = mock_polling_service
        
        with patch('polling_service.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            # Mock no existing sensor
            mock_session.query.return_value.filter.return_value.first.return_value = None
            
            service._process_status_data(mock_sensorpush_status_response)
            
            # Should add new sensors
            assert mock_session.add.call_count > 0
            mock_session.commit.assert_called_once()


@pytest.mark.unit
class TestPollingServiceControl:
    """Test polling service start/stop control."""
    
    def test_start_success(self, mock_polling_service):
        """Test successful service start."""
        service = mock_polling_service
        service.config.validate_required_config.return_value = []
        service.api_client.authenticate.return_value = True
        
        result = service.start()
        
        assert result is True
        assert service._is_running is True
        service.scheduler.add_job.assert_called()  # Should add jobs
        service.scheduler.start.assert_called_once()
    
    def test_start_already_running(self, mock_polling_service):
        """Test starting service when already running."""
        service = mock_polling_service
        service._is_running = True
        
        result = service.start()
        
        assert result is True
        service.scheduler.start.assert_not_called()
    
    def test_start_missing_config(self, mock_polling_service):
        """Test starting service with missing configuration."""
        service = mock_polling_service
        service.config.validate_required_config.return_value = ['MISSING_VAR']
        
        with pytest.raises(PollingServiceError, match="missing configuration"):
            service.start()
    
    def test_start_authentication_failure(self, mock_polling_service):
        """Test starting service with authentication failure."""
        service = mock_polling_service
        service.config.validate_required_config.return_value = []
        service.api_client.authenticate.return_value = False
        
        with pytest.raises(PollingServiceError, match="Failed to authenticate"):
            service.start()
    
    def test_start_api_connection_error(self, mock_polling_service):
        """Test starting service with API connection error."""
        service = mock_polling_service
        service.config.validate_required_config.return_value = []
        service.api_client.authenticate.side_effect = Exception("Connection failed")
        
        with patch('polling_service.handle_polling_error') as mock_handle_error:
            mock_handle_error.return_value = 'ERR-12345678'
            
            with pytest.raises(PollingServiceError, match="API connection test failed"):
                service.start()
    
    def test_stop_success(self, mock_polling_service):
        """Test successful service stop."""
        service = mock_polling_service
        service._is_running = True
        service.scheduler.get_job.return_value = Mock()  # Mock existing jobs
        
        result = service.stop()
        
        assert result is True
        assert service._is_running is False
        service.scheduler.remove_job.assert_called()  # Should remove jobs
        service.scheduler.shutdown.assert_called_once_with(wait=True)
    
    def test_stop_not_running(self, mock_polling_service):
        """Test stopping service when not running."""
        service = mock_polling_service
        service._is_running = False
        
        result = service.stop()
        
        assert result is True
        service.scheduler.shutdown.assert_not_called()
    
    def test_stop_error(self, mock_polling_service):
        """Test stopping service with error."""
        service = mock_polling_service
        service._is_running = True
        service.scheduler.shutdown.side_effect = Exception("Shutdown error")
        
        with patch('polling_service.handle_polling_error') as mock_handle_error:
            mock_handle_error.return_value = 'ERR-12345678'
            
            result = service.stop()
            
            assert result is False
    
    def test_is_running(self, mock_polling_service):
        """Test is_running method."""
        service = mock_polling_service
        service._is_running = True
        service.scheduler.running = True
        
        assert service.is_running() is True
        
        service._is_running = False
        assert service.is_running() is False
    
    def test_get_status(self, mock_polling_service):
        """Test get_status method."""
        service = mock_polling_service
        service._is_running = True
        service._last_poll_time = datetime.utcnow()
        service._successful_polls = 5
        service._failed_polls = 1
        
        status = service.get_status()
        
        assert status['is_running'] is True
        assert status['last_poll_time'] is not None
        assert status['successful_polls'] == 5
        assert status['failed_polls'] == 1


@pytest.mark.unit
class TestPollingServiceUtilityMethods:
    """Test utility methods of polling service."""
    
    def test_trigger_immediate_poll(self, mock_polling_service):
        """Test triggering immediate poll."""
        service = mock_polling_service
        service._is_running = True
        
        with patch.object(service, '_polling_job') as mock_polling_job:
            result = service.trigger_immediate_poll()
            
            assert result is True
            mock_polling_job.assert_called_once()
    
    def test_trigger_immediate_poll_not_running(self, mock_polling_service):
        """Test triggering immediate poll when service not running."""
        service = mock_polling_service
        service._is_running = False
        
        result = service.trigger_immediate_poll()
        
        assert result is False
    
    def test_trigger_immediate_purge(self, mock_polling_service):
        """Test triggering immediate purge."""
        service = mock_polling_service
        service._is_running = True
        
        with patch.object(service, '_data_purge_job') as mock_purge_job:
            result = service.trigger_immediate_purge()
            
            assert result is True
            mock_purge_job.assert_called_once()
    
    def test_update_polling_interval(self, mock_polling_service):
        """Test updating polling interval."""
        service = mock_polling_service
        service._is_running = True
        service.scheduler.get_job.return_value = Mock()
        
        result = service.update_polling_interval(10)
        
        assert result is True
        service.scheduler.remove_job.assert_called()
        service.scheduler.add_job.assert_called()
    
    def test_close(self, mock_polling_service):
        """Test closing the service."""
        service = mock_polling_service
        service._is_running = True
        
        with patch.object(service, 'stop') as mock_stop:
            service.close()
            
            mock_stop.assert_called_once()
            service.api_client.close.assert_called_once()


@pytest.mark.unit
def test_create_polling_service_function():
    """Test the create_polling_service convenience function."""
    test_config = TestingConfig
    
    with patch('polling_service.PollingService') as mock_service_class:
        mock_instance = Mock()
        mock_service_class.return_value = mock_instance
        
        result = create_polling_service(test_config, None)
        
        assert result == mock_instance
        mock_service_class.assert_called_once_with(test_config, None)


@pytest.mark.unit
class TestPollingServiceErrorScenarios:
    """Test various error scenarios."""
    
    def test_scheduler_initialization_error(self, test_config, mock_api_client):
        """Test error during scheduler initialization."""
        with patch('polling_service.BackgroundScheduler') as mock_scheduler_class:
            mock_scheduler_class.side_effect = Exception("Scheduler init failed")
            
            with pytest.raises(Exception):
                PollingService(config_class=test_config, api_client=mock_api_client)
    
    def test_job_addition_error(self, mock_polling_service):
        """Test error during job addition."""
        service = mock_polling_service
        service.config.validate_required_config.return_value = []
        service.api_client.authenticate.return_value = True
        service.scheduler.add_job.side_effect = Exception("Job addition failed")
        
        with pytest.raises(PollingServiceError):
            service.start()
    
    def test_unexpected_polling_error(self, mock_polling_service):
        """Test unexpected error during polling."""
        service = mock_polling_service
        
        with patch.object(service, '_process_samples_data') as mock_process:
            mock_process.side_effect = RuntimeError("Unexpected error")
            
            with patch('polling_service.handle_polling_error') as mock_handle_error:
                mock_handle_error.return_value = 'ERR-12345678'
                
                with pytest.raises(RuntimeError):
                    service._polling_job()