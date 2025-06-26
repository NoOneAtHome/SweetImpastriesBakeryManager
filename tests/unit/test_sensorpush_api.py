"""
Unit tests for the SensorPush API module.

Tests authentication, token management, API calls, and error handling
in isolation using mocks.
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from requests.exceptions import HTTPError, ConnectionError, Timeout, RequestException

from sensorpush_api import (
    SensorPushAPI, 
    SensorPushAPIError, 
    AuthenticationError, 
    TokenExpiredError, 
    APIConnectionError,
    create_api_client
)
from config import TestingConfig


@pytest.mark.unit
class TestSensorPushAPI:
    """Test cases for SensorPushAPI class."""
    
    def test_init_with_default_config(self):
        """Test API client initialization with default config."""
        with patch('sensorpush_api.Config') as mock_config:
            mock_config.SENSORPUSH_USERNAME = 'test@example.com'
            mock_config.SENSORPUSH_PASSWORD = 'password'
            mock_config.SENSORPUSH_API_BASE_URL = 'https://api.test.com'
            mock_config.validate_required_config.return_value = []
            
            api = SensorPushAPI()
            
            assert api.config == mock_config
            assert api.base_url == 'https://api.test.com'
            assert api.auth_endpoint == 'https://api.test.com/oauth/authorize'
            assert api.token_endpoint == 'https://api.test.com/oauth/accesstoken'
    
    def test_init_with_custom_config(self, test_config):
        """Test API client initialization with custom config."""
        api = SensorPushAPI(config_class=test_config)
        
        assert api.config == test_config
        assert api.base_url == test_config.SENSORPUSH_API_BASE_URL
    
    def test_init_missing_config_raises_error(self):
        """Test that missing configuration raises AuthenticationError."""
        with patch('sensorpush_api.Config') as mock_config:
            mock_config.validate_required_config.return_value = ['SENSORPUSH_USERNAME']
            
            with pytest.raises(AuthenticationError, match="Missing required configuration"):
                SensorPushAPI()
    
    def test_authenticate_success(self, test_config):
        """Test successful authentication flow."""
        api = SensorPushAPI(config_class=test_config)
        
        # Mock the session.post calls
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {'authorization': 'test_auth_code'}
        auth_response.raise_for_status.return_value = None
        
        token_response = Mock()
        token_response.status_code = 200
        token_response.json.return_value = {'accesstoken': 'test_token', 'expires_in': 3600}
        token_response.raise_for_status.return_value = None
        
        api.session.post.side_effect = [auth_response, token_response]
        
        result = api.authenticate()
        
        assert result is True
        assert api._access_token == 'test_token'
        assert api._token_expires_at is not None
        assert api.session.post.call_count == 2
    
    def test_authenticate_invalid_credentials(self, test_config):
        """Test authentication with invalid credentials."""
        api = SensorPushAPI(config_class=test_config)
        
        # Mock 401 response
        auth_response = Mock()
        auth_response.status_code = 401
        error = HTTPError()
        error.response = auth_response
        auth_response.raise_for_status.side_effect = error
        
        api.session.post.return_value = auth_response
        
        with pytest.raises(AuthenticationError, match="Invalid username or password"):
            api.authenticate()
    
    def test_authenticate_connection_error(self, test_config):
        """Test authentication with connection error."""
        api = SensorPushAPI(config_class=test_config)
        
        api.session.post.side_effect = ConnectionError("Connection failed")
        
        with pytest.raises(APIConnectionError, match="Connection error"):
            api.authenticate()
    
    def test_authenticate_timeout_error(self, test_config):
        """Test authentication with timeout error."""
        api = SensorPushAPI(config_class=test_config)
        
        api.session.post.side_effect = Timeout("Request timeout")
        
        with pytest.raises(APIConnectionError, match="Request timeout"):
            api.authenticate()
    
    def test_authenticate_invalid_response_format(self, test_config):
        """Test authentication with invalid response format."""
        api = SensorPushAPI(config_class=test_config)
        
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {'invalid': 'response'}
        auth_response.raise_for_status.return_value = None
        
        api.session.post.return_value = auth_response
        
        with pytest.raises(AuthenticationError, match="Invalid authentication response format"):
            api.authenticate()
    
    def test_authenticate_json_decode_error(self, test_config):
        """Test authentication with JSON decode error."""
        api = SensorPushAPI(config_class=test_config)
        
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        auth_response.raise_for_status.return_value = None
        
        api.session.post.return_value = auth_response
        
        with pytest.raises(AuthenticationError, match="Invalid JSON response"):
            api.authenticate()
    
    def test_token_exchange_failure(self, test_config):
        """Test token exchange failure."""
        api = SensorPushAPI(config_class=test_config)
        
        # Mock successful auth but failed token exchange
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json.return_value = {'authorization': 'test_auth_code'}
        auth_response.raise_for_status.return_value = None
        
        token_response = Mock()
        token_response.status_code = 400
        error = HTTPError()
        error.response = token_response
        token_response.raise_for_status.side_effect = error
        
        api.session.post.side_effect = [auth_response, token_response]
        
        with pytest.raises(AuthenticationError, match="Token exchange failed"):
            api.authenticate()
    
    def test_is_token_valid_no_token(self, test_config):
        """Test token validation with no token."""
        api = SensorPushAPI(config_class=test_config)
        
        assert api.is_token_valid() is False
    
    def test_is_token_valid_expired_token(self, test_config):
        """Test token validation with expired token."""
        api = SensorPushAPI(config_class=test_config)
        api._access_token = 'test_token'
        api._token_expires_at = datetime.now() - timedelta(minutes=10)  # Expired
        
        assert api.is_token_valid() is False
    
    def test_is_token_valid_expiring_soon(self, test_config):
        """Test token validation with token expiring soon."""
        api = SensorPushAPI(config_class=test_config)
        api._access_token = 'test_token'
        api._token_expires_at = datetime.now() + timedelta(minutes=2)  # Expires in 2 minutes
        
        assert api.is_token_valid() is False  # Should be False due to 5-minute buffer
    
    def test_is_token_valid_good_token(self, test_config):
        """Test token validation with valid token."""
        api = SensorPushAPI(config_class=test_config)
        api._access_token = 'test_token'
        api._token_expires_at = datetime.now() + timedelta(hours=1)  # Valid for 1 hour
        
        assert api.is_token_valid() is True
    
    def test_ensure_valid_token_with_valid_token(self, test_config):
        """Test ensure_valid_token with already valid token."""
        api = SensorPushAPI(config_class=test_config)
        api._access_token = 'test_token'
        api._token_expires_at = datetime.now() + timedelta(hours=1)
        
        result = api.ensure_valid_token()
        
        assert result is True
    
    def test_ensure_valid_token_refresh_needed(self, test_config):
        """Test ensure_valid_token when refresh is needed."""
        api = SensorPushAPI(config_class=test_config)
        
        # Mock authentication for refresh
        with patch.object(api, 'authenticate', return_value=True) as mock_auth:
            result = api.ensure_valid_token()
            
            assert result is True
            mock_auth.assert_called_once()
    
    def test_get_auth_headers_success(self, test_config):
        """Test getting authentication headers."""
        api = SensorPushAPI(config_class=test_config)
        api._access_token = 'test_token'
        api._token_expires_at = datetime.now() + timedelta(hours=1)
        
        headers = api.get_auth_headers()
        
        assert headers == {'Authorization': 'Bearer test_token'}
    
    def test_get_auth_headers_no_token(self, test_config):
        """Test getting authentication headers with no valid token."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'ensure_valid_token', return_value=False):
            with pytest.raises(AuthenticationError, match="Unable to obtain valid access token"):
                api.get_auth_headers()
    
    def test_make_authenticated_request_success(self, test_config):
        """Test successful authenticated request."""
        api = SensorPushAPI(config_class=test_config)
        api._access_token = 'test_token'
        api._token_expires_at = datetime.now() + timedelta(hours=1)
        
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        api.session.request.return_value = mock_response
        
        response = api.make_authenticated_request('GET', 'test/endpoint')
        
        assert response == mock_response
        api.session.request.assert_called_once()
    
    def test_make_authenticated_request_token_expired(self, test_config):
        """Test authenticated request with expired token."""
        api = SensorPushAPI(config_class=test_config)
        api._access_token = 'test_token'
        api._token_expires_at = datetime.now() + timedelta(hours=1)
        
        # Mock 401 response
        mock_response = Mock()
        mock_response.status_code = 401
        api.session.request.return_value = mock_response
        
        with pytest.raises(TokenExpiredError, match="Access token expired"):
            api.make_authenticated_request('GET', 'test/endpoint')
        
        # Token should be cleared
        assert api._access_token is None
    
    def test_make_authenticated_request_connection_error(self, test_config):
        """Test authenticated request with connection error."""
        api = SensorPushAPI(config_class=test_config)
        api._access_token = 'test_token'
        api._token_expires_at = datetime.now() + timedelta(hours=1)
        
        api.session.request.side_effect = ConnectionError("Connection failed")
        
        with pytest.raises(APIConnectionError, match="Connection error"):
            api.make_authenticated_request('GET', 'test/endpoint')
    
    def test_get_samples_success(self, test_config, mock_sensorpush_api_response):
        """Test successful get_samples call."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'make_authenticated_request') as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = mock_sensorpush_api_response
            mock_request.return_value = mock_response
            
            result = api.get_samples()
            
            assert result == mock_sensorpush_api_response
            mock_request.assert_called_once_with(
                method='POST',
                endpoint='samples',
                json={}
            )
    
    def test_get_samples_with_parameters(self, test_config):
        """Test get_samples with parameters."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'make_authenticated_request') as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = {'sensors': {}}
            mock_request.return_value = mock_response
            
            params = {
                'limit': 100,
                'startTime': '2025-01-01T00:00:00Z',
                'sensors': ['sensor1', 'sensor2']
            }
            
            api.get_samples(**params)
            
            mock_request.assert_called_once_with(
                method='POST',
                endpoint='samples',
                json=params
            )
    
    def test_get_samples_http_error(self, test_config):
        """Test get_samples with HTTP error."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'make_authenticated_request') as mock_request:
            error = HTTPError()
            error.response = Mock()
            error.response.status_code = 400
            mock_request.side_effect = error
            
            with pytest.raises(SensorPushAPIError, match="Bad request"):
                api.get_samples()
    
    def test_get_samples_invalid_response(self, test_config):
        """Test get_samples with invalid response format."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'make_authenticated_request') as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = "invalid response"  # Should be dict
            mock_request.return_value = mock_response
            
            with pytest.raises(SensorPushAPIError, match="Invalid samples response format"):
                api.get_samples()
    
    def test_get_status_success(self, test_config, mock_sensorpush_status_response):
        """Test successful get_status call."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'make_authenticated_request') as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = mock_sensorpush_status_response
            mock_request.return_value = mock_response
            
            result = api.get_status()
            
            assert result == mock_sensorpush_status_response
            mock_request.assert_called_once_with(
                method='GET',
                endpoint='status'
            )
    
    def test_get_status_with_parameters(self, test_config):
        """Test get_status with parameters."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'make_authenticated_request') as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = {}
            mock_request.return_value = mock_response
            
            params = {'sensors': ['sensor1', 'sensor2']}
            
            api.get_status(**params)
            
            mock_request.assert_called_once_with(
                method='GET',
                endpoint='status'
            )
    
    def test_get_token_info(self, test_config):
        """Test get_token_info method."""
        api = SensorPushAPI(config_class=test_config)
        api._access_token = 'test_token'
        api._token_expires_at = datetime.now() + timedelta(hours=1)
        
        token_info = api.get_token_info()
        
        assert token_info['has_token'] is True
        assert token_info['is_valid'] is True
        assert token_info['token_type'] == 'Bearer'
        assert 'expires_at' in token_info
    
    def test_clear_token(self, test_config):
        """Test clear_token method."""
        api = SensorPushAPI(config_class=test_config)
        api._access_token = 'test_token'
        api._token_expires_at = datetime.now() + timedelta(hours=1)
        
        api.clear_token()
        
        assert api._access_token is None
        assert api._token_expires_at is None
    
    def test_close(self, test_config):
        """Test close method."""
        api = SensorPushAPI(config_class=test_config)
        api._access_token = 'test_token'
        
        with patch.object(api.session, 'close') as mock_close:
            api.close()
            
            mock_close.assert_called_once()
            assert api._access_token is None


