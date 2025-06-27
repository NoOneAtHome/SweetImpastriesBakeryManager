"""
SensorPush API Authentication and Token Management Module.

This module provides authentication and token management functionality for the SensorPush API,
including OAuth token retrieval, secure storage, expiration checking, and automatic refresh.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import requests
from requests.exceptions import RequestException, HTTPError, ConnectionError, Timeout

from config import Config


class SensorPushAPIError(Exception):
    """Base exception for SensorPush API errors."""
    pass


class AuthenticationError(SensorPushAPIError):
    """Raised when authentication fails."""
    pass


class TokenExpiredError(SensorPushAPIError):
    """Raised when the access token has expired."""
    pass


class APIConnectionError(SensorPushAPIError):
    """Raised when there are connection issues with the API."""
    pass


class SensorPushAPI:
    """
    SensorPush API client with authentication and token management.
    
    This class handles OAuth authentication, token storage in memory,
    automatic token refresh, and provides a foundation for API interactions.
    """
    
    def __init__(self, config_class=None):
        """
        Initialize the SensorPush API client.
        
        Args:
            config_class: Configuration class to use (defaults to Config)
        """
        self.config = config_class # Always use the provided config_class
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"SensorPushAPI received config_class: {config_class.__name__ if config_class else 'None'}")
        self.logger.info(f"SensorPushAPI initialized with SENSORPUSH_USERNAME: {self.config.SENSORPUSH_USERNAME}")
        self.logger.info(f"SensorPushAPI initialized with SENSORPUSH_PASSWORD: {self.config.SENSORPUSH_PASSWORD}")
        
        # API endpoints
        self.base_url = self.config.SENSORPUSH_API_BASE_URL
        self.auth_endpoint = f"{self.base_url}/oauth/authorize"
        self.token_endpoint = f"{self.base_url}/oauth/accesstoken"
        
        # Token storage (in-memory)
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._token_type: str = "Bearer"
        
        # Request session for connection pooling and performance
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'SensorDashboard/1.0'
        })
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self):
        """Validate that required configuration is present."""
        missing_vars = self.config.validate_required_config()
        if missing_vars:
            self.logger.error(f"Configuration validation failed: Missing variables: {', '.join(missing_vars)}")
            raise AuthenticationError(
                f"Missing required configuration variables: {', '.join(missing_vars)}"
            )
        self.logger.info("Configuration validated successfully.")
    
    def authenticate(self) -> bool:
        """
        Authenticate with the SensorPush API and obtain an access token.
        
        Returns:
            bool: True if authentication successful, False otherwise
            
        Raises:
            AuthenticationError: If authentication fails
            APIConnectionError: If there are connection issues
        """
        try:
            self.logger.info("Attempting to authenticate with SensorPush API")
            
            # Prepare authentication request
            auth_data = {
                "email": self.config.SENSORPUSH_USERNAME, # Use the config_class's attribute
                "password": self.config.SENSORPUSH_PASSWORD # Use the config_class's attribute
            }
            
            # Make authentication request
            response = self.session.post(
                self.auth_endpoint,
                json=auth_data,
                timeout=30
            )
            
            # Check for HTTP errors
            response.raise_for_status()
            
            # Parse response
            auth_response = response.json()
            
            # Validate response structure
            if 'authorization' not in auth_response:
                raise AuthenticationError("Invalid authentication response format")
            
            # Extract authorization token (it's directly a string, not nested)
            auth_code = auth_response['authorization']
            if not auth_code:
                raise AuthenticationError("No authorization code received")
            
            # Exchange authorization code for access token
            return self._exchange_auth_code_for_token(auth_code)
            
        except HTTPError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid username or password")
            elif e.response.status_code == 403:
                raise AuthenticationError("Account access forbidden")
            else:
                raise AuthenticationError(f"HTTP error during authentication: {e}")
        except ConnectionError as e:
            raise APIConnectionError(f"Connection error: {e}")
        except Timeout as e:
            raise APIConnectionError(f"Request timeout: {e}")
        except RequestException as e:
            raise APIConnectionError(f"Request error: {e}")
        except json.JSONDecodeError as e:
            raise AuthenticationError(f"Invalid JSON response: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during authentication: {e}")
            raise AuthenticationError(f"Unexpected authentication error: {e}")
    
    def _exchange_auth_code_for_token(self, auth_code: str) -> bool:
        """
        Exchange authorization code for access token.
        
        Args:
            auth_code: Authorization code from initial authentication
            
        Returns:
            bool: True if token exchange successful
            
        Raises:
            AuthenticationError: If token exchange fails
        """
        try:
            self.logger.debug("Exchanging authorization code for access token")
            
            # Prepare token request
            token_data = {
                "authorization": auth_code
            }
            
            # Make token request
            response = self.session.post(
                self.token_endpoint,
                json=token_data,
                timeout=30
            )
            
            # Check for HTTP errors
            response.raise_for_status()
            
            # Parse response
            token_response = response.json()
            
            # Extract token information
            access_token = token_response.get('accesstoken')
            if not access_token:
                raise AuthenticationError("No access token received")
            
            # Store token information
            self._access_token = access_token
            
            # Calculate token expiration (SensorPush tokens typically last 24 hours)
            # If no expiration is provided, assume 23 hours for safety
            expires_in = token_response.get('expires_in', 23 * 3600)  # Default to 23 hours
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            self.logger.info(f"Successfully obtained access token, expires at: {self._token_expires_at}")
            return True
            
        except HTTPError as e:
            raise AuthenticationError(f"Token exchange failed: {e}")
        except json.JSONDecodeError as e:
            raise AuthenticationError(f"Invalid token response: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during token exchange: {e}")
            raise AuthenticationError(f"Token exchange error: {e}")
    
    def is_token_valid(self) -> bool:
        """
        Check if the current access token is valid and not expired.
        
        Returns:
            bool: True if token is valid and not expired
        """
        if not self._access_token:
            return False
        
        if not self._token_expires_at:
            return False
        
        # Check if token expires within the next 5 minutes (buffer for safety)
        buffer_time = datetime.now() + timedelta(minutes=5)
        return self._token_expires_at > buffer_time
    
    def ensure_valid_token(self) -> bool:
        """
        Ensure we have a valid access token, refreshing if necessary.
        
        Returns:
            bool: True if valid token is available
            
        Raises:
            AuthenticationError: If unable to obtain valid token
        """
        if self.is_token_valid():
            return True
        
        self.logger.info("Token invalid or expired, attempting to refresh")
        return self.authenticate()
    
    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers for API requests.
        
        Returns:
            dict: Headers with authorization token
            
        Raises:
            AuthenticationError: If no valid token available
        """
        if not self.ensure_valid_token():
            raise AuthenticationError("Unable to obtain valid access token")
        
        return {
            'Authorization': f'{self._token_type} {self._access_token}'
        }
    
    def make_authenticated_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Make an authenticated request to the SensorPush API with automatic token refresh retry.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (relative to base URL)
            **kwargs: Additional arguments for requests
            
        Returns:
            requests.Response: API response
            
        Raises:
            AuthenticationError: If authentication fails
            APIConnectionError: If there are connection issues
            TokenExpiredError: If token expires and retry fails
        """
        max_retries = 1  # Allow one retry after a 401
        retry_count = 0
        
        # Store original kwargs to preserve them for retry
        original_kwargs = kwargs.copy()
        
        while retry_count <= max_retries:
            try:
                # Ensure we have a valid token (proactive check)
                self.ensure_valid_token()
                
                # Prepare request
                url = f"{self.base_url}/{endpoint.lstrip('/')}"
                headers = original_kwargs.pop('headers', {}) if retry_count == 0 else {}
                headers.update(self.get_auth_headers())
                
                # Use original_kwargs for the request to preserve parameters on retry
                request_kwargs = original_kwargs.copy()
                timeout = request_kwargs.pop('timeout', 30)
                
                self.logger.debug(f"Making authenticated request (attempt {retry_count + 1}): {method} {url}")
                self.logger.debug(f"Request Headers: {headers}")
                if 'json' in request_kwargs:
                    self.logger.debug(f"Request Body (JSON): {json.dumps(request_kwargs['json'])}")
                elif 'data' in request_kwargs:
                    self.logger.debug(f"Request Body (Data): {request_kwargs['data']}")

                # Make request
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=timeout,
                    **request_kwargs
                )
                self.logger.debug(f"Response Status Code: {response.status_code}")
                self.logger.debug(f"Response Headers: {response.headers}")
                self.logger.debug(f"Response Body: {response.text}")
                
                # Check for token expiration (reactive check)
                if response.status_code == 401:
                    self.logger.warning("Received 401, token may have expired. Attempting refresh and retry.")
                    self._access_token = None  # Clear invalid token
                    
                    if retry_count < max_retries:
                        retry_count += 1
                        self.logger.info(f"Attempting token refresh and retry (attempt {retry_count + 1})")
                        # The next iteration will call ensure_valid_token() which will re-authenticate
                        continue
                    else:
                        # If max retries reached, raise the error
                        raise TokenExpiredError("Access token expired after retry attempt")
                
                # Check for other HTTP errors
                response.raise_for_status()
                
                return response
                
            except TokenExpiredError:
                # Re-raise TokenExpiredError to propagate to caller
                raise
            except AuthenticationError as e:
                # Authentication failed during refresh - this is a critical error
                self.logger.error(f"Authentication failed during token refresh: {e}")
                raise
            except ConnectionError as e:
                raise APIConnectionError(f"Connection error: {e}")
            except Timeout as e:
                raise APIConnectionError(f"Request timeout: {e}")
            except RequestException as e:
                raise APIConnectionError(f"Request error: {e}")
        
        # Should not be reached, but as a fallback
        raise SensorPushAPIError("Failed to make authenticated request after retries")
    
    def get_token_info(self) -> Dict[str, Any]:
        """
        Get information about the current token.
        
        Returns:
            dict: Token information including validity and expiration
        """
        return {
            'has_token': bool(self._access_token),
            'is_valid': self.is_token_valid(),
            'expires_at': self._token_expires_at.isoformat() if self._token_expires_at else None,
            'token_type': self._token_type
        }
    
    def clear_token(self):
        """Clear the stored access token."""
        self._access_token = None
        self._token_expires_at = None
        self.logger.info("Access token cleared")
    
    def get_samples(self, **kwargs) -> Dict[str, Any]:
        """
        Retrieve sensor readings from the /samples endpoint.
        
        Args:
            **kwargs: Optional parameters for the samples request such as:
                - limit: Maximum number of samples to return
                - startTime: Start time for sample range (ISO format)
                - endTime: End time for sample range (ISO format)
                - sensors: List of sensor IDs to filter by
                
        Returns:
            dict: JSON response containing sensor samples data
            
        Raises:
            AuthenticationError: If authentication fails
            APIConnectionError: If there are connection issues
            SensorPushAPIError: If API returns an error response
        """
        try:
            self.logger.info("Fetching sensor samples from SensorPush API")
            
            # Prepare request parameters
            params = {}
            if kwargs:
                # Filter out None values and prepare parameters
                for key, value in kwargs.items():
                    if value is not None:
                        params[key] = value
            self.logger.debug(f"Samples request parameters: {params}")

            # Make authenticated request to samples endpoint
            response = self.make_authenticated_request(
                method='POST',
                endpoint='samples',
                json=params if params else {}
            )
            
            # Parse and return response
            samples_data = response.json()
            
            # Basic validation of response structure
            if not isinstance(samples_data, dict):
                raise SensorPushAPIError("Invalid samples response format")
            
            self.logger.info(f"Successfully retrieved samples data")
            return samples_data
            
        except (AuthenticationError, APIConnectionError, TokenExpiredError):
            # Re-raise these specific exceptions
            raise
        except HTTPError as e:
            error_msg = f"HTTP error retrieving samples: {e}"
            if e.response.status_code == 400:
                error_msg = "Bad request - check your parameters"
            elif e.response.status_code == 403:
                error_msg = "Forbidden - insufficient permissions"
            elif e.response.status_code == 404:
                error_msg = "Samples endpoint not found"
            elif e.response.status_code >= 500:
                error_msg = "Server error - please try again later"
            
            self.logger.error(error_msg)
            raise SensorPushAPIError(error_msg)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response from samples endpoint: {e}"
            self.logger.error(error_msg)
            raise SensorPushAPIError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error retrieving samples: {e}"
            self.logger.error(error_msg)
            raise SensorPushAPIError(error_msg)
    
    def get_status(self, **kwargs) -> Dict[str, Any]:
        """
        Retrieve sensor status information from the /status endpoint.
        
        Args:
            **kwargs: Optional parameters for the status request such as:
                - sensors: List of sensor IDs to get status for
                
        Returns:
            dict: JSON response containing sensor status information
            
        Raises:
            AuthenticationError: If authentication fails
            APIConnectionError: If there are connection issues
            SensorPushAPIError: If API returns an error response
        """
        try:
            self.logger.info("Fetching sensor status from SensorPush API")
            
            # Prepare request parameters
            params = {}
            if kwargs:
                # Filter out None values and prepare parameters
                for key, value in kwargs.items():
                    if value is not None:
                        params[key] = value
            self.logger.debug(f"Status request parameters: {params}")

            # Make authenticated request to status endpoint
            response = self.make_authenticated_request(
                method='GET',
                endpoint='status'
            )
            
            # Parse and return response
            status_data = response.json()
            
            # Basic validation of response structure
            if not isinstance(status_data, dict):
                raise SensorPushAPIError("Invalid status response format")
            
            self.logger.info(f"Successfully retrieved status data")
            return status_data
            
        except (AuthenticationError, APIConnectionError, TokenExpiredError):
            # Re-raise these specific exceptions
            raise
        except HTTPError as e:
            error_msg = f"HTTP error retrieving status: {e}"
            if e.response.status_code == 400:
                error_msg = "Bad request - check your parameters"
            elif e.response.status_code == 403:
                error_msg = "Forbidden - insufficient permissions"
            elif e.response.status_code == 404:
                error_msg = "Status endpoint not found"
            elif e.response.status_code >= 500:
                error_msg = "Server error - please try again later"
            
            self.logger.error(error_msg)
            raise SensorPushAPIError(error_msg)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response from status endpoint: {e}"
            self.logger.error(error_msg)
            raise SensorPushAPIError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error retrieving status: {e}"
            self.logger.error(error_msg)
            raise SensorPushAPIError(error_msg)

    def get_sensors(self, **kwargs) -> Dict[str, Any]:
        """
        Retrieve sensor metadata from the /sensors endpoint.
        
        This endpoint provides sensor information including names, hardware models,
        active status, and last seen timestamps.
        
        Args:
            **kwargs: Optional parameters for the sensors request
                
        Returns:
            dict: JSON response containing sensor metadata with names
            
        Raises:
            AuthenticationError: If authentication fails
            APIConnectionError: If there are connection issues
            SensorPushAPIError: If API returns an error response
        """
        try:
            self.logger.info("Fetching sensor metadata from SensorPush API")
            
            # Prepare request parameters
            params = {}
            if kwargs:
                # Filter out None values and prepare parameters
                for key, value in kwargs.items():
                    if value is not None:
                        params[key] = value
            self.logger.debug(f"Sensors request parameters: {params}")

            # Make authenticated request to sensors endpoint
            response = self.make_authenticated_request(
                method='GET',
                endpoint='sensors'
            )
            
            # Parse and return response
            sensors_data = response.json()
            
            # Basic validation of response structure
            if not isinstance(sensors_data, dict):
                raise SensorPushAPIError("Invalid sensors response format")
            
            self.logger.info(f"Successfully retrieved sensor metadata for {len(sensors_data)} sensors")
            return sensors_data
            
        except (AuthenticationError, APIConnectionError, TokenExpiredError):
            # Re-raise these specific exceptions
            raise
        except HTTPError as e:
            error_msg = f"HTTP error retrieving sensors: {e}"
            if e.response.status_code == 400:
                error_msg = "Bad request - check your parameters"
            elif e.response.status_code == 403:
                error_msg = "Forbidden - insufficient permissions"
            elif e.response.status_code == 404:
                error_msg = "Sensors endpoint not found"
            elif e.response.status_code >= 500:
                error_msg = "Server error - please try again later"
            
            self.logger.error(error_msg)
            raise SensorPushAPIError(error_msg)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response from sensors endpoint: {e}"
            self.logger.error(error_msg)
            raise SensorPushAPIError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error retrieving sensors: {e}"
            self.logger.error(error_msg)
            raise SensorPushAPIError(error_msg)

    def get_devices_sensors(self, **kwargs) -> Dict[str, Any]:
        """
        Retrieve sensor devices from the /devices/sensors endpoint.
        
        This endpoint provides sensor device information including IDs and names.
        
        Args:
            **kwargs: Optional parameters for the devices/sensors request
                
        Returns:
            dict: JSON response containing sensor device metadata with IDs and names
            
        Raises:
            AuthenticationError: If authentication fails
            APIConnectionError: If there are connection issues
            SensorPushAPIError: If API returns an error response
        """
        try:
            self.logger.info("Fetching sensor devices from SensorPush API")
            
            # Prepare request parameters
            params = {}
            if kwargs:
                # Filter out None values and prepare parameters
                for key, value in kwargs.items():
                    if value is not None:
                        params[key] = value
            self.logger.debug(f"Devices/sensors request parameters: {params}")

            # Make authenticated request to devices/sensors endpoint
            response = self.make_authenticated_request(
                method='GET',
                endpoint='devices/sensors'
            )
            
            # Parse and return response
            devices_data = response.json()
            
            # Basic validation of response structure
            if not isinstance(devices_data, dict):
                raise SensorPushAPIError("Invalid devices/sensors response format")
            
            self.logger.info(f"Successfully retrieved sensor devices for {len(devices_data)} sensors")
            return devices_data
            
        except (AuthenticationError, APIConnectionError, TokenExpiredError):
            # Re-raise these specific exceptions
            raise
        except HTTPError as e:
            error_msg = f"HTTP error retrieving sensor devices: {e}"
            if e.response.status_code == 400:
                error_msg = "Bad request - check your parameters"
            elif e.response.status_code == 403:
                error_msg = "Forbidden - insufficient permissions"
            elif e.response.status_code == 404:
                error_msg = "Devices/sensors endpoint not found"
            elif e.response.status_code >= 500:
                error_msg = "Server error - please try again later"
            
            self.logger.error(error_msg)
            raise SensorPushAPIError(error_msg)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response from devices/sensors endpoint: {e}"
            self.logger.error(error_msg)
            raise SensorPushAPIError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error retrieving sensor devices: {e}"
            self.logger.error(error_msg)
            raise SensorPushAPIError(error_msg)

    def close(self):
        """Close the session and clean up resources."""
        if hasattr(self, 'session'):
            self.session.close()
        self.clear_token()


# Convenience function for creating API client
def create_api_client(config_class=None) -> SensorPushAPI:
    """
    Create a SensorPush API client instance.
    
    Args:
        config_class: Configuration class to use (defaults to Config)
        
    Returns:
        SensorPushAPI: Configured API client instance
    """
    return SensorPushAPI(config_class)


# Example usage and testing function
def test_authentication():
    """
    Test function to verify authentication works.
    This can be used for debugging and validation.
    """
    try:
        # Create API client
        api = create_api_client()
        
        # Test authentication
        if api.authenticate():
            print("✓ Authentication successful")
            print(f"Token info: {api.get_token_info()}")
            return True
        else:
            print("✗ Authentication failed")
            return False
            
    except Exception as e:
        print(f"✗ Authentication error: {e}")
        return False
    finally:
        if 'api' in locals():
            api.close()

def test_api_methods():
    """
    Test function to verify API methods work.
    This tests the get_samples() and get_status() methods.
    """
    api = None
    try:
        # Create API client
        api = create_api_client()
        
        # Test authentication first
        if not api.authenticate():
            print("✗ Authentication failed")
            return False
        
        print("✓ Authentication successful")
        
        # Test get_status method
        try:
            print("Testing get_status()...")
            status_data = api.get_status()
            print(f"✓ Status retrieved successfully. Keys: {list(status_data.keys())}")
        except Exception as e:
            print(f"✗ Status retrieval failed: {e}")
        
        # Test get_samples method
        try:
            print("Testing get_samples()...")
            samples_data = api.get_samples()
            print(f"✓ Samples retrieved successfully. Keys: {list(samples_data.keys())}")
        except Exception as e:
            print(f"✗ Samples retrieval failed: {e}")
        
        return True
        
    except Exception as e:
        print(f"✗ API test error: {e}")
        return False
    finally:
        if api:
            api.close()

if __name__ == "__main__":
    # Configure logging for testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run authentication test
    print("=== Testing Authentication ===")
    test_authentication()
    
    print("\n=== Testing API Methods ===")
    test_api_methods()