#!/usr/bin/env python3
"""
Test script to verify the integrated polling service works correctly.
"""

import logging
import sys
import time
from flask import Flask

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_integrated_polling_service():
    """Test that the polling service is properly integrated into the Flask app."""
    logger.info("=== Testing Integrated Polling Service ===")
    
    try:
        # Import app as a module (this is what Gunicorn does)
        from app import app
        
        # Check if polling service is attached to app
        has_polling_service = hasattr(app, 'polling_service')
        logger.info(f"App has polling_service attribute: {has_polling_service}")
        
        if has_polling_service and app.polling_service:
            # Check if polling service is running
            is_running = app.polling_service.is_running()
            logger.info(f"Polling service is running: {is_running}")
            
            # Get status
            status = app.polling_service.get_status()
            logger.info(f"Polling service status: {status}")
            
            # Test within app context
            with app.app_context():
                from flask import current_app
                has_current_app_polling = hasattr(current_app, 'polling_service')
                logger.info(f"current_app has polling_service: {has_current_app_polling}")
                
                if has_current_app_polling and current_app.polling_service:
                    current_app_running = current_app.polling_service.is_running()
                    logger.info(f"current_app polling service is running: {current_app_running}")
                    
                    return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error testing integrated polling service: {e}")
        return False

def test_direct_app_creation():
    """Test creating app directly with different configurations."""
    logger.info("=== Testing Direct App Creation ===")
    
    try:
        from app import create_app
        from config import DevelopmentConfig, ProductionConfig
        
        # Test with development config
        dev_app = create_app(config_class=DevelopmentConfig)
        dev_has_polling = hasattr(dev_app, 'polling_service') and dev_app.polling_service is not None
        logger.info(f"Development app has polling service: {dev_has_polling}")
        
        if dev_has_polling:
            dev_running = dev_app.polling_service.is_running()
            logger.info(f"Development polling service is running: {dev_running}")
            
            # Clean up
            if dev_running:
                dev_app.polling_service.stop()
                logger.info("Development polling service stopped")
        
        # Test with production config
        prod_app = create_app(config_class=ProductionConfig)
        prod_has_polling = hasattr(prod_app, 'polling_service') and prod_app.polling_service is not None
        logger.info(f"Production app has polling service: {prod_has_polling}")
        
        if prod_has_polling:
            prod_running = prod_app.polling_service.is_running()
            logger.info(f"Production polling service is running: {prod_running}")
            
            # Clean up
            if prod_running:
                prod_app.polling_service.stop()
                logger.info("Production polling service stopped")
        
        return dev_has_polling and prod_has_polling
        
    except Exception as e:
        logger.error(f"Error testing direct app creation: {e}")
        return False

def test_polling_service_disabled():
    """Test creating app with polling service disabled."""
    logger.info("=== Testing Polling Service Disabled ===")
    
    try:
        from app import create_app
        
        # Create app with polling service disabled
        app_no_polling = create_app(start_polling_service=False)
        has_polling = hasattr(app_no_polling, 'polling_service') and app_no_polling.polling_service is not None
        logger.info(f"App with disabled polling has polling service: {has_polling}")
        
        return not has_polling  # Should be False when disabled
        
    except Exception as e:
        logger.error(f"Error testing disabled polling service: {e}")
        return False

if __name__ == '__main__':
    logger.info("Starting integrated polling service tests...")
    
    # Test 1: Integrated polling service
    try:
        integrated_works = test_integrated_polling_service()
        logger.info(f"Integrated polling service test: {'PASS' if integrated_works else 'FAIL'}")
    except Exception as e:
        logger.error(f"Integrated polling service test failed: {e}")
        integrated_works = False
    
    # Test 2: Direct app creation
    try:
        direct_works = test_direct_app_creation()
        logger.info(f"Direct app creation test: {'PASS' if direct_works else 'FAIL'}")
    except Exception as e:
        logger.error(f"Direct app creation test failed: {e}")
        direct_works = False
    
    # Test 3: Polling service disabled
    try:
        disabled_works = test_polling_service_disabled()
        logger.info(f"Polling service disabled test: {'PASS' if disabled_works else 'FAIL'}")
    except Exception as e:
        logger.error(f"Polling service disabled test failed: {e}")
        disabled_works = False
    
    # Summary
    all_passed = integrated_works and direct_works and disabled_works
    logger.info(f"All tests passed: {all_passed}")
    
    if all_passed:
        logger.info("✓ Polling service integration is working correctly!")
    else:
        logger.error("✗ Some tests failed. Check the logs above for details.")
    
    sys.exit(0 if all_passed else 1)