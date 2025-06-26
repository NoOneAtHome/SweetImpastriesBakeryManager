#!/usr/bin/env python3
"""
Debug script to investigate the Status endpoint issue.

This script will try different endpoint variations to find the correct Status endpoint.
"""

import sys
import logging
from config import Config
from sensorpush_api import SensorPushAPI, SensorPushAPIError, AuthenticationError, APIConnectionError

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_endpoint_variations():
    """Test different endpoint variations to find the correct Status endpoint."""
    try:
        logger.info("Testing different Status endpoint variations...")
        
        # Create API client
        api = SensorPushAPI(Config)
        
        # Test authentication
        logger.info("Testing authentication...")
        if not api.authenticate():
            logger.error("Authentication failed")
            return False
        logger.info("✓ Authentication successful")
        
        # Test different endpoint variations
        endpoints_to_test = [
            ('GET', 'status'),
            ('POST', 'status'),
            ('GET', 'devices/status'),
            ('POST', 'devices/status'),
            ('GET', 'sensors/status'),
            ('POST', 'sensors/status'),
            ('GET', 'gateways/status'),
            ('POST', 'gateways/status'),
        ]
        
        for method, endpoint in endpoints_to_test:
            try:
                logger.info(f"Testing {method} {endpoint}...")
                
                if method == 'GET':
                    response = api.make_authenticated_request(
                        method='GET',
                        endpoint=endpoint
                    )
                else:
                    response = api.make_authenticated_request(
                        method='POST',
                        endpoint=endpoint,
                        json={}
                    )
                
                data = response.json()
                logger.info(f"✓ {method} {endpoint} - SUCCESS!")
                logger.info(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                
                # If we get here, this endpoint works
                return True
                
            except Exception as e:
                logger.debug(f"✗ {method} {endpoint} - Failed: {e}")
                continue
        
        logger.error("No working status endpoint found")
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
    logger.info("SensorPush API Status Endpoint Debug")
    logger.info("=" * 50)
    
    success = test_endpoint_variations()
    
    if success:
        logger.info("✓ Found working status endpoint!")
        sys.exit(0)
    else:
        logger.error("✗ No working status endpoint found.")
        sys.exit(1)

if __name__ == "__main__":
    main()