@pytest.mark.unit
class TestSensorPushAPIErrorHandling:
    """Test error handling scenarios for SensorPush API."""
    
    def test_authentication_error_inheritance(self):
        """Test that AuthenticationError inherits from SensorPushAPIError."""
        error = AuthenticationError("Test error")
        assert isinstance(error, SensorPushAPIError)
    
    def test_token_expired_error_inheritance(self):
        """Test that TokenExpiredError inherits from SensorPushAPIError."""
        error = TokenExpiredError("Test error")
        assert isinstance(error, SensorPushAPIError)
    
    def test_api_connection_error_inheritance(self):
        """Test that APIConnectionError inherits from SensorPushAPIError."""
        error = APIConnectionError("Test error")
        assert isinstance(error, SensorPushAPIError)
    
    def test_network_error_handling(self, test_config):
        """Test handling of various network errors."""
        api = SensorPushAPI(config_class=test_config)
        
        # Test different network errors
        network_errors = [
            ConnectionError("Connection failed"),
            Timeout("Request timeout"),
            RequestException("General request error")
        ]
        
        for error in network_errors:
            api.session.post.side_effect = error
            
            with pytest.raises(APIConnectionError):
                api.authenticate()


@pytest.mark.unit
def test_create_api_client_function():
    """Test the create_api_client convenience function."""
    with patch('sensorpush_api.SensorPushAPI') as mock_api_class:
        mock_instance = Mock()
        mock_api_class.return_value = mock_instance
        
        result = create_api_client()
        
        assert result == mock_instance
        mock_api_class.assert_called_once_with(None)


