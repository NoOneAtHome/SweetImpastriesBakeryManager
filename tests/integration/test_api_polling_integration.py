"""
Integration tests for API client and polling service interaction.

Tests the integration between SensorPush API client and polling service,
verifying data flow and error handling across module boundaries.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from requests.exceptions import HTTPError, ConnectionError, Timeout

from sensorpush_api import SensorPushAPI, SensorPushAPIError, AuthenticationError, APIConnectionError
from polling_service import PollingService, PollingServiceError
from config import TestingConfig


@pytest.mark.integration
class TestAPIPollingIntegration:
    """Test integration between API client and polling service."""
    
    def test_polling_service_with_real_api_client(self, test_config, mock_sensorpush_api_response):
        """Test polling service using real API client with mocked HTTP responses."""
        with patch('sensorpush_api.requests.Session') as mock_session_class:
            # Setup mock session
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock authentication flow
            auth_response = Mock()
            auth_response.status_code = 200
            auth_response.json.return_value = {'authorization': 'test_auth_code'}
            auth_response.raise_for_status.return_value = None
            
            token_response = Mock()
            token_response.status_code = 200
            token_response.json.return_value = {'accesstoken': 'test_token', 'expires_in': 3600}
            token_response.raise_for_status.return_value = None
            
            # Mock samples API response
            samples_response = Mock()
            samples_response.status_code = 200
            samples_response.json.return_value = mock_sensorpush_api_response
            samples_response.raise_for_status.return_value = None
            
            # Configure session responses
            mock_session.post.side_effect = [auth_response, token_response]
            mock_session.request.return_value = samples_response
            
            # Create real API client and polling service
            api_client = SensorPushAPI(config_class=test_config)
            polling_service = PollingService(config_class=test_config, api_client=api_client)
            
            # Test authentication
            assert api_client.authenticate() is True
            assert api_client.is_token_valid() is True
            
            # Test data retrieval
            samples_data = api_client.get_samples()
            assert samples_data == mock_sensorpush_api_response
            
            # Test polling service can process the data
            with patch('polling_service.get_db_session_context') as mock_context:
                mock_session_db = Mock()
                mock_context.return_value.__enter__.return_value = mock_session_db
                mock_context.return_value.__exit__.return_value = None
                mock_session_db.query.return_value.filter.return_value.first.return_value = None
                
                polling_service._process_samples_data(samples_data)
                
                # Verify database operations
                assert mock_session_db.add.call_count > 0
                mock_session_db.commit.assert_called_once()
    
    def test_polling_service_handles_api_authentication_error(self, test_config):
        """Test polling service handling of API authentication errors."""
        with patch('sensorpush_api.requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock authentication failure
            auth_response = Mock()
            auth_response.status_code = 401
            error = HTTPError()
            error.response = auth_response
            auth_response.raise_for_status.side_effect = error
            mock_session.post.return_value = auth_response
            
            # Create API client and polling service
            api_client = SensorPushAPI(config_class=test_config)
            polling_service = PollingService(config_class=test_config, api_client=api_client)
            
            # Test that authentication error is properly handled
            with pytest.raises(AuthenticationError):
                api_client.authenticate()
            
            # Test that polling service handles auth errors gracefully
            with patch('polling_service.handle_polling_error') as mock_handle_error:
                mock_handle_error.return_value = 'ERR-12345678'
                
                # Should not raise exception, should handle gracefully
                polling_service._polling_job()
                
                mock_handle_error.assert_called()
    
    def test_polling_service_handles_api_connection_error(self, test_config):
        """Test polling service handling of API connection errors."""
        with patch('sensorpush_api.requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.post.side_effect = ConnectionError("Connection failed")
            
            # Create API client and polling service
            api_client = SensorPushAPI(config_class=test_config)
            polling_service = PollingService(config_class=test_config, api_client=api_client)
            
            # Test that connection error is properly handled
            with pytest.raises(APIConnectionError):
                api_client.authenticate()
            
            # Test that polling service handles connection errors gracefully
            with patch('polling_service.handle_polling_error') as mock_handle_error:
                mock_handle_error.return_value = 'ERR-12345678'
                
                # Should not raise exception, should handle gracefully
                polling_service._polling_job()
                
                mock_handle_error.assert_called()
    
    def test_polling_service_handles_api_timeout(self, test_config):
        """Test polling service handling of API timeouts."""
        with patch('sensorpush_api.requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.post.side_effect = Timeout("Request timeout")
            
            # Create API client and polling service
            api_client = SensorPushAPI(config_class=test_config)
            polling_service = PollingService(config_class=test_config, api_client=api_client)
            
            # Test that timeout error is properly handled
            with pytest.raises(APIConnectionError):
                api_client.authenticate()
            
            # Test that polling service handles timeouts gracefully
            with patch('polling_service.handle_polling_error') as mock_handle_error:
                mock_handle_error.return_value = 'ERR-12345678'
                
                # Should not raise exception, should handle gracefully
                polling_service._polling_job()
                
                mock_handle_error.assert_called()
    
    def test_polling_service_token_refresh_integration(self, test_config, mock_sensorpush_api_response):
        """Test polling service integration with token refresh."""
        with patch('sensorpush_api.requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock initial authentication
            auth_response = Mock()
            auth_response.status_code = 200
            auth_response.json.return_value = {'authorization': 'test_auth_code'}
            auth_response.raise_for_status.return_value = None
            
            token_response = Mock()
            token_response.status_code = 200
            token_response.json.return_value = {'accesstoken': 'test_token', 'expires_in': 3600}
            token_response.raise_for_status.return_value = None
            
            mock_session.post.side_effect = [auth_response, token_response]
            
            # Create API client
            api_client = SensorPushAPI(config_class=test_config)
            assert api_client.authenticate() is True
            
            # Simulate token expiration
            api_client._token_expires_at = datetime.now() - timedelta(minutes=10)
            assert api_client.is_token_valid() is False
            
            # Mock token refresh
            auth_response2 = Mock()
            auth_response2.status_code = 200
            auth_response2.json.return_value = {'authorization': 'new_auth_code'}
            auth_response2.raise_for_status.return_value = None
            
            token_response2 = Mock()
            token_response2.status_code = 200
            token_response2.json.return_value = {'accesstoken': 'new_token', 'expires_in': 3600}
            token_response2.raise_for_status.return_value = None
            
            mock_session.post.side_effect = [auth_response2, token_response2]
            
            # Test that ensure_valid_token refreshes the token
            assert api_client.ensure_valid_token() is True
            assert api_client.is_token_valid() is True
            assert api_client._access_token == 'new_token'
    
    def test_polling_service_data_processing_integration(self, test_config, mock_sensorpush_api_response):
        """Test end-to-end data processing from API to database."""
        with patch('sensorpush_api.requests.Session') as mock_session_class, \
             patch('polling_service.get_db_session_context') as mock_context:
            
            # Setup API mocks
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            auth_response = Mock()
            auth_response.status_code = 200
            auth_response.json.return_value = {'authorization': 'test_auth_code'}
            auth_response.raise_for_status.return_value = None
            
            token_response = Mock()
            token_response.status_code = 200
            token_response.json.return_value = {'accesstoken': 'test_token', 'expires_in': 3600}
            token_response.raise_for_status.return_value = None
            
            samples_response = Mock()
            samples_response.status_code = 200
            samples_response.json.return_value = mock_sensorpush_api_response
            samples_response.raise_for_status.return_value = None
            
            mock_session.post.side_effect = [auth_response, token_response]
            mock_session.request.return_value = samples_response
            
            # Setup database mocks
            mock_session_db = Mock()
            mock_context.return_value.__enter__.return_value = mock_session_db
            mock_context.return_value.__exit__.return_value = None
            mock_session_db.query.return_value.filter.return_value.first.return_value = None
            
            # Create services
            api_client = SensorPushAPI(config_class=test_config)
            polling_service = PollingService(config_class=test_config, api_client=api_client)
            
            # Authenticate
            assert api_client.authenticate() is True
            
            # Execute polling job
            polling_service._polling_job()
            
            # Verify API was called
            assert mock_session.request.called
            
            # Verify database operations
            assert mock_session_db.add.call_count > 0
            mock_session_db.commit.assert_called()
    
    def test_polling_service_error_propagation(self, test_config):
        """Test error propagation from API client to polling service."""
        with patch('sensorpush_api.requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock successful authentication
            auth_response = Mock()
            auth_response.status_code = 200
            auth_response.json.return_value = {'authorization': 'test_auth_code'}
            auth_response.raise_for_status.return_value = None
            
            token_response = Mock()
            token_response.status_code = 200
            token_response.json.return_value = {'accesstoken': 'test_token', 'expires_in': 3600}
            token_response.raise_for_status.return_value = None
            
            mock_session.post.side_effect = [auth_response, token_response]
            
            # Mock API error during samples request
            samples_response = Mock()
            samples_response.status_code = 500
            error = HTTPError()
            error.response = samples_response
            samples_response.raise_for_status.side_effect = error
            mock_session.request.return_value = samples_response
            
            # Create services
            api_client = SensorPushAPI(config_class=test_config)
            polling_service = PollingService(config_class=test_config, api_client=api_client)
            
            # Authenticate
            assert api_client.authenticate() is True
            
            # Test that API error is properly caught and handled by polling service
            with patch('polling_service.handle_polling_error') as mock_handle_error:
                mock_handle_error.return_value = 'ERR-12345678'
                
                # Should handle the error gracefully
                with pytest.raises(SensorPushAPIError):
                    polling_service._polling_job()
                
                mock_handle_error.assert_called()


@pytest.mark.integration
class TestAPIPollingServiceStartup:
    """Test integration during polling service startup."""
    
    def test_polling_service_startup_with_api_validation(self, test_config):
        """Test polling service startup validates API connection."""
        with patch('sensorpush_api.requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock successful authentication
            auth_response = Mock()
            auth_response.status_code = 200
            auth_response.json.return_value = {'authorization': 'test_auth_code'}
            auth_response.raise_for_status.return_value = None
            
            token_response = Mock()
            token_response.status_code = 200
            token_response.json.return_value = {'accesstoken': 'test_token', 'expires_in': 3600}
            token_response.raise_for_status.return_value = None
            
            mock_session.post.side_effect = [auth_response, token_response]
            
            # Create services
            api_client = SensorPushAPI(config_class=test_config)
            polling_service = PollingService(config_class=test_config, api_client=api_client)
            
            # Mock scheduler
            with patch.object(polling_service, 'scheduler') as mock_scheduler:
                mock_scheduler.add_job.return_value = None
                mock_scheduler.start.return_value = None
                
                # Test startup
                result = polling_service.start()
                
                assert result is True
                assert polling_service._is_running is True
                mock_scheduler.start.assert_called_once()
    
    def test_polling_service_startup_fails_with_api_error(self, test_config):
        """Test polling service startup fails when API connection fails."""
        with patch('sensorpush_api.requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            mock_session.post.side_effect = ConnectionError("Connection failed")
            
            # Create services
            api_client = SensorPushAPI(config_class=test_config)
            polling_service = PollingService(config_class=test_config, api_client=api_client)
            
            # Test startup failure
            with patch('polling_service.handle_polling_error') as mock_handle_error:
                mock_handle_error.return_value = 'ERR-12345678'
                
                with pytest.raises(PollingServiceError, match="API connection test failed"):
                    polling_service.start()
                
                assert polling_service._is_running is False
    
    def test_polling_service_configuration_validation_integration(self, test_config):
        """Test integration of configuration validation across modules."""
        # Test with missing configuration
        test_config.SENSORPUSH_USERNAME = None
        test_config.SENSORPUSH_PASSWORD = None
        
        with patch.object(test_config, 'validate_required_config') as mock_validate:
            mock_validate.return_value = ['SENSORPUSH_USERNAME', 'SENSORPUSH_PASSWORD']
            
            # Create services
            api_client = SensorPushAPI(config_class=test_config)
            polling_service = PollingService(config_class=test_config, api_client=api_client)
            
            # Test startup failure due to missing config
            with pytest.raises(PollingServiceError, match="missing configuration"):
                polling_service.start()


@pytest.mark.integration
class TestAPIPollingRealWorldScenarios:
    """Test real-world integration scenarios."""
    
    def test_polling_service_handles_intermittent_api_failures(self, test_config, mock_sensorpush_api_response):
        """Test polling service handling intermittent API failures."""
        with patch('sensorpush_api.requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock authentication
            auth_response = Mock()
            auth_response.status_code = 200
            auth_response.json.return_value = {'authorization': 'test_auth_code'}
            auth_response.raise_for_status.return_value = None
            
            token_response = Mock()
            token_response.status_code = 200
            token_response.json.return_value = {'accesstoken': 'test_token', 'expires_in': 3600}
            token_response.raise_for_status.return_value = None
            
            mock_session.post.side_effect = [auth_response, token_response]
            
            # Create services
            api_client = SensorPushAPI(config_class=test_config)
            polling_service = PollingService(config_class=test_config, api_client=api_client)
            
            # Authenticate
            assert api_client.authenticate() is True
            
            # Test sequence: success, failure, success
            success_response = Mock()
            success_response.status_code = 200
            success_response.json.return_value = mock_sensorpush_api_response
            success_response.raise_for_status.return_value = None
            
            failure_response = Mock()
            failure_response.status_code = 500
            error = HTTPError()
            error.response = failure_response
            failure_response.raise_for_status.side_effect = error
            
            mock_session.request.side_effect = [success_response, failure_response, success_response]
            
            with patch('polling_service.get_db_session_context') as mock_context, \
                 patch('polling_service.handle_polling_error') as mock_handle_error:
                
                mock_session_db = Mock()
                mock_context.return_value.__enter__.return_value = mock_session_db
                mock_context.return_value.__exit__.return_value = None
                mock_session_db.query.return_value.filter.return_value.first.return_value = None
                mock_handle_error.return_value = 'ERR-12345678'
                
                # First call should succeed
                polling_service._polling_job()
                assert mock_session_db.commit.call_count == 1
                
                # Second call should fail but be handled gracefully
                with pytest.raises(SensorPushAPIError):
                    polling_service._polling_job()
                
                # Third call should succeed again
                polling_service._polling_job()
                assert mock_session_db.commit.call_count == 2
    
    def test_polling_service_handles_malformed_api_responses(self, test_config):
        """Test polling service handling malformed API responses."""
        with patch('sensorpush_api.requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock authentication
            auth_response = Mock()
            auth_response.status_code = 200
            auth_response.json.return_value = {'authorization': 'test_auth_code'}
            auth_response.raise_for_status.return_value = None
            
            token_response = Mock()
            token_response.status_code = 200
            token_response.json.return_value = {'accesstoken': 'test_token', 'expires_in': 3600}
            token_response.raise_for_status.return_value = None
            
            mock_session.post.side_effect = [auth_response, token_response]
            
            # Mock malformed response
            malformed_response = Mock()
            malformed_response.status_code = 200
            malformed_response.json.return_value = "invalid json structure"  # Should be dict
            malformed_response.raise_for_status.return_value = None
            
            mock_session.request.return_value = malformed_response
            
            # Create services
            api_client = SensorPushAPI(config_class=test_config)
            polling_service = PollingService(config_class=test_config, api_client=api_client)
            
            # Authenticate
            assert api_client.authenticate() is True
            
            # Test that malformed response is handled
            with patch('polling_service.handle_polling_error') as mock_handle_error:
                mock_handle_error.return_value = 'ERR-12345678'
                
                with pytest.raises(SensorPushAPIError):
                    polling_service._polling_job()
                
                mock_handle_error.assert_called()
    
    def test_polling_service_large_dataset_handling(self, test_config):
        """Test polling service handling large datasets from API."""
        # Create large mock response
        large_response = {
            'sensors': {}
        }
        
        # Generate 100 sensors with 10 readings each
        for i in range(100):
            sensor_id = f'SENSOR_{i:03d}'
            readings = []
            for j in range(10):
                readings.append({
                    'observed': f'2025-01-01T{j:02d}:00:00Z',
                    'temperature': 20.0 + i + j * 0.1,
                    'humidity': 50.0 + i + j * 0.1
                })
            large_response['sensors'][sensor_id] = readings
        
        with patch('sensorpush_api.requests.Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock authentication
            auth_response = Mock()
            auth_response.status_code = 200
            auth_response.json.return_value = {'authorization': 'test_auth_code'}
            auth_response.raise_for_status.return_value = None
            
            token_response = Mock()
            token_response.status_code = 200
            token_response.json.return_value = {'accesstoken': 'test_token', 'expires_in': 3600}
            token_response.raise_for_status.return_value = None
            
            mock_session.post.side_effect = [auth_response, token_response]
            
            # Mock large response
            samples_response = Mock()
            samples_response.status_code = 200
            samples_response.json.return_value = large_response
            samples_response.raise_for_status.return_value = None
            
            mock_session.request.return_value = samples_response
            
            # Create services
            api_client = SensorPushAPI(config_class=test_config)
            polling_service = PollingService(config_class=test_config, api_client=api_client)
            
            # Authenticate
            assert api_client.authenticate() is True
            
            # Test processing large dataset
            with patch('polling_service.get_db_session_context') as mock_context:
                mock_session_db = Mock()
                mock_context.return_value.__enter__.return_value = mock_session_db
                mock_context.return_value.__exit__.return_value = None
                mock_session_db.query.return_value.filter.return_value.first.return_value = None
                
                polling_service._polling_job()
                
                # Should handle large dataset without issues
                assert mock_session_db.add.call_count >= 100  # At least 100 sensors
                mock_session_db.commit.assert_called()