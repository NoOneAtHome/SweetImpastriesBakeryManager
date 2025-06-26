#!/usr/bin/env python3
"""
Test script to verify the Status endpoint fix.

This script tests the corrected SensorPush API Status endpoint implementation
to ensure it works correctly with the real API.
"""

import sys
import logging
from config import Config
from sensorpush_api import SensorPushAPI, SensorPushAPIError, AuthenticationError, APIConnectionError

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_status_endpoint():
    """Test the corrected Status endpoint implementation."""
    try:
        logger.info("Testing SensorPush API Status endpoint fix...")
        
        # Create API client
        api = SensorPushAPI(Config)
        
        # Test authentication
        logger.info("Testing authentication...")
        if not api.authenticate():
            logger.error("Authentication failed")
            return False
        logger.info("✓ Authentication successful")
        
        # Test Status endpoint
        logger.info("Testing Status endpoint...")
        try:
            status_data = api.get_status()
            logger.info("✓ Status endpoint call successful")
            
            # Validate response structure
            if not isinstance(status_data, dict):
                logger.error("✗ Status response is not a dictionary")
                return False
            
            # Check for expected Status endpoint fields
            expected_fields = ['sensors', 'gateway_connected', 'timestamp']
            missing_fields = []
            
            for field in expected_fields:
                if field not in status_data:
                    missing_fields.append(field)
            
            if missing_fields:
                logger.warning(f"Status response missing expected fields: {missing_fields}")
                logger.info(f"Actual response keys: {list(status_data.keys())}")
            else:
                logger.info("✓ Status response has expected structure")
            
            # Log response details
            sensors_data = status_data.get('sensors', {})
            gateway_connected = status_data.get('gateway_connected', 'unknown')
            timestamp = status_data.get('timestamp', 'unknown')
            
            logger.info(f"Status summary:")
            logger.info(f"  - Gateway connected: {gateway_connected}")
            logger.info(f"  - Timestamp: {timestamp}")
            logger.info(f"  - Number of sensors: {len(sensors_data)}")
            
            # Log sensor details
            for sensor_id, sensor_status in sensors_data.items():
                temp = sensor_status.get('temperature', 'N/A')
                humidity = sensor_status.get('humidity', 'N/A')
                status = sensor_status.get('status', 'N/A')
                logger.info(f"  - Sensor {sensor_id}: T={temp}°C, H={humidity}%, Status={status}")
            
            logger.info("✓ Status endpoint test completed successfully")
            return True
            
        except SensorPushAPIError as e:
            logger.error(f"✗ Status endpoint API error: {e}")
            return False
            
    except AuthenticationError as e:
        logger.error(f"✗ Authentication error: {e}")
        return False
    except APIConnectionError as e:
        logger.error(f"✗ Connection error: {e}")
        return False
    except Exception as e:
        logger.error(f"✗ Unexpected error: {e}")
        return False
    finally:
        # Clean up
        if 'api' in locals():
            api.close()

def main():
    """Main function."""
    logger.info("SensorPush API Status Endpoint Fix Test")
    logger.info("=" * 50)
    
    success = test_status_endpoint()
    
    if success:
        logger.info("✓ All tests passed! Status endpoint fix is working correctly.")
        sys.exit(0)
    else:
        logger.error("✗ Tests failed. Please check the implementation.")
        sys.exit(1)

if __name__ == "__main__":
    main()