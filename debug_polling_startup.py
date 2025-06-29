#!/usr/bin/env python3
"""
Debug script to validate polling service startup assumptions.
"""

import logging
import sys
import os
from flask import Flask

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_direct_import():
    """Test what happens when we import app directly (like Gunicorn does)."""
    logger.info("=== Testing Direct Import (Gunicorn-style) ===")
    
    # Import app as a module (this is what Gunicorn does)
    from app import app
    
    # Check if polling service is attached to app
    has_polling_service = hasattr(app, 'polling_service')
    logger.info(f"App has polling_service attribute: {has_polling_service}")
    
    # Check if we can access it via current_app context
    with app.app_context():
        from flask import current_app
        has_current_app_polling = hasattr(current_app, 'polling_service')
        logger.info(f"current_app has polling_service: {has_current_app_polling}")
    
    return has_polling_service, has_current_app_polling

def test_main_execution():
    """Test what happens when we run the main block."""
    logger.info("=== Testing Main Block Execution ===")
    
    # This simulates what happens when running `python app.py`
    from config import get_config
    from polling_service import create_polling_service
    from app import create_app
    
    config = get_config()
    app = create_app()
    
    # Create polling service like in __main__
    polling_service_instance = create_polling_service(config_class=config)
    
    # Check if it can start
    can_start = polling_service_instance.start()
    logger.info(f"Polling service can start: {can_start}")
    
    if can_start:
        is_running = polling_service_instance.is_running()
        logger.info(f"Polling service is running: {is_running}")
        
        # Stop it
        polling_service_instance.stop()
        logger.info("Polling service stopped")
    
    return can_start

def test_gunicorn_config():
    """Test the Gunicorn configuration approach."""
    logger.info("=== Testing Gunicorn Config Approach ===")
    
    try:
        from gunicorn_config import post_fork
        from config import ProductionConfig
        
        # Simulate what post_fork does
        from polling_service import create_polling_service
        
        polling_service_instance = create_polling_service(config_class=ProductionConfig)
        can_start = polling_service_instance.start()
        logger.info(f"Gunicorn-style polling service can start: {can_start}")
        
        if can_start:
            is_running = polling_service_instance.is_running()
            logger.info(f"Gunicorn-style polling service is running: {is_running}")
            polling_service_instance.stop()
        
        return can_start
    except Exception as e:
        logger.error(f"Error testing Gunicorn config: {e}")
        return False

if __name__ == '__main__':
    logger.info("Starting polling service startup diagnostics...")
    
    # Test 1: Direct import (what Gunicorn does)
    try:
        has_attr, has_current = test_direct_import()
        logger.info(f"Direct import results: has_attribute={has_attr}, has_current_app={has_current}")
    except Exception as e:
        logger.error(f"Direct import test failed: {e}")
    
    # Test 2: Main execution simulation
    try:
        main_works = test_main_execution()
        logger.info(f"Main execution works: {main_works}")
    except Exception as e:
        logger.error(f"Main execution test failed: {e}")
    
    # Test 3: Gunicorn config approach
    try:
        gunicorn_works = test_gunicorn_config()
        logger.info(f"Gunicorn config works: {gunicorn_works}")
    except Exception as e:
        logger.error(f"Gunicorn config test failed: {e}")
    
    logger.info("Diagnostics complete.")