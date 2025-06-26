"""
Error Handling and Logging Implementation for the Bakery Sensors application.

This module provides centralized error handling, logging configuration, and
error storage functionality for the entire application.
"""

import logging
import traceback
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError
from config import get_config
from database import get_db_session_context
from models import Error


class ErrorHandler:
    """
    Centralized error handler for the Bakery Sensors application.
    
    This class provides methods to log errors, store them in the database,
    and generate user-friendly error messages with unique error IDs.
    """
    
    def __init__(self, config_class=None):
        """
        Initialize the error handler.
        
        Args:
            config_class: Configuration class to use (defaults to current config)
        """
        self.config = config_class or get_config()
        self.logger = self._setup_logging()
        
    def _setup_logging(self) -> logging.Logger:
        """
        Set up logging configuration based on config settings.
        
        Returns:
            logging.Logger: Configured logger instance
        """
        # Create logger
        logger = logging.getLogger('bakery_sensors')
        
        # Avoid adding multiple handlers if already configured
        if logger.handlers:
            return logger
            
        # Set log level
        log_level = getattr(logging, self.config.LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(log_level)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Create file handler
        try:
            file_handler = logging.FileHandler(self.config.LOG_FILE, encoding='utf-8')
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            # Fallback to console if file logging fails
            print(f"Warning: Could not set up file logging: {e}")
            
        # Create console handler for development
        if self.config.DEBUG:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
            
        # Prevent propagation to root logger
        logger.propagate = False
        
        return logger
    
    def generate_error_id(self) -> str:
        """
        Generate a unique error ID.
        
        Returns:
            str: Unique error ID in format 'ERR-XXXXXXXX'
        """
        return f"ERR-{uuid.uuid4().hex[:8].upper()}"
    
    def log_and_store_error(
        self,
        exception: Exception,
        context: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
        level: Optional[str] = None,
        source: Optional[str] = None
    ) -> str:
        """
        Log an error and store it in the database.
        
        Args:
            exception: The exception that occurred
            context: Additional context about where the error occurred
            additional_data: Additional data to include in the error message
            level: Error level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            source: Source of the error (e.g., 'polling_service', 'web_interface', 'api')
            
        Returns:
            str: Unique error ID for the stored error
        """
        error_id = self.generate_error_id()
        
        # Get stack trace
        stack_trace = traceback.format_exc()
        
        # Build error message
        error_message = str(exception)
        if context:
            error_message = f"{context}: {error_message}"
        if additional_data:
            error_message += f" | Additional data: {additional_data}"
            
        # Log the error
        self.logger.error(
            f"Error {error_id}: {error_message}\n"
            f"Stack trace:\n{stack_trace}"
        )
        
        # Determine error level if not provided
        if level is None:
            # Map exception types to appropriate levels
            if isinstance(exception, (ValueError, TypeError, AttributeError)):
                level = 'ERROR'
            elif isinstance(exception, (ConnectionError, TimeoutError)):
                level = 'CRITICAL'
            elif isinstance(exception, Warning):
                level = 'WARNING'
            else:
                level = 'ERROR'
        
        # Determine source if not provided
        if source is None:
            source = context if context else 'application'
        
        # Store in database
        try:
            self._store_error_in_db(error_id, error_message, stack_trace, level, source)
        except Exception as db_error:
            # If we can't store in DB, at least log it
            self.logger.critical(
                f"Failed to store error {error_id} in database: {db_error}\n"
                f"Original error: {error_message}"
            )
        
        return error_id
    
    def _store_error_in_db(self, error_id: str, message: str, stack_trace: str, level: str = 'ERROR', source: str = 'application'):
        """
        Store error information in the database.
        
        Args:
            error_id: Unique error identifier
            message: Error message
            stack_trace: Full stack trace
            level: Error level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            source: Source of the error
        """
        try:
            with get_db_session_context() as session:
                error_record = Error(
                    error_id=error_id,
                    message=message,
                    stack_trace=stack_trace,
                    level=level,
                    source=source,
                    timestamp=datetime.utcnow()
                )
                session.add(error_record)
                session.commit()
                
        except SQLAlchemyError as e:
            # Re-raise SQLAlchemy errors so caller can handle them
            raise e
    
    def get_user_friendly_error(self, error_id: str) -> Dict[str, Any]:
        """
        Generate a user-friendly error response.
        
        Args:
            error_id: The unique error ID
            
        Returns:
            dict: User-friendly error response
        """
        return {
            'success': False,
            'error': 'An internal error occurred',
            'error_id': error_id,
            'message': f'Please contact support with error ID: {error_id}'
        }
    
    def log_info(self, message: str, context: Optional[str] = None):
        """
        Log an informational message.
        
        Args:
            message: The message to log
            context: Optional context information
        """
        log_message = f"{context}: {message}" if context else message
        self.logger.info(log_message)
    
    def log_warning(self, message: str, context: Optional[str] = None):
        """
        Log a warning message.
        
        Args:
            message: The message to log
            context: Optional context information
        """
        log_message = f"{context}: {message}" if context else message
        self.logger.warning(log_message)
    
    def log_debug(self, message: str, context: Optional[str] = None):
        """
        Log a debug message.
        
        Args:
            message: The message to log
            context: Optional context information
        """
        log_message = f"{context}: {message}" if context else message
        self.logger.debug(log_message)


# Global error handler instance
_error_handler = None


def get_error_handler() -> ErrorHandler:
    """
    Get the global error handler instance.
    
    Returns:
        ErrorHandler: Global error handler instance
    """
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler()
    return _error_handler


@contextmanager
def error_context(context_name: str, additional_data: Optional[Dict[str, Any]] = None):
    """
    Context manager for handling errors with automatic logging and storage.
    
    Args:
        context_name: Name of the context where errors might occur
        additional_data: Additional data to include if an error occurs
        
    Yields:
        str: Error ID if an error occurs, None otherwise
        
    Example:
        with error_context("API call", {"endpoint": "/api/sensors"}) as error_id:
            if error_id:
                return get_error_handler().get_user_friendly_error(error_id)
            # Your code here
    """
    error_id = None
    try:
        yield error_id
    except Exception as e:
        error_handler = get_error_handler()
        error_id = error_handler.log_and_store_error(e, context_name, additional_data)
        # Re-raise the exception so the caller can handle it
        raise


def handle_flask_error(exception: Exception, context: str = "Flask request") -> tuple:
    """
    Handle Flask application errors and return appropriate response.
    
    Args:
        exception: The exception that occurred
        context: Context where the error occurred
        
    Returns:
        tuple: (response_dict, status_code)
    """
    error_handler = get_error_handler()
    error_id = error_handler.log_and_store_error(exception, context)
    
    # Determine status code based on exception type
    if isinstance(exception, ValueError):
        status_code = 400
    elif isinstance(exception, FileNotFoundError):
        status_code = 404
    elif isinstance(exception, PermissionError):
        status_code = 403
    else:
        status_code = 500
    
    return error_handler.get_user_friendly_error(error_id), status_code


def handle_polling_error(exception: Exception, context: str = "Polling service") -> str:
    """
    Handle polling service errors and return error ID.
    
    Args:
        exception: The exception that occurred
        context: Context where the error occurred
        
    Returns:
        str: Unique error ID
    """
    error_handler = get_error_handler()
    return error_handler.log_and_store_error(exception, context)


# Convenience functions for logging
def log_info(message: str, context: Optional[str] = None):
    """Log an informational message."""
    get_error_handler().log_info(message, context)


def log_warning(message: str, context: Optional[str] = None):
    """Log a warning message."""
    get_error_handler().log_warning(message, context)


def log_debug(message: str, context: Optional[str] = None):
    """Log a debug message."""
    get_error_handler().log_debug(message, context)


def log_error(exception: Exception, context: Optional[str] = None, additional_data: Optional[Dict[str, Any]] = None, level: Optional[str] = None, source: Optional[str] = None) -> str:
    """
    Log and store an error, returning the error ID.
    
    Args:
        exception: The exception that occurred
        context: Context where the error occurred
        additional_data: Additional data to include
        level: Error level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        source: Source of the error
        
    Returns:
        str: Unique error ID
    """
    return get_error_handler().log_and_store_error(exception, context, additional_data, level, source)