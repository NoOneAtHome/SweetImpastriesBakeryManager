"""
Settings Manager for the Bakery Sensors application.

This module provides functions to manage system settings that can be configured
through the manager interface, including polling intervals and other system parameters.
"""

from typing import Optional, Dict, Any
from database import get_db_session_context
from models import SystemSettings, Sensor
from error_handling import log_info, log_warning, log_debug
from sqlalchemy.exc import SQLAlchemyError


class SettingsManager:
    """
    Manager for system settings stored in the database.
    """
    
    @staticmethod
    def get_setting(key: str, default_value: str = None) -> Optional[str]:
        """
        Get a system setting value by key.
        
        Args:
            key: Setting key to retrieve
            default_value: Default value if setting doesn't exist
            
        Returns:
            Setting value or default_value if not found
        """
        try:
            with get_db_session_context() as db_session:
                setting = db_session.query(SystemSettings).filter(
                    SystemSettings.setting_key == key
                ).first()
                
                if setting:
                    return setting.setting_value
                return default_value
                
        except SQLAlchemyError as e:
            log_warning(f"Error retrieving setting '{key}': {str(e)}", "SettingsManager.get_setting")
            return default_value
    
    @staticmethod
    def set_setting(key: str, value: str, description: str = None) -> bool:
        """
        Set a system setting value.
        
        Args:
            key: Setting key
            value: Setting value
            description: Optional description of the setting
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with get_db_session_context() as db_session:
                setting = db_session.query(SystemSettings).filter(
                    SystemSettings.setting_key == key
                ).first()
                
                if setting:
                    # Update existing setting
                    setting.setting_value = value
                    if description:
                        setting.description = description
                    log_debug(f"Updated setting '{key}' to '{value}'", "SettingsManager.set_setting")
                else:
                    # Create new setting
                    setting = SystemSettings(
                        setting_key=key,
                        setting_value=value,
                        description=description
                    )
                    db_session.add(setting)
                    log_debug(f"Created new setting '{key}' with value '{value}'", "SettingsManager.set_setting")
                
                db_session.commit()
                log_info(f"Setting '{key}' updated successfully", "SettingsManager.set_setting")
                return True
                
        except SQLAlchemyError as e:
            log_warning(f"Error setting '{key}': {str(e)}", "SettingsManager.set_setting")
            return False
    
    @staticmethod
    def get_all_settings() -> Dict[str, Any]:
        """
        Get all system settings as a dictionary.
        
        Returns:
            Dictionary of all settings with their values and metadata
        """
        try:
            with get_db_session_context() as db_session:
                settings = db_session.query(SystemSettings).all()
                
                result = {}
                for setting in settings:
                    result[setting.setting_key] = {
                        'value': setting.setting_value,
                        'description': setting.description,
                        'updated_at': setting.updated_at
                    }
                
                return result
                
        except SQLAlchemyError as e:
            log_warning(f"Error retrieving all settings: {str(e)}", "SettingsManager.get_all_settings")
            return {}
    
    @staticmethod
    def get_polling_interval() -> int:
        """
        Get the current polling interval in minutes.
        
        Returns:
            Polling interval in minutes (defaults to 1 if not set)
        """
        interval_str = SettingsManager.get_setting('polling_interval_minutes', '1')
        try:
            return int(interval_str)
        except ValueError:
            log_warning(f"Invalid polling interval value: {interval_str}, using default", "SettingsManager.get_polling_interval")
            return 1
    
    @staticmethod
    def set_polling_interval(minutes: int) -> bool:
        """
        Set the polling interval in minutes.
        
        Args:
            minutes: Polling interval in minutes (must be >= 1)
            
        Returns:
            True if successful, False otherwise
        """
        if minutes < 1:
            log_warning(f"Invalid polling interval: {minutes} minutes (must be >= 1)", "SettingsManager.set_polling_interval")
            return False
        
        return SettingsManager.set_setting(
            'polling_interval_minutes',
            str(minutes),
            f'Polling interval for sensor data collection (minutes)'
        )

    @staticmethod
    def update_sensor_full_settings(
        sensor_id: str,
        display_name: str,
        min_temp: float,
        max_temp: float,
        min_humidity: float,
        max_humidity: float,
        category: Optional[str],
        color: Optional[str]
    ) -> bool:
        """
        Update a sensor's display name, thresholds, category, and color in a single operation.

        Args:
            sensor_id: The ID of the sensor to update.
            display_name: The new display name for the sensor.
            min_temp: The new minimum temperature threshold.
            max_temp: The new maximum temperature threshold.
            min_humidity: The new minimum humidity threshold.
            max_humidity: The new maximum humidity threshold.
            category: The new category for the sensor (can be None).
            color: The new color for the sensor (can be None).

        Returns:
            True if the update was successful, False otherwise.
        """
        try:
            with get_db_session_context() as db_session:
                sensor = db_session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()

                if not sensor:
                    log_warning(f"Sensor with ID '{sensor_id}' not found for update.", "SettingsManager.update_sensor_full_settings")
                    return False

                # Update sensor properties
                sensor.name = display_name
                sensor.min_temp = min_temp
                sensor.max_temp = max_temp
                sensor.min_humidity = min_humidity
                sensor.max_humidity = max_humidity
                sensor.category = category
                sensor.color = color

                db_session.commit()
                log_info(f"Sensor '{sensor_id}' (name: '{display_name}') settings updated successfully.", "SettingsManager.update_sensor_full_settings")
                return True

        except SQLAlchemyError as e:
            log_warning(f"Database error updating sensor '{sensor_id}' settings: {str(e)}", "SettingsManager.update_sensor_full_settings")
            # Note: db_session.rollback() is handled automatically by the context manager
            return False
        except Exception as e:
            log_warning(f"An unexpected error occurred while updating sensor '{sensor_id}' settings: {str(e)}", "SettingsManager.update_sensor_full_settings")
            return False


def check_threshold_breach(sensor, latest_reading) -> Dict[str, Any]:
    """
    Check if a sensor reading breaches its configured thresholds.
    
    Args:
        sensor: Sensor object with threshold configuration
        latest_reading: Latest sensor reading
        
    Returns:
        Dictionary with breach information
    """
    if not latest_reading:
        return {
            'has_breach': False,
            'temperature_breach': None,
            'humidity_breach': None,
            'breach_type': None
        }
    
    temp_breach = None
    humidity_breach = None
    
    # Check temperature thresholds
    if latest_reading.temperature < sensor.min_temp:
        temp_breach = 'low'
    elif latest_reading.temperature > sensor.max_temp:
        temp_breach = 'high'
    
    # Check humidity thresholds
    if latest_reading.humidity < sensor.min_humidity:
        humidity_breach = 'low'
    elif latest_reading.humidity > sensor.max_humidity:
        humidity_breach = 'high'
    
    has_breach = temp_breach is not None or humidity_breach is not None
    
    # Determine overall breach type for styling
    breach_type = None
    if has_breach:
        if temp_breach == 'high' or humidity_breach == 'high':
            breach_type = 'critical'  # High values are typically more critical
        else:
            breach_type = 'warning'   # Low values are warnings
    
    return {
        'has_breach': has_breach,
        'temperature_breach': temp_breach,
        'humidity_breach': humidity_breach,
        'breach_type': breach_type
    }