@pytest.mark.unit
def test_create_api_client_with_config():
    """Test create_api_client with custom config."""
    test_config = TestingConfig
    
    with patch('sensorpush_api.SensorPushAPI') as mock_api_class:
        mock_instance = Mock()
        mock_api_class.return_value = mock_instance
        
        result = create_api_client(test_config)
        
        assert result == mock_instance
        mock_api_class.assert_called_once_with(test_config)


@pytest.mark.unit
class TestSensorPushAPIEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_samples_response(self, test_config):
        """Test handling of empty samples response."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'make_authenticated_request') as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = {'sensors': {}}
            mock_request.return_value = mock_response
            
            result = api.get_samples()
            
            assert result == {'sensors': {}}
    
    def test_malformed_json_response(self, test_config):
        """Test handling of malformed JSON response."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'make_authenticated_request') as mock_request:
            mock_response = Mock()
            mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
            mock_request.return_value = mock_response
            
            with pytest.raises(SensorPushAPIError, match="Invalid JSON response"):
                api.get_samples()
    
    def test_server_error_response(self, test_config):
        """Test handling of server error responses."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'make_authenticated_request') as mock_request:
            error = HTTPError()
            error.response = Mock()
            error.response.status_code = 500
            mock_request.side_effect = error
            
            with pytest.raises(SensorPushAPIError, match="Server error"):
                api.get_samples()
    
    def test_forbidden_response(self, test_config):
        """Test handling of forbidden responses."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'make_authenticated_request') as mock_request:
            error = HTTPError()
            error.response = Mock()
            error.response.status_code = 403
            mock_request.side_effect = error
            
            with pytest.raises(SensorPushAPIError, match="Forbidden"):
                api.get_samples()
    
    def test_not_found_response(self, test_config):
        """Test handling of not found responses."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'make_authenticated_request') as mock_request:
            error = HTTPError()
            error.response = Mock()
            error.response.status_code = 404
            mock_request.side_effect = error
            
            with pytest.raises(SensorPushAPIError, match="endpoint not found"):
                api.get_samples()
    
    def test_unexpected_exception_handling(self, test_config):
        """Test handling of unexpected exceptions."""
        api = SensorPushAPI(config_class=test_config)
        
        with patch.object(api, 'make_authenticated_request') as mock_request:
            mock_request.side_effect = ValueError("Unexpected error")
            
            with pytest.raises(SensorPushAPIError, match="Unexpected error"):
                api.get_samples()