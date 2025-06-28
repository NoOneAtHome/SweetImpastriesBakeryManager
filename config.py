print("Loading config.py module...")
"""
Configuration management for the Sensor Monitoring Dashboard.

This module handles loading configuration from environment variables
and provides default values for the application.
"""

import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()
logger.info("Environment variables loaded.")


class Config:
    """Base configuration class with common settings."""
    
    # SensorPush API Configuration
    SENSORPUSH_USERNAME = os.getenv('SENSORPUSH_USERNAME')
    SENSORPUSH_PASSWORD = os.getenv('SENSORPUSH_PASSWORD')
    SENSORPUSH_API_BASE_URL = os.getenv('SENSORPUSH_API_BASE_URL', 'https://api.sensorpush.com/api/v1')
    logger.info(f"Config - SENSORPUSH_USERNAME: {bool(SENSORPUSH_USERNAME)}")
    logger.info(f"Config - SENSORPUSH_PASSWORD: {bool(SENSORPUSH_PASSWORD)}")
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    DEBUG = os.getenv('DEBUG', 'False').lower() in ['true', '1', 'yes']
    
    # Database Configuration
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///db/sensor_dashboard.db')
    
    # Application Settings
    DEFAULT_POLLING_INTERVAL = int(os.getenv('DEFAULT_POLLING_INTERVAL', '1'))  # minutes
    DATA_RETENTION_MONTHS = int(os.getenv('DATA_RETENTION_MONTHS', '12'))  # months
    
    # Manager Authentication
    MANAGER_PIN_HASH = os.getenv('MANAGER_PIN_HASH')  # Hashed PIN for manager access
    SESSION_TIMEOUT = int(os.getenv('SESSION_TIMEOUT', '3600'))  # seconds (1 hour)
    MAX_LOGIN_ATTEMPTS = int(os.getenv('MAX_LOGIN_ATTEMPTS', '4'))
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG')
    LOG_FILE = os.getenv('LOG_FILE', 'sensor_dashboard.log')
    
    @classmethod
    def validate_required_config(cls):
        """
        Validate that all required configuration variables are set.
        
        Returns:
            list: List of missing required configuration variables
        """
        missing_vars = []
        
        if not cls.SENSORPUSH_USERNAME:
            missing_vars.append('SENSORPUSH_USERNAME')
            logger.warning("SENSORPUSH_USERNAME is not set.")
        
        if not cls.SENSORPUSH_PASSWORD:
            missing_vars.append('SENSORPUSH_PASSWORD')
            logger.warning("SENSORPUSH_PASSWORD is not set.")
        
        return missing_vars
    
    @classmethod
    def get_config_summary(cls):
        """
        Get a summary of current configuration (excluding sensitive data).
        
        Returns:
            dict: Configuration summary
        """
        return {
            'sensorpush_api_url': cls.SENSORPUSH_API_BASE_URL,
            'sensorpush_username_set': bool(cls.SENSORPUSH_USERNAME),
            'sensorpush_password_set': bool(cls.SENSORPUSH_PASSWORD),
            'flask_env': cls.FLASK_ENV,
            'debug': cls.DEBUG,
            'database_url': cls.DATABASE_URL,
            'polling_interval': cls.DEFAULT_POLLING_INTERVAL,
            'data_retention_months': cls.DATA_RETENTION_MONTHS,
            'session_timeout': cls.SESSION_TIMEOUT,
            'max_login_attempts': cls.MAX_LOGIN_ATTEMPTS,
            'log_level': cls.LOG_LEVEL,
            'manager_pin_configured': bool(cls.MANAGER_PIN_HASH)
        }


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    FLASK_ENV = 'development'


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    FLASK_ENV = 'production'
    
    @classmethod
    def validate_required_config(cls):
        """Additional validation for production environment."""
        missing_vars = super().validate_required_config()
        
        if cls.SECRET_KEY == 'dev-secret-key-change-in-production':
            missing_vars.append('SECRET_KEY (using default dev key)')
        
        # Only require MANAGER_PIN_HASH if MANAGER_PIN is not provided
        manager_pin = os.getenv('MANAGER_PIN')
        if not cls.MANAGER_PIN_HASH and not manager_pin:
            missing_vars.append('MANAGER_PIN_HASH (or MANAGER_PIN for initial setup)')
        
        return missing_vars


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True
    DATABASE_URL = 'sqlite:///:memory:'  # In-memory database for tests
    DEFAULT_POLLING_INTERVAL = 1  # Faster polling for tests
    # Explicitly define these for testing to avoid reliance on os.getenv at import time
    SENSORPUSH_USERNAME = 'test_user'
    SENSORPUSH_PASSWORD = 'test_password'
    SECRET_KEY = 'test-secret-key'
    FLASK_ENV = 'testing'
    
    # Add __name__ attribute for Flask compatibility
    __name__ = 'TestingConfig'
    
    @classmethod
    def validate_required_config(cls):
        """Override validation for testing - credentials are always set."""
        # In testing, we always have valid credentials set
        return []


# Configuration mapping
config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(config_name=None):
    """
    Get configuration class based on environment or provided name.
    
    Args:
        config_name (str, optional): Configuration name. If None, uses FLASK_ENV.
    
    Returns:
        Config: Configuration class
    """
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')
    
    return config_map.get(config_name, config_map['default'])