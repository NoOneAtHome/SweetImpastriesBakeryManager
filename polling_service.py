"""
API Polling Service Implementation.

This module provides a background polling service that periodically fetches
sensor data from the SensorPush API using APScheduler's BackgroundScheduler.
It also manages data retention by periodically purging old sensor readings.
"""

import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

import os
from config import Config, get_config, TestingConfig
from sensorpush_api import SensorPushAPI, SensorPushAPIError, AuthenticationError, APIConnectionError
from database import get_db_session_context
from models import Sensor, SensorReading
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_
from error_handling import handle_polling_error, log_info, log_warning, log_debug, get_error_handler
from data_retention import purge_old_readings, DataRetentionError


class PollingServiceError(Exception):
    """Base exception for polling service errors."""
    pass


class PollingService:
    """
    Background polling service for SensorPush API data collection.
    
    This service uses APScheduler to periodically call the SensorPush API
    and collect sensor samples and status information.
    """
    
    def __init__(self, config_class=None, api_client=None):
        """
        Initialize the polling service.
        
        Args:
            config_class: Configuration class to use (defaults to Config)
            api_client: SensorPush API client instance (optional, will create if not provided)
        """
        self.config = config_class or Config
        self.logger = logging.getLogger(__name__)
        
        # Initialize API client
        # Ensure that the provided config_class is always used, not the default Config
        self.api_client = api_client or SensorPushAPI(config_class)
        
        # Initialize scheduler
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        
        # Service state
        self._is_running = False
        self._job_id = 'sensorpush_polling_job'
        self._purge_job_id = 'data_retention_purge_job'
        
        # Statistics
        self._last_poll_time: Optional[datetime] = None
        self._last_purge_time: Optional[datetime] = None
        self._successful_polls = 0
        self._failed_polls = 0
        self._successful_purges = 0
        self._failed_purges = 0
        
        # Import SettingsManager and get polling interval from database
        from settings_manager import SettingsManager
        self.polling_interval = SettingsManager.get_polling_interval()
        
        log_info(f"Polling service initialized with interval: {self.polling_interval} minutes", "PollingService.__init__")
    
    def _job_listener(self, event):
        """
        Listen for job execution events and log them.
        
        Args:
            event: APScheduler job event
        """
        job_name = event.job_id
        
        if event.exception:
            error_id = handle_polling_error(event.exception, f"APScheduler job execution ({job_name})")
            log_warning(f"Job {job_name} failed with error ID: {error_id}", "PollingService._job_listener")
            
            if job_name == self._job_id:
                self._failed_polls += 1
            elif job_name == self._purge_job_id:
                self._failed_purges += 1
        else:
            log_debug(f"Job {job_name} completed successfully", "PollingService._job_listener")
            
            if job_name == self._job_id:
                self._successful_polls += 1
            elif job_name == self._purge_job_id:
                self._successful_purges += 1
    
    def _polling_job(self):
        """
        Main polling job that fetches data from SensorPush API.
        
        This method is called periodically by the scheduler to collect
        sensor samples and status information.
        """
        try:
            log_info("Starting polling job execution", "PollingService._polling_job")
            self._last_poll_time = datetime.now()
            
            # Fetch sensor samples
            try:
                log_debug("Fetching sensor samples", "PollingService._polling_job")
                samples_data = self.api_client.get_samples()
                log_info(f"Successfully retrieved samples data with {len(samples_data.get('sensors', {}))} sensors", "PollingService._polling_job")
                
                # Process and store samples data in database
                try:
                    self._process_samples_data(samples_data)
                except (SQLAlchemyError, Exception) as e:
                    error_id = handle_polling_error(e, "Processing samples data")
                    log_warning(f"Failed to process samples data with error ID: {error_id}", "PollingService._polling_job")
                    # Don't re-raise to allow status processing to continue
                
            except SensorPushAPIError as e:
                error_id = handle_polling_error(e, "Fetching sensor samples")
                log_warning(f"Failed to fetch samples with error ID: {error_id}", "PollingService._polling_job")
                raise
            
            # Fetch sensor status (temporarily disabled due to API endpoint issues)
            try:
                log_debug("Fetching sensor status", "PollingService._polling_job")
                status_data = self.api_client.get_status()
                log_info(f"Successfully retrieved status data with {len(status_data)} sensors", "PollingService._polling_job")
                self._process_status_data(status_data)
                
            except Exception as e:
                error_id = handle_polling_error(e, "Fetching sensor status")
                log_warning(f"Failed to fetch status with error ID: {error_id}", "PollingService._polling_job")
                # Don't re-raise to allow polling to continue
            
            log_info("Polling job completed successfully", "PollingService._polling_job")
            
        except AuthenticationError as e:
            error_id = handle_polling_error(e, "Authentication during polling")
            log_warning(f"Authentication error during polling with error ID: {error_id}", "PollingService._polling_job")
            # Don't re-raise authentication errors to avoid stopping the scheduler
            # The API client will attempt to re-authenticate on the next call
            
        except APIConnectionError as e:
            error_id = handle_polling_error(e, "API connection during polling")
            log_warning(f"Connection error during polling with error ID: {error_id}", "PollingService._polling_job")
            # Don't re-raise connection errors as they may be temporary
            
        except Exception as e:
            error_id = handle_polling_error(e, "Unexpected error during polling")
            log_warning(f"Unexpected error during polling with error ID: {error_id}", "PollingService._polling_job")
            # Re-raise unexpected errors to trigger the job listener
            raise
    
    def _data_purge_job(self):
        """
        Data purging job that removes old sensor readings based on retention policy.
        
        This method is called periodically by the scheduler to purge old data
        according to the configured DATA_RETENTION_MONTHS setting.
        """
        try:
            log_info("Starting data purge job execution", "PollingService._data_purge_job")
            self._last_purge_time = datetime.now()
            
            # Execute the data purging
            purge_result = purge_old_readings(self.config)
            
            if purge_result['success']:
                log_info(
                    f"Data purge completed successfully: {purge_result['records_deleted']} records deleted, "
                    f"retention: {purge_result['retention_months']} months, "
                    f"cutoff: {purge_result['cutoff_date'].isoformat()}",
                    "PollingService._data_purge_job"
                )
            else:
                log_warning(
                    f"Data purge failed: {purge_result['error_message']}",
                    "PollingService._data_purge_job"
                )
                # Raise exception to trigger job listener error handling
                raise DataRetentionError(purge_result['error_message'])
                
        except DataRetentionError as e:
            error_id = handle_polling_error(e, "Data retention error during purge job")
            log_warning(f"Data retention error during purge job with error ID: {error_id}", "PollingService._data_purge_job")
            raise
            
        except Exception as e:
            error_id = handle_polling_error(e, "Unexpected error during data purge job")
            log_warning(f"Unexpected error during data purge job with error ID: {error_id}", "PollingService._data_purge_job")
            raise
    
    def _get_sensor_names(self) -> Dict[str, str]:
        """
        Fetch sensor names from the SensorPush API.
        
        Returns:
            dict: Mapping of sensor_id to sensor name
        """
        try:
            sensors_metadata = self.api_client.get_sensors()
            sensor_names = {}
            
            for sensor_id, sensor_info in sensors_metadata.items():
                # Extract sensor name from the metadata
                sensor_name = sensor_info.get('name', f'Sensor {sensor_id}')
                sensor_names[sensor_id] = sensor_name
                
            log_debug(f"Retrieved names for {len(sensor_names)} sensors", "PollingService._get_sensor_names")
            return sensor_names
            
        except Exception as e:
            log_warning(f"Failed to fetch sensor names: {e}. Will use generic names.", "PollingService._get_sensor_names")
            return {}
    
    def _process_samples_data(self, samples_data: Dict[str, Any]):
        """
        Process and store sensor samples data in the database.
        
        Args:
            samples_data: Raw samples data from the SensorPush API
        """
        try:
            with get_db_session_context() as session:
                sensors_data = samples_data.get('sensors', {})
                new_readings_count = 0
                duplicate_readings_count = 0
                
                # Get sensor names from API for any new sensors we might need to create
                sensor_names = {}
                new_sensor_ids = []
                
                # First pass: identify sensors that don't exist in database
                for sensor_id in sensors_data.keys():
                    existing_sensor = session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
                    if not existing_sensor:
                        new_sensor_ids.append(sensor_id)
                
                # Fetch sensor names if we have new sensors to create
                if new_sensor_ids:
                    sensor_names = self._get_sensor_names()
                    log_debug(f"Fetched sensor names for {len(new_sensor_ids)} new sensors", "PollingService._process_samples_data")
                
                for sensor_id, readings in sensors_data.items():
                    if not isinstance(readings, list):
                        log_warning(f"Invalid readings format for sensor {sensor_id}", "PollingService._process_samples_data")
                        continue
                    
                    # Ensure sensor exists in database (create if not exists)
                    existing_sensor = session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
                    if not existing_sensor:
                        # Use actual sensor name from API if available, otherwise fallback to generic name
                        sensor_name = sensor_names.get(sensor_id, f'Sensor {sensor_id}')
                        
                        new_sensor = Sensor(
                            sensor_id=sensor_id,
                            name=sensor_name,
                            active=True,
                            min_temp=0.0,  # Default minimum temperature
                            max_temp=50.0,  # Default maximum temperature
                            min_humidity=0.0,  # Default minimum humidity
                            max_humidity=100.0  # Default maximum humidity
                        )
                        session.add(new_sensor)
                        log_debug(f"Created new sensor {sensor_id} with name '{sensor_name}' from samples data", "PollingService._process_samples_data")
                    
                    for reading in readings:
                        try:
                            # Extract reading data
                            timestamp_str = reading.get('observed')
                            temperature = reading.get('temperature')
                            humidity = reading.get('humidity')
                            
                            if not all([timestamp_str, temperature is not None, humidity is not None]):
                                log_warning(f"Incomplete reading data for sensor {sensor_id}: {reading}", "PollingService._process_samples_data")
                                continue
                            
                            # Parse timestamp
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            
                            # Check for duplicate reading (same sensor_id and timestamp)
                            existing_reading = session.query(SensorReading).filter(
                                and_(
                                    SensorReading.sensor_id == sensor_id,
                                    SensorReading.timestamp == timestamp
                                )
                            ).first()
                            
                            if existing_reading:
                                duplicate_readings_count += 1
                                continue
                            
                            # Create new sensor reading
                            new_reading = SensorReading(
                                sensor_id=sensor_id,
                                timestamp=timestamp,
                                temperature=float(temperature),
                                humidity=float(humidity)
                            )
                            
                            session.add(new_reading)
                            new_readings_count += 1
                            
                        except (ValueError, TypeError) as e:
                            error_id = handle_polling_error(e, f"Processing reading for sensor {sensor_id}")
                            log_warning(f"Error processing reading for sensor {sensor_id} with error ID: {error_id}", "PollingService._process_samples_data")
                            continue
                
                # Commit all new readings
                session.commit()
                log_info(f"Processed samples: {new_readings_count} new readings, {duplicate_readings_count} duplicates skipped", "PollingService._process_samples_data")
                
        except SQLAlchemyError as e:
            error_id = handle_polling_error(e, "Database error processing samples data")
            log_warning(f"Database error processing samples data with error ID: {error_id}", "PollingService._process_samples_data")
            raise
        except Exception as e:
            error_id = handle_polling_error(e, "Unexpected error processing samples data")
            log_warning(f"Unexpected error processing samples data with error ID: {error_id}", "PollingService._process_samples_data")
            raise
    
    def _process_status_data(self, status_data: Dict[str, Any]):
        """
        Process and store sensor status data in the database.
        
        This method processes data from the SensorPush Status endpoint which provides
        gateway and sensor online status along with latest environmental readings.
        
        Args:
            status_data: Raw status data from the SensorPush API status endpoint
        """
        try:
            with get_db_session_context() as session:
                sensors_updated = 0
                readings_added = 0
                
                # Extract gateway status information
                gateway_connected = status_data.get('gateway_connected', False)
                timestamp = status_data.get('timestamp')
                
                log_debug(f"Processing status data: gateway_connected={gateway_connected}, timestamp={timestamp}", "PollingService._process_status_data")
                
                # Process sensor status and readings
                sensors_data = status_data.get('sensors', {})
                
                # Get sensor names from API for any new sensors we might need to create
                sensor_names = {}
                new_sensor_ids = []
                
                # First pass: identify sensors that don't exist in database
                for sensor_id in sensors_data.keys():
                    existing_sensor = session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
                    if not existing_sensor:
                        new_sensor_ids.append(sensor_id)
                
                # Fetch sensor names if we have new sensors to create
                if new_sensor_ids:
                    sensor_names = self._get_sensor_names()
                    log_debug(f"Fetched sensor names for {len(new_sensor_ids)} new sensors", "PollingService._process_status_data")
                
                for sensor_id, sensor_status in sensors_data.items():
                    try:
                        # Extract sensor status information
                        temperature = sensor_status.get('temperature')
                        humidity = sensor_status.get('humidity')
                        battery = sensor_status.get('battery')
                        signal_strength = sensor_status.get('signal_strength')
                        sensor_active_status = sensor_status.get('status', 'unknown')
                        
                        # Check if sensor exists in database
                        existing_sensor = session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
                        
                        if existing_sensor:
                            # Update sensor active status based on status endpoint
                            sensor_is_active = sensor_active_status.lower() == 'active'
                            if existing_sensor.active != sensor_is_active:
                                existing_sensor.active = sensor_is_active
                                sensors_updated += 1
                                log_debug(f"Updated sensor {sensor_id} active status: {sensor_is_active}", "PollingService._process_status_data")
                        else:
                            # Create new sensor if it doesn't exist (use actual name from API)
                            sensor_is_active = sensor_active_status.lower() == 'active'
                            # Use actual sensor name from API if available, otherwise fallback to generic name
                            sensor_name = sensor_names.get(sensor_id, f'Sensor {sensor_id}')
                            
                            new_sensor = Sensor(
                                sensor_id=sensor_id,
                                name=sensor_name,
                                active=sensor_is_active,
                                min_temp=0.0,  # Default minimum temperature
                                max_temp=50.0,  # Default maximum temperature
                                min_humidity=0.0,  # Default minimum humidity
                                max_humidity=100.0  # Default maximum humidity
                            )
                            session.add(new_sensor)
                            sensors_updated += 1
                            log_info(f"Created new sensor {sensor_id} with name '{sensor_name}' from status data (status: {sensor_active_status})", "PollingService._process_status_data")
                        
                        # Add current reading if temperature and humidity are available
                        if temperature is not None and humidity is not None and timestamp:
                            try:
                                # Parse timestamp (assuming Unix timestamp)
                                if isinstance(timestamp, (int, float)):
                                    reading_timestamp = datetime.fromtimestamp(timestamp)
                                else:
                                    # Try to parse as ISO format if it's a string
                                    reading_timestamp = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
                                
                                # Check for duplicate reading
                                existing_reading = session.query(SensorReading).filter(
                                    and_(
                                        SensorReading.sensor_id == sensor_id,
                                        SensorReading.timestamp == reading_timestamp
                                    )
                                ).first()
                                
                                if not existing_reading:
                                    # Create new sensor reading from status data
                                    new_reading = SensorReading(
                                        sensor_id=sensor_id,
                                        timestamp=reading_timestamp,
                                        temperature=float(temperature),
                                        humidity=float(humidity)
                                    )
                                    session.add(new_reading)
                                    readings_added += 1
                                    log_debug(f"Added reading from status for sensor {sensor_id}: T={temperature}°C, H={humidity}%", "PollingService._process_status_data")
                                
                            except (ValueError, TypeError) as e:
                                error_id = handle_polling_error(e, f"Processing status reading for sensor {sensor_id}")
                                log_warning(f"Error processing status reading for sensor {sensor_id} with error ID: {error_id}", "PollingService._process_status_data")
                    
                    except (ValueError, TypeError) as e:
                        error_id = handle_polling_error(e, f"Processing status for sensor {sensor_id}")
                        log_warning(f"Error processing status for sensor {sensor_id} with error ID: {error_id}", "PollingService._process_status_data")
                        continue
                
                # Commit all changes
                session.commit()
                
                log_info(f"Processed status: {sensors_updated} sensors updated, {readings_added} readings added, gateway_connected={gateway_connected}", "PollingService._process_status_data")
                
        except SQLAlchemyError as e:
            error_id = handle_polling_error(e, "Database error processing status data")
            log_warning(f"Database error processing status data with error ID: {error_id}", "PollingService._process_status_data")
            raise
        except Exception as e:
            error_id = handle_polling_error(e, "Unexpected error processing status data")
            log_warning(f"Unexpected error processing status data with error ID: {error_id}", "PollingService._process_status_data")
            raise
    
    def start(self) -> bool:
        """
        Start the polling service.
        
        Returns:
            bool: True if service started successfully, False otherwise
            
        Raises:
            PollingServiceError: If service fails to start
        """
        if self._is_running:
            self.logger.warning("Polling service is already running")
            return True
        
        try:
            log_info("Starting polling service", "PollingService.start")
            
            # Validate configuration
            missing_vars = self.config.validate_required_config()
            if missing_vars:
                raise PollingServiceError(
                    f"Cannot start polling service - missing configuration: {', '.join(missing_vars)}"
                )
            
            # Test API connection before starting scheduler
            try:
                log_info("Testing API connection before starting polling", "PollingService.start")
                if not self.api_client.authenticate():
                    raise PollingServiceError("Failed to authenticate with SensorPush API")
                log_info("API authentication successful", "PollingService.start")
            except Exception as e:
                error_id = handle_polling_error(e, "API connection test during service start")
                raise PollingServiceError(f"API connection test failed with error ID {error_id}: {e}")
            
            # Add polling job to scheduler
            self.scheduler.add_job(
                func=self._polling_job,
                trigger=IntervalTrigger(minutes=self.polling_interval),
                id=self._job_id,
                name='SensorPush API Polling Job',
                replace_existing=True,
                max_instances=1  # Prevent overlapping job executions
            )
            
            # Add data purging job to scheduler (runs daily at 2 AM)
            self.scheduler.add_job(
                func=self._data_purge_job,
                trigger=CronTrigger(hour=2, minute=0),  # Daily at 2:00 AM
                id=self._purge_job_id,
                name='Data Retention Purge Job',
                replace_existing=True,
                max_instances=1  # Prevent overlapping job executions
            )
            
            # Start the scheduler
            self.scheduler.start()
            self._is_running = True
            
            log_info(f"Polling service started successfully with {self.config.DEFAULT_POLLING_INTERVAL} minute interval", "PollingService.start")
            log_info("Data purging job scheduled to run daily at 2:00 AM", "PollingService.start")
            return True
            
        except Exception as e:
            error_id = handle_polling_error(e, "Failed to start polling service")
            log_warning(f"Failed to start polling service with error ID: {error_id}", "PollingService.start")
            self._is_running = False
            raise PollingServiceError(f"Failed to start polling service: {e}")
    
    def stop(self) -> bool:
        """
        Stop the polling service gracefully.
        
        Returns:
            bool: True if service stopped successfully, False otherwise
        """
        if not self._is_running:
            self.logger.warning("Polling service is not running")
            return True
        
        try:
            log_info("Stopping polling service", "PollingService.stop")
            
            # Remove the polling job
            if self.scheduler.get_job(self._job_id):
                self.scheduler.remove_job(self._job_id)
                log_debug("Polling job removed from scheduler", "PollingService.stop")
            
            # Remove the data purging job
            if self.scheduler.get_job(self._purge_job_id):
                self.scheduler.remove_job(self._purge_job_id)
                log_debug("Data purging job removed from scheduler", "PollingService.stop")
            
            # Shutdown the scheduler
            self.scheduler.shutdown(wait=True)
            self._is_running = False
            
            log_info("Polling service stopped successfully", "PollingService.stop")
            return True
            
        except Exception as e:
            error_id = handle_polling_error(e, "Error stopping polling service")
            log_warning(f"Error stopping polling service with error ID: {error_id}", "PollingService.stop")
            return False
    
    def is_running(self) -> bool:
        """
        Check if the polling service is currently running.
        
        Returns:
            bool: True if service is running, False otherwise
        """
        return self._is_running and self.scheduler.running
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the polling service.
        
        Returns:
            dict: Service status information
        """
        return {
            'is_running': self.is_running(),
            'polling_interval_minutes': self.polling_interval,
            'last_poll_time': self._last_poll_time.isoformat() if self._last_poll_time else None,
            'last_purge_time': self._last_purge_time.isoformat() if self._last_purge_time else None,
            'successful_polls': self._successful_polls,
            'failed_polls': self._failed_polls,
            'total_polls': self._successful_polls + self._failed_polls,
            'successful_purges': self._successful_purges,
            'failed_purges': self._failed_purges,
            'total_purges': self._successful_purges + self._failed_purges,
            'data_retention_months': self.config.DATA_RETENTION_MONTHS,
            'scheduler_running': self.scheduler.running if hasattr(self, 'scheduler') else False,
            'api_token_valid': self.api_client.is_token_valid() if self.api_client else False
        }
    
    def trigger_immediate_poll(self) -> bool:
        """
        Trigger an immediate polling job execution.
        
        Returns:
            bool: True if job was triggered successfully, False otherwise
        """
        if not self._is_running:
            self.logger.error("Cannot trigger immediate poll - service is not running")
            return False
        
        try:
            log_info("Triggering immediate polling job", "PollingService.trigger_immediate_poll")
            job = self.scheduler.get_job(self._job_id)
            if job:
                job.modify(next_run_time=datetime.now())
                log_info("Immediate poll triggered successfully", "PollingService.trigger_immediate_poll")
                return True
            else:
                log_warning("Polling job not found in scheduler", "PollingService.trigger_immediate_poll")
                return False
                
        except Exception as e:
            error_id = handle_polling_error(e, "Failed to trigger immediate poll")
            log_warning(f"Failed to trigger immediate poll with error ID: {error_id}", "PollingService.trigger_immediate_poll")
            return False
    
    def trigger_immediate_purge(self) -> bool:
        """
        Trigger an immediate data purge job execution.
        
        Returns:
            bool: True if job was triggered successfully, False otherwise
        """
        if not self._is_running:
            self.logger.error("Cannot trigger immediate purge - service is not running")
            return False
        
        try:
            log_info("Triggering immediate data purge job", "PollingService.trigger_immediate_purge")
            job = self.scheduler.get_job(self._purge_job_id)
            if job:
                job.modify(next_run_time=datetime.now())
                log_info("Immediate purge triggered successfully", "PollingService.trigger_immediate_purge")
                return True
            else:
                log_warning("Data purge job not found in scheduler", "PollingService.trigger_immediate_purge")
                return False
                
        except Exception as e:
            error_id = handle_polling_error(e, "Failed to trigger immediate purge")
            log_warning(f"Failed to trigger immediate purge with error ID: {error_id}", "PollingService.trigger_immediate_purge")
            return False
    
    def update_polling_interval(self, interval_minutes: int) -> bool:
        """
        Update the polling interval while the service is running.
        
        Args:
            interval_minutes: New polling interval in minutes
            
        Returns:
            bool: True if interval updated successfully, False otherwise
        """
        if interval_minutes <= 0:
            self.logger.error("Polling interval must be greater than 0")
            return False
        
        try:
            log_info(f"Updating polling interval to {interval_minutes} minutes", "PollingService.update_polling_interval")
            
            # Update the instance variable
            self.polling_interval = interval_minutes
            
            if self._is_running:
                # Update the existing job
                job = self.scheduler.get_job(self._job_id)
                if job:
                    job.reschedule(trigger=IntervalTrigger(minutes=interval_minutes))
                    log_info(f"Polling interval updated to {interval_minutes} minutes", "PollingService.update_polling_interval")
                    return True
                else:
                    log_warning("Polling job not found in scheduler", "PollingService.update_polling_interval")
                    return False
            else:
                log_info("Service not running - interval will be used when service starts", "PollingService.update_polling_interval")
                return True
                
        except Exception as e:
            error_id = handle_polling_error(e, "Failed to update polling interval")
            log_warning(f"Failed to update polling interval with error ID: {error_id}", "PollingService.update_polling_interval")
            return False
    
    def close(self):
        """Clean up resources and close the polling service."""
        log_info("Closing polling service", "PollingService.close")
        
        # Stop the service if running
        if self._is_running:
            self.stop()
        
        # Close API client
        if self.api_client:
            self.api_client.close()
        
        log_info("Polling service closed", "PollingService.close")


# Convenience function for creating polling service
def create_polling_service(config_class=None, api_client=None) -> PollingService:
    """
    Create a polling service instance.
    
    Args:
        config_class: Configuration class to use (defaults to Config)
        api_client: SensorPush API client instance (optional)
        
    Returns:
        PollingService: Configured polling service instance
    """
    return PollingService(config_class, api_client)


# Example usage and testing function
def test_polling_service():
    """
    Test function to verify polling service works.
    This can be used for debugging and validation.
    """
    import time
    
    # Configure logging for testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Testing polling service")
        
        # Create polling service
        service = create_polling_service()
        
        # Start the service
        if service.start():
            logger.info("Polling service started successfully")
            
            # Let it run for a short time
            logger.info("Letting service run for 30 seconds...")
            time.sleep(30)
            
            # Check status
            status = service.get_status()
            logger.info(f"Service status: {status}")
            
            # Trigger immediate poll
            service.trigger_immediate_poll()
            time.sleep(5)
            
            # Stop the service
            if service.stop():
                logger.info("Polling service stopped successfully")
            else:
                logger.error("Failed to stop polling service")
        else:
            logger.error("Failed to start polling service")
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
    finally:
        # Clean up
        if 'service' in locals():
            service.close()


if __name__ == "__main__":
    test_polling_service()