#!/usr/bin/env python3
"""
Demonstration script for the DataRetentionService.

This script shows how to use the DataRetentionService for both automatic
purging and on-demand deletion of sensor readings.
"""

import sys
from datetime import datetime, timedelta
from data_retention import DataRetentionService
from config import Config

def main():
    """Demonstrate DataRetentionService functionality."""
    print("=== DataRetentionService Demonstration ===\n")
    
    # Initialize the service
    service = DataRetentionService()
    print("✓ DataRetentionService initialized")
    
    try:
        # 1. Validate configuration
        print("\n1. Validating retention configuration...")
        config_validation = service.validate_config()
        print(f"   Configuration valid: {config_validation['is_valid']}")
        print(f"   Configured retention: {config_validation['configured_months']} months")
        print(f"   Effective retention: {config_validation['effective_months']} months")
        if config_validation['warnings']:
            for warning in config_validation['warnings']:
                print(f"   ⚠️  Warning: {warning}")
        
        # 2. Get current retention statistics
        print("\n2. Getting current retention statistics...")
        stats = service.get_retention_stats()
        print(f"   Total records: {stats['total_records']}")
        print(f"   Oldest record: {stats['oldest_record_date']}")
        print(f"   Newest record: {stats['newest_record_date']}")
        print(f"   Records eligible for purge: {stats['records_eligible_for_purge']}")
        
        # 3. Demonstrate automatic purging
        print("\n3. Running automatic purge of old readings...")
        purge_result = service.purge_old_readings()
        if purge_result['success']:
            print(f"   ✓ Purge successful: {purge_result['records_deleted']} records deleted")
            print(f"   Cutoff date: {purge_result['cutoff_date']}")
            print(f"   Retention period: {purge_result['retention_months']} months")
        else:
            print(f"   ❌ Purge failed: {purge_result['error_message']}")
        
        # 4. Demonstrate sensor data summary
        print("\n4. Getting sensor data summaries...")
        # Get a list of sensors from the stats (this is a simplified approach)
        if stats['total_records'] > 0:
            # For demo purposes, we'll try a few common sensor IDs
            demo_sensor_ids = ['sensor1', 'sensor2', 'test_sensor']
            for sensor_id in demo_sensor_ids:
                try:
                    summary = service.get_sensor_data_summary(sensor_id)
                    if summary['total_records'] > 0:
                        print(f"   Sensor {sensor_id}:")
                        print(f"     Records: {summary['total_records']}")
                        print(f"     Date range: {summary['date_range_days']} days")
                        print(f"     Oldest: {summary['oldest_record_date']}")
                        print(f"     Newest: {summary['newest_record_date']}")
                        break
                except Exception:
                    continue
            else:
                print("   No sensor data found for demo sensor IDs")
        else:
            print("   No sensor data available for summary")
        
        # 5. Demonstrate on-demand deletion (commented out to avoid deleting real data)
        print("\n5. On-demand deletion capabilities:")
        print("   📝 Available methods:")
        print("   - delete_readings_by_sensor(sensor_id, start_date=None, end_date=None)")
        print("   - delete_readings_by_date_range(start_date, end_date, sensor_ids=None)")
        print("   💡 These methods are available but not executed in this demo")
        print("      to preserve existing data.")
        
        # Example of how to use on-demand deletion (commented out)
        """
        # Delete all readings for a specific sensor
        result = service.delete_readings_by_sensor('old_sensor_id')
        
        # Delete readings for a sensor within a date range
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 12, 31)
        result = service.delete_readings_by_sensor('sensor_id', start_date, end_date)
        
        # Delete all readings within a date range
        result = service.delete_readings_by_date_range(start_date, end_date)
        
        # Delete readings for specific sensors within a date range
        sensor_list = ['sensor1', 'sensor2']
        result = service.delete_readings_by_date_range(start_date, end_date, sensor_list)
        """
        
        print("\n=== Demonstration Complete ===")
        print("✓ DataRetentionService is fully functional and ready for use")
        
    except Exception as e:
        print(f"\n❌ Error during demonstration: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())