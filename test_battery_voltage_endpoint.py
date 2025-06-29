#!/usr/bin/env python3
"""
Test script to verify battery_voltage data is available in the /devices/sensors endpoint.
"""

import sys
import logging
import json
from config import get_config
from sensorpush_api import SensorPushAPI, SensorPushAPIError

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_devices_sensors_endpoint():
    """Test the /devices/sensors endpoint to check for battery_voltage data."""
    logger.info("Testing /devices/sensors endpoint for battery_voltage data...")
    
    try:
        config = get_config()
        api_client = SensorPushAPI(config)
        
        # Authenticate
        if not api_client.authenticate():
            logger.error("✗ Failed to authenticate with API")
            return False
        
        logger.info("✓ API authentication successful")
        
        # Test /devices/sensors endpoint
        logger.info("Calling /devices/sensors endpoint...")
        devices_data = api_client.get_devices_sensors()
        
        logger.info(f"✓ Retrieved devices data with {len(devices_data)} sensors")
        
        # Check for battery_voltage in the response
        battery_voltage_found = False
        sensors_with_battery = []
        
        logger.info("\nAnalyzing devices/sensors response structure:")
        logger.info(f"Response type: {type(devices_data)}")
        logger.info(f"Response keys: {list(devices_data.keys()) if isinstance(devices_data, dict) else 'Not a dict'}")
        
        # Pretty print a sample of the response
        if devices_data:
            logger.info("\nSample response data:")
            sample_data = dict(list(devices_data.items())[:2])  # First 2 sensors
            logger.info(json.dumps(sample_data, indent=2, default=str))
        
        # Check each sensor for battery_voltage
        for sensor_id, sensor_info in devices_data.items():
            if isinstance(sensor_info, dict):
                if 'battery_voltage' in sensor_info:
                    battery_voltage_found = True
                    sensors_with_battery.append(sensor_id)
                    logger.info(f"✓ Sensor {sensor_id} has battery_voltage: {sensor_info['battery_voltage']}")
                else:
                    logger.debug(f"Sensor {sensor_id} fields: {list(sensor_info.keys())}")
        
        if battery_voltage_found:
            logger.info(f"\n✓ SUCCESS: battery_voltage found in /devices/sensors for {len(sensors_with_battery)} sensors")
        else:
            logger.warning(f"\n✗ No battery_voltage found in /devices/sensors endpoint")
            
            # Show what fields are available
            if devices_data:
                sample_sensor = next(iter(devices_data.values()))
                if isinstance(sample_sensor, dict):
                    logger.info(f"Available fields in sensor data: {list(sample_sensor.keys())}")
        
        return battery_voltage_found
        
    except Exception as e:
        logger.error(f"✗ Failed to test /devices/sensors endpoint: {e}")
        return False

def compare_endpoints():
    """Compare data from /samples vs /devices/sensors endpoints."""
    logger.info("\n" + "="*50)
    logger.info("COMPARING /samples vs /devices/sensors ENDPOINTS")
    logger.info("="*50)
    
    try:
        config = get_config()
        api_client = SensorPushAPI(config)
        
        if not api_client.authenticate():
            logger.error("✗ Failed to authenticate")
            return
        
        # Get samples data
        logger.info("Getting /samples data...")
        samples_data = api_client.get_samples()
        
        # Get devices/sensors data
        logger.info("Getting /devices/sensors data...")
        devices_data = api_client.get_devices_sensors()
        
        logger.info(f"\n/samples endpoint: {len(samples_data.get('sensors', {}))} sensors")
        logger.info(f"/devices/sensors endpoint: {len(devices_data)} sensors")
        
        # Compare sensor IDs
        samples_sensor_ids = set(samples_data.get('sensors', {}).keys())
        devices_sensor_ids = set(devices_data.keys())
        
        logger.info(f"\nSensor ID overlap: {len(samples_sensor_ids & devices_sensor_ids)} common sensors")
        
        # Show sample data structure from each endpoint
        if samples_data.get('sensors'):
            sample_sensor_id = next(iter(samples_data['sensors'].keys()))
            sample_readings = samples_data['sensors'][sample_sensor_id]
            if sample_readings:
                logger.info(f"\n/samples data structure for sensor {sample_sensor_id}:")
                logger.info(f"  Reading fields: {list(sample_readings[0].keys()) if sample_readings else 'No readings'}")
        
        if devices_data:
            sample_sensor_id = next(iter(devices_data.keys()))
            sample_device = devices_data[sample_sensor_id]
            logger.info(f"\n/devices/sensors data structure for sensor {sample_sensor_id}:")
            logger.info(f"  Device fields: {list(sample_device.keys()) if isinstance(sample_device, dict) else 'Not a dict'}")
        
    except Exception as e:
        logger.error(f"✗ Failed to compare endpoints: {e}")

def main():
    """Main function."""
    logger.info("Battery Voltage Endpoint Test")
    logger.info("=" * 50)
    
    # Test the devices/sensors endpoint
    success = test_devices_sensors_endpoint()
    
    # Compare both endpoints
    compare_endpoints()
    
    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("TEST SUMMARY")
    logger.info("=" * 50)
    
    if success:
        logger.info("✓ battery_voltage data IS available in /devices/sensors endpoint")
        logger.info("RECOMMENDATION: Modify polling service to call get_devices_sensors() for battery data")
    else:
        logger.info("✗ battery_voltage data NOT found in /devices/sensors endpoint")
        logger.info("RECOMMENDATION: Check SensorPush API documentation for battery data location")

if __name__ == "__main__":
    main()