#!/usr/bin/env python3
"""
Diagnostic script to check if the polling service is running.

This script will:
1. Check if there's a running Flask application
2. Try to connect to the application and check polling service status
3. Create a standalone polling service instance to test its functionality
4. Report findings about battery_voltage collection
"""

import sys
import logging
import requests
import time
from datetime import datetime
from config import get_config
from polling_service import create_polling_service, PollingServiceError
from sensorpush_api import SensorPushAPI, SensorPushAPIError
from database import get_db_session_context
from models import SensorReading
from sqlalchemy import desc

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_flask_app_running():
    """Check if the Flask application is running by trying to connect to it."""
    logger.info("Checking if Flask application is running...")
    
    # Common ports for Flask development
    ports_to_check = [5000, 8000, 3000]
    
    for port in ports_to_check:
        try:
            url = f"http://localhost:{port}/api/sensors"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                logger.info(f"✓ Flask application found running on port {port}")
                return port
        except requests.exceptions.RequestException:
            continue
    
    logger.info("✗ No Flask application found running on common ports")
    return None

def check_polling_service_via_api(port):
    """Check polling service status via the Flask API if available."""
    try:
        # Try to get a status endpoint or any endpoint that might show polling info
        url = f"http://localhost:{port}/api/sensors"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✓ API responded with {len(data)} sensors")
            return True
        else:
            logger.warning(f"API responded with status code: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"✗ Failed to check polling service via API: {e}")
        return False

def test_standalone_polling_service():
    """Test creating and checking a standalone polling service."""
    logger.info("Testing standalone polling service...")
    
    try:
        config = get_config()
        
        # Create polling service
        service = create_polling_service(config_class=config)
        logger.info("✓ Polling service created successfully")
        
        # Check if it can start (don't actually start it to avoid conflicts)
        logger.info("Checking polling service configuration...")
        
        # Validate configuration
        missing_vars = config.validate_required_config()
        if missing_vars:
            logger.error(f"✗ Missing configuration variables: {', '.join(missing_vars)}")
            return False
        else:
            logger.info("✓ Configuration is valid")
        
        # Test API connection
        api_client = SensorPushAPI(config)
        if api_client.authenticate():
            logger.info("✓ API authentication successful")
        else:
            logger.error("✗ API authentication failed")
            return False
        
        # Get service status (even if not running)
        status = service.get_status()
        logger.info(f"Polling service status: {status}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to test standalone polling service: {e}")
        return False

def check_battery_voltage_in_api():
    """Check if battery_voltage is present in raw API responses."""
    logger.info("Checking for battery_voltage in API responses...")
    
    try:
        config = get_config()
        api_client = SensorPushAPI(config)
        
        if not api_client.authenticate():
            logger.error("✗ Failed to authenticate with API")
            return False
        
        # Get samples data
        samples_data = api_client.get_samples()
        logger.info(f"✓ Retrieved samples data with {len(samples_data.get('sensors', {}))} sensors")
        
        # Check for battery_voltage in the data
        battery_voltage_found = False
        sensors_with_battery = []
        
        for sensor_id, readings in samples_data.get('sensors', {}).items():
            if isinstance(readings, list) and readings:
                # Check the most recent reading
                recent_reading = readings[0] if readings else {}
                if 'battery_voltage' in recent_reading:
                    battery_voltage_found = True
                    sensors_with_battery.append(sensor_id)
                    logger.info(f"✓ Sensor {sensor_id} has battery_voltage: {recent_reading['battery_voltage']}")
        
        if battery_voltage_found:
            logger.info(f"✓ battery_voltage found in API responses for {len(sensors_with_battery)} sensors")
        else:
            logger.warning("✗ No battery_voltage found in any API responses")
        
        return battery_voltage_found
        
    except Exception as e:
        logger.error(f"✗ Failed to check battery_voltage in API: {e}")
        return False

def check_battery_voltage_in_database():
    """Check if battery_voltage is being stored in the database."""
    logger.info("Checking for battery_voltage in database...")
    
    try:
        with get_db_session_context() as session:
            # Get recent readings with battery_voltage
            recent_readings = session.query(SensorReading).filter(
                SensorReading.battery_voltage.isnot(None)
            ).order_by(desc(SensorReading.timestamp)).limit(10).all()
            
            if recent_readings:
                logger.info(f"✓ Found {len(recent_readings)} recent readings with battery_voltage in database")
                for reading in recent_readings[:3]:  # Show first 3
                    logger.info(f"  Sensor {reading.sensor_id}: {reading.battery_voltage}V at {reading.timestamp}")
                return True
            else:
                logger.warning("✗ No readings with battery_voltage found in database")
                
                # Check if there are any readings at all
                total_readings = session.query(SensorReading).count()
                logger.info(f"Total readings in database: {total_readings}")
                
                if total_readings > 0:
                    # Check recent readings regardless of battery_voltage
                    recent_any = session.query(SensorReading).order_by(
                        desc(SensorReading.timestamp)
                    ).limit(5).all()
                    
                    logger.info("Recent readings (any type):")
                    for reading in recent_any:
                        logger.info(f"  Sensor {reading.sensor_id}: T={reading.temperature}°C, H={reading.humidity}%, "
                                  f"Battery={reading.battery_voltage}V, Time={reading.timestamp}")
                
                return False
                
    except Exception as e:
        logger.error(f"✗ Failed to check battery_voltage in database: {e}")
        return False

def main():
    """Main diagnostic function."""
    logger.info("Polling Service Diagnostic Tool")
    logger.info("=" * 50)
    
    results = {}
    
    # 1. Check if Flask app is running
    flask_port = check_flask_app_running()
    results['flask_running'] = flask_port is not None
    
    # 2. If Flask is running, check polling service via API
    if flask_port:
        results['api_accessible'] = check_polling_service_via_api(flask_port)
    else:
        results['api_accessible'] = False
    
    # 3. Test standalone polling service
    results['polling_service_config'] = test_standalone_polling_service()
    
    # 4. Check battery_voltage in API responses
    results['battery_voltage_in_api'] = check_battery_voltage_in_api()
    
    # 5. Check battery_voltage in database
    results['battery_voltage_in_db'] = check_battery_voltage_in_database()
    
    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("DIAGNOSTIC SUMMARY")
    logger.info("=" * 50)
    
    for check, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{check}: {status}")
    
    # Recommendations
    logger.info("\nRECOMMENDATIONS:")
    
    if not results['flask_running']:
        logger.info("• Flask application is not running. Start it with: python app.py")
    
    if not results['polling_service_config']:
        logger.info("• Polling service configuration issues detected. Check environment variables.")
    
    if not results['battery_voltage_in_api']:
        logger.info("• battery_voltage not found in API responses. This may be a SensorPush API limitation.")
    
    if not results['battery_voltage_in_db']:
        logger.info("• battery_voltage not being stored in database. Check if polling service is collecting data.")
    
    if results['battery_voltage_in_api'] and not results['battery_voltage_in_db']:
        logger.info("• battery_voltage available in API but not in database. Polling service may not be running.")

if __name__ == "__main__":
    main()