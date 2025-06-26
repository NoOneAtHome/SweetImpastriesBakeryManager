"""
Data Retention and Purging Logic for the Bakery Sensors application.

This module manages the automatic purging of old sensor readings based on
the configured data retention period, ensuring that at least 6 months of
data are always retained. It also provides on-demand deletion capabilities.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_, func

from config import Config
from database import get_db_session_context
from models import SensorReading
from error_handling import handle_polling_error, log_info, log_warning, log_debug


class DataRetentionError(Exception):
    """Base exception for data retention errors."""
    pass


class DataRetentionService:
    """
    Service class for managing data retention and purging operations.
    
    This service provides both automatic purging based on retention policies
    and on-demand deletion capabilities for sensor readings.
    """
    
    def __init__(self, config_class=None):
        """
        Initialize the DataRetentionService.
        
        Args:
            config_class: Configuration class to use (defaults to Config)
        """
        self.config = config_class or Config
        self.logger = logging.getLogger(__name__)
    
    def purge_old_readings(self) -> Dict[str, Any]:
        """
        Purge old sensor readings based on the configured retention period.
        
        This method delegates to the module-level function for backward compatibility.
        
        Returns:
            dict: Results of the purging operation
        """
        return purge_old_readings(self.config)
    
    def delete_readings_by_sensor(self, sensor_id: str, start_date: Optional[datetime] = None,
                                 end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Delete sensor readings for a specific sensor within an optional date range.
        
        Args:
            sensor_id: ID of the sensor whose readings should be deleted
            start_date: Optional start date for deletion range (inclusive)
            end_date: Optional end date for deletion range (inclusive)
            
        Returns:
            dict: Results of the deletion operation including:
                - success: bool indicating if operation was successful
                - records_deleted: int number of records deleted
                - sensor_id: str sensor ID that was processed
                - date_range: dict with start_date and end_date used
                - error_message: str error message if operation failed
        """
        log_info(f"Starting on-demand deletion for sensor {sensor_id}", "delete_readings_by_sensor")
        
        try:
            with get_db_session_context() as session:
                # Build query for the specific sensor
                query = session.query(SensorReading).filter(SensorReading.sensor_id == sensor_id)
                
                # Apply date filters if provided
                if start_date:
                    query = query.filter(SensorReading.timestamp >= start_date)
                if end_date:
                    query = query.filter(SensorReading.timestamp <= end_date)
                
                # Count records to be deleted
                records_to_delete = query.count()
                
                if records_to_delete == 0:
                    log_info(f"No records found for sensor {sensor_id} in specified range", "delete_readings_by_sensor")
                    return {
                        'success': True,
                        'records_deleted': 0,
                        'sensor_id': sensor_id,
                        'date_range': {'start_date': start_date, 'end_date': end_date},
                        'error_message': None
                    }
                
                log_info(f"Found {records_to_delete} records to delete for sensor {sensor_id}", "delete_readings_by_sensor")
                
                # Delete the records
                deleted_count = query.delete()
                session.commit()
                
                log_info(f"Successfully deleted {deleted_count} readings for sensor {sensor_id}", "delete_readings_by_sensor")
                
                return {
                    'success': True,
                    'records_deleted': deleted_count,
                    'sensor_id': sensor_id,
                    'date_range': {'start_date': start_date, 'end_date': end_date},
                    'error_message': None
                }
                
        except SQLAlchemyError as e:
            error_id = handle_polling_error(e, f"Database error during on-demand deletion for sensor {sensor_id}")
            error_msg = f"Database error during deletion for sensor {sensor_id} with error ID: {error_id}"
            log_warning(error_msg, "delete_readings_by_sensor")
            
            return {
                'success': False,
                'records_deleted': 0,
                'sensor_id': sensor_id,
                'date_range': {'start_date': start_date, 'end_date': end_date},
                'error_message': error_msg
            }
            
        except Exception as e:
            error_id = handle_polling_error(e, f"Unexpected error during on-demand deletion for sensor {sensor_id}")
            error_msg = f"Unexpected error during deletion for sensor {sensor_id} with error ID: {error_id}"
            log_warning(error_msg, "delete_readings_by_sensor")
            
            return {
                'success': False,
                'records_deleted': 0,
                'sensor_id': sensor_id,
                'date_range': {'start_date': start_date, 'end_date': end_date},
                'error_message': error_msg
            }
    
    def delete_readings_by_date_range(self, start_date: datetime, end_date: datetime,
                                     sensor_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Delete sensor readings within a specific date range, optionally filtered by sensor IDs.
        
        Args:
            start_date: Start date for deletion range (inclusive)
            end_date: End date for deletion range (inclusive)
            sensor_ids: Optional list of sensor IDs to limit deletion to
            
        Returns:
            dict: Results of the deletion operation including:
                - success: bool indicating if operation was successful
                - records_deleted: int number of records deleted
                - date_range: dict with start_date and end_date used
                - sensor_ids: list of sensor IDs processed (or None for all)
                - error_message: str error message if operation failed
        """
        log_info(f"Starting date range deletion from {start_date} to {end_date}", "delete_readings_by_date_range")
        
        try:
            with get_db_session_context() as session:
                # Build query for the date range
                query = session.query(SensorReading).filter(
                    and_(
                        SensorReading.timestamp >= start_date,
                        SensorReading.timestamp <= end_date
                    )
                )
                
                # Apply sensor filter if provided
                if sensor_ids:
                    query = query.filter(SensorReading.sensor_id.in_(sensor_ids))
                
                # Count records to be deleted
                records_to_delete = query.count()
                
                if records_to_delete == 0:
                    log_info(f"No records found in date range {start_date} to {end_date}", "delete_readings_by_date_range")
                    return {
                        'success': True,
                        'records_deleted': 0,
                        'date_range': {'start_date': start_date, 'end_date': end_date},
                        'sensor_ids': sensor_ids,
                        'error_message': None
                    }
                
                log_info(f"Found {records_to_delete} records to delete in date range", "delete_readings_by_date_range")
                
                # Delete the records
                deleted_count = query.delete()
                session.commit()
                
                log_info(f"Successfully deleted {deleted_count} readings in date range", "delete_readings_by_date_range")
                
                return {
                    'success': True,
                    'records_deleted': deleted_count,
                    'date_range': {'start_date': start_date, 'end_date': end_date},
                    'sensor_ids': sensor_ids,
                    'error_message': None
                }
                
        except SQLAlchemyError as e:
            error_id = handle_polling_error(e, f"Database error during date range deletion")
            error_msg = f"Database error during date range deletion with error ID: {error_id}"
            log_warning(error_msg, "delete_readings_by_date_range")
            
            return {
                'success': False,
                'records_deleted': 0,
                'date_range': {'start_date': start_date, 'end_date': end_date},
                'sensor_ids': sensor_ids,
                'error_message': error_msg
            }
            
        except Exception as e:
            error_id = handle_polling_error(e, f"Unexpected error during date range deletion")
            error_msg = f"Unexpected error during date range deletion with error ID: {error_id}"
            log_warning(error_msg, "delete_readings_by_date_range")
            
            return {
                'success': False,
                'records_deleted': 0,
                'date_range': {'start_date': start_date, 'end_date': end_date},
                'sensor_ids': sensor_ids,
                'error_message': error_msg
            }
    
    def get_retention_stats(self) -> Dict[str, Any]:
        """
        Get statistics about current data retention and storage.
        
        This method delegates to the module-level function for backward compatibility.
        
        Returns:
            dict: Statistics about data retention
        """
        return get_data_retention_stats(self.config)
    
    def validate_config(self) -> Dict[str, Any]:
        """
        Validate the data retention configuration.
        
        This method delegates to the module-level function for backward compatibility.
        
        Returns:
            dict: Validation results
        """
        return validate_retention_config(self.config)
    
    def get_sensor_data_summary(self, sensor_id: str) -> Dict[str, Any]:
        """
        Get a summary of data for a specific sensor.
        
        Args:
            sensor_id: ID of the sensor to get summary for
            
        Returns:
            dict: Summary including:
                - sensor_id: str sensor ID
                - total_records: int total number of readings
                - oldest_record_date: datetime date of oldest record
                - newest_record_date: datetime date of newest record
                - date_range_days: int number of days covered by data
        """
        try:
            with get_db_session_context() as session:
                # Get record count for this sensor
                total_records = session.query(func.count(SensorReading.id)).filter(
                    SensorReading.sensor_id == sensor_id
                ).scalar() or 0
                
                # Get oldest and newest record dates for this sensor
                oldest_record = session.query(func.min(SensorReading.timestamp)).filter(
                    SensorReading.sensor_id == sensor_id
                ).scalar()
                
                newest_record = session.query(func.max(SensorReading.timestamp)).filter(
                    SensorReading.sensor_id == sensor_id
                ).scalar()
                
                # Calculate date range in days
                date_range_days = 0
                if oldest_record and newest_record:
                    date_range_days = (newest_record - oldest_record).days
                
                return {
                    'sensor_id': sensor_id,
                    'total_records': total_records,
                    'oldest_record_date': oldest_record,
                    'newest_record_date': newest_record,
                    'date_range_days': date_range_days
                }
                
        except SQLAlchemyError as e:
            error_id = handle_polling_error(e, f"Database error getting sensor summary for {sensor_id}")
            log_warning(f"Database error getting sensor summary for {sensor_id} with error ID: {error_id}", "get_sensor_data_summary")
            raise DataRetentionError(f"Failed to get sensor summary for {sensor_id}: {e}")
        except Exception as e:
            error_id = handle_polling_error(e, f"Unexpected error getting sensor summary for {sensor_id}")
            log_warning(f"Unexpected error getting sensor summary for {sensor_id} with error ID: {error_id}", "get_sensor_data_summary")
            raise DataRetentionError(f"Failed to get sensor summary for {sensor_id}: {e}")


def purge_old_readings(config_class=None) -> Dict[str, Any]:
    """
    Purge old sensor readings based on the configured retention period.
    
    This function deletes SensorReading entries older than the DATA_RETENTION_MONTHS
    configured in config.py, but ensures that at least 6 months of data are always
    retained, even if DATA_RETENTION_MONTHS is set lower than 6.
    
    Args:
        config_class: Configuration class to use (defaults to Config)
        
    Returns:
        dict: Results of the purging operation including:
            - success: bool indicating if operation was successful
            - records_deleted: int number of records deleted
            - cutoff_date: datetime cutoff date used for purging
            - retention_months: int actual retention months used
            - error_message: str error message if operation failed
            
    Raises:
        DataRetentionError: If there's an error during the purging process
    """
    config = config_class or Config
    logger = logging.getLogger(__name__)
    
    # Ensure minimum 6 months retention
    retention_months = max(config.DATA_RETENTION_MONTHS, 6)
    
    # Calculate cutoff date
    cutoff_date = datetime.utcnow() - timedelta(days=retention_months * 30)  # Approximate months to days
    
    log_info(f"Starting data purging process - retention: {retention_months} months, cutoff: {cutoff_date.isoformat()}", "purge_old_readings")
    
    try:
        with get_db_session_context() as session:
            # Count records to be deleted for logging
            records_to_delete = session.query(SensorReading).filter(
                SensorReading.timestamp < cutoff_date
            ).count()
            
            if records_to_delete == 0:
                log_info("No old records found to purge", "purge_old_readings")
                return {
                    'success': True,
                    'records_deleted': 0,
                    'cutoff_date': cutoff_date,
                    'retention_months': retention_months,
                    'error_message': None
                }
            
            log_info(f"Found {records_to_delete} records to purge (older than {cutoff_date.isoformat()})", "purge_old_readings")
            
            # Delete old records
            deleted_count = session.query(SensorReading).filter(
                SensorReading.timestamp < cutoff_date
            ).delete()
            
            # Commit the deletion
            session.commit()
            
            log_info(f"Successfully purged {deleted_count} old sensor readings", "purge_old_readings")
            
            return {
                'success': True,
                'records_deleted': deleted_count,
                'cutoff_date': cutoff_date,
                'retention_months': retention_months,
                'error_message': None
            }
            
    except SQLAlchemyError as e:
        error_id = handle_polling_error(e, "Database error during data purging")
        error_msg = f"Database error during data purging with error ID: {error_id}"
        log_warning(error_msg, "purge_old_readings")
        
        return {
            'success': False,
            'records_deleted': 0,
            'cutoff_date': cutoff_date,
            'retention_months': retention_months,
            'error_message': error_msg
        }
        
    except Exception as e:
        error_id = handle_polling_error(e, "Unexpected error during data purging")
        error_msg = f"Unexpected error during data purging with error ID: {error_id}"
        log_warning(error_msg, "purge_old_readings")
        
        return {
            'success': False,
            'records_deleted': 0,
            'cutoff_date': cutoff_date,
            'retention_months': retention_months,
            'error_message': error_msg
        }


def get_data_retention_stats(config_class=None) -> Dict[str, Any]:
    """
    Get statistics about current data retention and storage.
    
    Args:
        config_class: Configuration class to use (defaults to Config)
        
    Returns:
        dict: Statistics including:
            - total_records: int total number of sensor readings
            - oldest_record_date: datetime date of oldest record
            - newest_record_date: datetime date of newest record
            - retention_months: int configured retention months
            - effective_retention_months: int actual retention months (min 6)
            - records_eligible_for_purge: int number of records that would be purged
    """
    config = config_class or Config
    retention_months = max(config.DATA_RETENTION_MONTHS, 6)
    cutoff_date = datetime.utcnow() - timedelta(days=retention_months * 30)
    
    try:
        with get_db_session_context() as session:
            # Get total record count
            total_records = session.query(func.count(SensorReading.id)).scalar() or 0
            
            # Get oldest and newest record dates
            oldest_record = session.query(func.min(SensorReading.timestamp)).scalar()
            newest_record = session.query(func.max(SensorReading.timestamp)).scalar()
            
            # Count records eligible for purging
            records_eligible_for_purge = session.query(SensorReading).filter(
                SensorReading.timestamp < cutoff_date
            ).count()
            
            return {
                'total_records': total_records,
                'oldest_record_date': oldest_record,
                'newest_record_date': newest_record,
                'retention_months': config.DATA_RETENTION_MONTHS,
                'effective_retention_months': retention_months,
                'records_eligible_for_purge': records_eligible_for_purge,
                'cutoff_date': cutoff_date
            }
            
    except SQLAlchemyError as e:
        error_id = handle_polling_error(e, "Database error getting retention stats")
        log_warning(f"Database error getting retention stats with error ID: {error_id}", "get_data_retention_stats")
        raise DataRetentionError(f"Failed to get retention stats: {e}")
    except Exception as e:
        error_id = handle_polling_error(e, "Unexpected error getting retention stats")
        log_warning(f"Unexpected error getting retention stats with error ID: {error_id}", "get_data_retention_stats")
        raise DataRetentionError(f"Failed to get retention stats: {e}")


def validate_retention_config(config_class=None) -> Dict[str, Any]:
    """
    Validate the data retention configuration.
    
    Args:
        config_class: Configuration class to use (defaults to Config)
        
    Returns:
        dict: Validation results including:
            - is_valid: bool whether configuration is valid
            - configured_months: int configured retention months
            - effective_months: int actual retention months that will be used
            - warnings: list of warning messages
    """
    config = config_class or Config
    warnings = []
    
    configured_months = config.DATA_RETENTION_MONTHS
    effective_months = max(configured_months, 6)
    
    if configured_months < 6:
        warnings.append(f"Configured retention of {configured_months} months is below minimum. Using 6 months instead.")
    
    if configured_months > 60:  # 5 years seems like a reasonable upper limit
        warnings.append(f"Configured retention of {configured_months} months is very high. Consider storage implications.")
    
    return {
        'is_valid': True,  # Configuration is always valid due to minimum enforcement
        'configured_months': configured_months,
        'effective_months': effective_months,
        'warnings': warnings
    }