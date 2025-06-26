"""
Unit tests for the error handling module.

Tests error logging, storage, and handler functionality in isolation using mocks.
"""

import pytest
import logging
import uuid
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock, mock_open
from sqlalchemy.exc import SQLAlchemyError

from error_handling import (
    ErrorHandler,
    get_error_handler,
    error_context,
    handle_flask_error,
    handle_polling_error,
    log_info,
    log_warning,
    log_debug,
    log_error
)
from config import TestingConfig


@pytest.mark.unit
class TestErrorHandler:
    """Test the ErrorHandler class."""
    
    def test_error_handler_init_default_config(self):
        """Test ErrorHandler initialization with default config."""
        with patch('error_handling.get_config') as mock_get_config:
            mock_config = Mock()
            mock_config.LOG_LEVEL = 'INFO'
            mock_config.LOG_FILE = 'test.log'
            mock_config.DEBUG = False
            mock_get_config.return_value = mock_config
            
            with patch.object(ErrorHandler, '_setup_logging') as mock_setup:
                mock_logger = Mock()
                mock_setup.return_value = mock_logger
                
                handler = ErrorHandler()
                
                assert handler.config == mock_config
                assert handler.logger == mock_logger
                mock_setup.assert_called_once()
    
    def test_error_handler_init_custom_config(self, test_config):
        """Test ErrorHandler initialization with custom config."""
        with patch.object(ErrorHandler, '_setup_logging') as mock_setup:
            mock_logger = Mock()
            mock_setup.return_value = mock_logger
            
            handler = ErrorHandler(config_class=test_config)
            
            assert handler.config == test_config
            assert handler.logger == mock_logger
    
    def test_setup_logging_basic_configuration(self, test_config):
        """Test basic logging setup."""
        test_config.LOG_LEVEL = 'DEBUG'
        test_config.LOG_FILE = 'test.log'
        test_config.DEBUG = True
        
        with patch('error_handling.logging.getLogger') as mock_get_logger, \
             patch('error_handling.logging.FileHandler') as mock_file_handler, \
             patch('error_handling.logging.StreamHandler') as mock_stream_handler:
            
            mock_logger = Mock()
            mock_logger.handlers = []  # No existing handlers
            mock_get_logger.return_value = mock_logger
            
            handler = ErrorHandler(config_class=test_config)
            
            # Verify logger configuration
            mock_logger.setLevel.assert_called_with(logging.DEBUG)
            mock_file_handler.assert_called_once()
            mock_stream_handler.assert_called_once()  # Debug mode adds console handler
    
    def test_setup_logging_existing_handlers(self, test_config):
        """Test logging setup when handlers already exist."""
        with patch('error_handling.logging.getLogger') as mock_get_logger:
            mock_logger = Mock()
            mock_logger.handlers = [Mock()]  # Existing handler
            mock_get_logger.return_value = mock_logger
            
            handler = ErrorHandler(config_class=test_config)
            
            # Should return existing logger without modification
            assert handler.logger == mock_logger
    
    def test_setup_logging_file_handler_error(self, test_config):
        """Test logging setup when file handler creation fails."""
        test_config.LOG_LEVEL = 'INFO'
        test_config.LOG_FILE = '/invalid/path/test.log'
        test_config.DEBUG = False
        
        with patch('error_handling.logging.getLogger') as mock_get_logger, \
             patch('error_handling.logging.FileHandler') as mock_file_handler, \
             patch('builtins.print') as mock_print:
            
            mock_logger = Mock()
            mock_logger.handlers = []
            mock_get_logger.return_value = mock_logger
            mock_file_handler.side_effect = Exception("File creation failed")
            
            handler = ErrorHandler(config_class=test_config)
            
            # Should print warning but continue
            mock_print.assert_called_once()
            assert "Could not set up file logging" in str(mock_print.call_args)
    
    def test_generate_error_id(self, test_config):
        """Test error ID generation."""
        handler = ErrorHandler(config_class=test_config)
        
        error_id = handler.generate_error_id()
        
        assert error_id.startswith('ERR-')
        assert len(error_id) == 12  # ERR- + 8 hex chars
        
        # Generate another to ensure uniqueness
        error_id2 = handler.generate_error_id()
        assert error_id != error_id2
    
    def test_log_and_store_error_success(self, test_config):
        """Test successful error logging and storage."""
        with patch.object(ErrorHandler, '_store_error_in_db') as mock_store:
            handler = ErrorHandler(config_class=test_config)
            handler.logger = Mock()
            
            exception = ValueError("Test error")
            context = "Test context"
            additional_data = {"key": "value"}
            
            error_id = handler.log_and_store_error(exception, context, additional_data)
            
            assert error_id.startswith('ERR-')
            handler.logger.error.assert_called_once()
            mock_store.assert_called_once()
            
            # Verify log message content
            log_call = handler.logger.error.call_args[0][0]
            assert error_id in log_call
            assert "Test context: Test error" in log_call
            assert "Additional data" in log_call
    
    def test_log_and_store_error_db_storage_failure(self, test_config):
        """Test error logging when database storage fails."""
        with patch.object(ErrorHandler, '_store_error_in_db') as mock_store:
            handler = ErrorHandler(config_class=test_config)
            handler.logger = Mock()
            
            mock_store.side_effect = Exception("DB storage failed")
            exception = ValueError("Test error")
            
            error_id = handler.log_and_store_error(exception)
            
            # Should still return error ID and log
            assert error_id.startswith('ERR-')
            assert handler.logger.error.call_count == 1
            assert handler.logger.critical.call_count == 1
            
            # Critical log should mention DB storage failure
            critical_call = handler.logger.critical.call_args[0][0]
            assert "Failed to store error" in critical_call
    
    def test_store_error_in_db_success(self, test_config):
        """Test successful error storage in database."""
        with patch('error_handling.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            handler = ErrorHandler(config_class=test_config)
            
            handler._store_error_in_db('ERR-12345678', 'Test message', 'Stack trace')
            
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
            
            # Verify Error object creation
            error_obj = mock_session.add.call_args[0][0]
            assert error_obj.error_id == 'ERR-12345678'
            assert error_obj.message == 'Test message'
            assert error_obj.stack_trace == 'Stack trace'
    
    def test_store_error_in_db_sqlalchemy_error(self, test_config):
        """Test error storage with SQLAlchemy error."""
        with patch('error_handling.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            mock_session.commit.side_effect = SQLAlchemyError("DB error")
            
            handler = ErrorHandler(config_class=test_config)
            
            with pytest.raises(SQLAlchemyError):
                handler._store_error_in_db('ERR-12345678', 'Test message', 'Stack trace')
    
    def test_get_user_friendly_error(self, test_config):
        """Test user-friendly error response generation."""
        handler = ErrorHandler(config_class=test_config)
        
        response = handler.get_user_friendly_error('ERR-12345678')
        
        assert response['success'] is False
        assert response['error'] == 'An internal error occurred'
        assert response['error_id'] == 'ERR-12345678'
        assert 'ERR-12345678' in response['message']
    
    def test_log_info(self, test_config):
        """Test info logging."""
        handler = ErrorHandler(config_class=test_config)
        handler.logger = Mock()
        
        handler.log_info("Test message", "Test context")
        
        handler.logger.info.assert_called_once_with("Test context: Test message")
    
    def test_log_info_no_context(self, test_config):
        """Test info logging without context."""
        handler = ErrorHandler(config_class=test_config)
        handler.logger = Mock()
        
        handler.log_info("Test message")
        
        handler.logger.info.assert_called_once_with("Test message")
    
    def test_log_warning(self, test_config):
        """Test warning logging."""
        handler = ErrorHandler(config_class=test_config)
        handler.logger = Mock()
        
        handler.log_warning("Test warning", "Test context")
        
        handler.logger.warning.assert_called_once_with("Test context: Test warning")
    
    def test_log_debug(self, test_config):
        """Test debug logging."""
        handler = ErrorHandler(config_class=test_config)
        handler.logger = Mock()
        
        handler.log_debug("Test debug", "Test context")
        
        handler.logger.debug.assert_called_once_with("Test context: Test debug")


@pytest.mark.unit
class TestGlobalErrorHandler:
    """Test global error handler functionality."""
    
    def test_get_error_handler_singleton(self):
        """Test that get_error_handler returns singleton instance."""
        with patch('error_handling.ErrorHandler') as mock_handler_class:
            mock_instance = Mock()
            mock_handler_class.return_value = mock_instance
            
            # Clear global instance
            import error_handling
            error_handling._error_handler = None
            
            handler1 = get_error_handler()
            handler2 = get_error_handler()
            
            assert handler1 == handler2
            assert handler1 == mock_instance
            mock_handler_class.assert_called_once()  # Only created once
    
    def test_get_error_handler_existing_instance(self):
        """Test get_error_handler with existing instance."""
        mock_instance = Mock()
        
        import error_handling
        error_handling._error_handler = mock_instance
        
        handler = get_error_handler()
        
        assert handler == mock_instance


@pytest.mark.unit
class TestErrorContext:
    """Test the error_context context manager."""
    
    def test_error_context_no_exception(self):
        """Test error context when no exception occurs."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_get_handler.return_value = mock_handler
            
            with error_context("Test context") as error_id:
                assert error_id is None
                # Do some work without exception
                pass
            
            # Handler should not be called
            mock_handler.log_and_store_error.assert_not_called()
    
    def test_error_context_with_exception(self):
        """Test error context when exception occurs."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_handler.log_and_store_error.return_value = 'ERR-12345678'
            mock_get_handler.return_value = mock_handler
            
            test_exception = ValueError("Test error")
            
            with pytest.raises(ValueError):
                with error_context("Test context", {"key": "value"}) as error_id:
                    raise test_exception
            
            # Handler should be called with exception details
            mock_handler.log_and_store_error.assert_called_once_with(
                test_exception, "Test context", {"key": "value"}
            )
    
    def test_error_context_with_additional_data(self):
        """Test error context with additional data."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_handler.log_and_store_error.return_value = 'ERR-12345678'
            mock_get_handler.return_value = mock_handler
            
            additional_data = {"endpoint": "/api/test", "user_id": 123}
            
            with pytest.raises(RuntimeError):
                with error_context("API call", additional_data):
                    raise RuntimeError("API failed")
            
            mock_handler.log_and_store_error.assert_called_once()
            call_args = mock_handler.log_and_store_error.call_args
            assert call_args[0][1] == "API call"
            assert call_args[0][2] == additional_data


@pytest.mark.unit
class TestFlaskErrorHandling:
    """Test Flask-specific error handling."""
    
    def test_handle_flask_error_value_error(self):
        """Test Flask error handling for ValueError."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_handler.log_and_store_error.return_value = 'ERR-12345678'
            mock_handler.get_user_friendly_error.return_value = {'error': 'User friendly'}
            mock_get_handler.return_value = mock_handler
            
            exception = ValueError("Invalid input")
            
            response, status_code = handle_flask_error(exception, "Test context")
            
            assert status_code == 400
            assert response == {'error': 'User friendly'}
            mock_handler.log_and_store_error.assert_called_once_with(exception, "Test context")
    
    def test_handle_flask_error_file_not_found(self):
        """Test Flask error handling for FileNotFoundError."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_handler.log_and_store_error.return_value = 'ERR-12345678'
            mock_handler.get_user_friendly_error.return_value = {'error': 'Not found'}
            mock_get_handler.return_value = mock_handler
            
            exception = FileNotFoundError("File not found")
            
            response, status_code = handle_flask_error(exception)
            
            assert status_code == 404
            assert response == {'error': 'Not found'}
    
    def test_handle_flask_error_permission_error(self):
        """Test Flask error handling for PermissionError."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_handler.log_and_store_error.return_value = 'ERR-12345678'
            mock_handler.get_user_friendly_error.return_value = {'error': 'Forbidden'}
            mock_get_handler.return_value = mock_handler
            
            exception = PermissionError("Access denied")
            
            response, status_code = handle_flask_error(exception)
            
            assert status_code == 403
            assert response == {'error': 'Forbidden'}
    
    def test_handle_flask_error_generic_exception(self):
        """Test Flask error handling for generic exception."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_handler.log_and_store_error.return_value = 'ERR-12345678'
            mock_handler.get_user_friendly_error.return_value = {'error': 'Internal error'}
            mock_get_handler.return_value = mock_handler
            
            exception = RuntimeError("Something went wrong")
            
            response, status_code = handle_flask_error(exception)
            
            assert status_code == 500
            assert response == {'error': 'Internal error'}


@pytest.mark.unit
class TestPollingErrorHandling:
    """Test polling service error handling."""
    
    def test_handle_polling_error(self):
        """Test polling error handling."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_handler.log_and_store_error.return_value = 'ERR-12345678'
            mock_get_handler.return_value = mock_handler
            
            exception = ConnectionError("Connection failed")
            
            error_id = handle_polling_error(exception, "Polling context")
            
            assert error_id == 'ERR-12345678'
            mock_handler.log_and_store_error.assert_called_once_with(exception, "Polling context")
    
    def test_handle_polling_error_default_context(self):
        """Test polling error handling with default context."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_handler.log_and_store_error.return_value = 'ERR-87654321'
            mock_get_handler.return_value = mock_handler
            
            exception = ValueError("Invalid data")
            
            error_id = handle_polling_error(exception)
            
            assert error_id == 'ERR-87654321'
            mock_handler.log_and_store_error.assert_called_once_with(exception, "Polling service")


@pytest.mark.unit
class TestConvenienceFunctions:
    """Test convenience logging functions."""
    
    def test_log_info_function(self):
        """Test log_info convenience function."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_get_handler.return_value = mock_handler
            
            log_info("Test message", "Test context")
            
            mock_handler.log_info.assert_called_once_with("Test message", "Test context")
    
    def test_log_warning_function(self):
        """Test log_warning convenience function."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_get_handler.return_value = mock_handler
            
            log_warning("Test warning", "Test context")
            
            mock_handler.log_warning.assert_called_once_with("Test warning", "Test context")
    
    def test_log_debug_function(self):
        """Test log_debug convenience function."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_get_handler.return_value = mock_handler
            
            log_debug("Test debug", "Test context")
            
            mock_handler.log_debug.assert_called_once_with("Test debug", "Test context")
    
    def test_log_error_function(self):
        """Test log_error convenience function."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_handler.log_and_store_error.return_value = 'ERR-12345678'
            mock_get_handler.return_value = mock_handler
            
            exception = ValueError("Test error")
            additional_data = {"key": "value"}
            
            error_id = log_error(exception, "Test context", additional_data)
            
            assert error_id == 'ERR-12345678'
            mock_handler.log_and_store_error.assert_called_once_with(
                exception, "Test context", additional_data
            )


@pytest.mark.unit
class TestErrorHandlingEdgeCases:
    """Test edge cases and error scenarios."""
    
    def test_error_handler_with_none_config(self):
        """Test ErrorHandler with None config."""
        with patch('error_handling.get_config') as mock_get_config:
            mock_config = Mock()
            mock_get_config.return_value = mock_config
            
            with patch.object(ErrorHandler, '_setup_logging'):
                handler = ErrorHandler(config_class=None)
                
                assert handler.config == mock_config
                mock_get_config.assert_called_once()
    
    def test_log_and_store_error_with_none_values(self, test_config):
        """Test error logging with None values."""
        with patch.object(ErrorHandler, '_store_error_in_db'):
            handler = ErrorHandler(config_class=test_config)
            handler.logger = Mock()
            
            exception = ValueError("Test error")
            
            error_id = handler.log_and_store_error(exception, None, None)
            
            assert error_id.startswith('ERR-')
            handler.logger.error.assert_called_once()
    
    def test_setup_logging_invalid_log_level(self, test_config):
        """Test logging setup with invalid log level."""
        test_config.LOG_LEVEL = 'INVALID_LEVEL'
        test_config.LOG_FILE = 'test.log'
        test_config.DEBUG = False
        
        with patch('error_handling.logging.getLogger') as mock_get_logger:
            mock_logger = Mock()
            mock_logger.handlers = []
            mock_get_logger.return_value = mock_logger
            
            handler = ErrorHandler(config_class=test_config)
            
            # Should default to INFO level when invalid level provided
            mock_logger.setLevel.assert_called_with(logging.INFO)
    
    def test_store_error_in_db_with_unicode_content(self, test_config):
        """Test error storage with unicode content."""
        with patch('error_handling.get_db_session_context') as mock_context:
            mock_session = Mock()
            mock_context.return_value.__enter__.return_value = mock_session
            mock_context.return_value.__exit__.return_value = None
            
            handler = ErrorHandler(config_class=test_config)
            
            unicode_message = "Test message with unicode: 测试 🚀"
            unicode_stack = "Stack trace with unicode: ñáéíóú"
            
            handler._store_error_in_db('ERR-12345678', unicode_message, unicode_stack)
            
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
            
            # Verify unicode content is preserved
            error_obj = mock_session.add.call_args[0][0]
            assert error_obj.message == unicode_message
            assert error_obj.stack_trace == unicode_stack
    
    def test_error_context_nested_exceptions(self):
        """Test error context with nested exceptions."""
        with patch('error_handling.get_error_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_handler.log_and_store_error.return_value = 'ERR-12345678'
            mock_get_handler.return_value = mock_handler
            
            with pytest.raises(ValueError):
                with error_context("Outer context"):
                    try:
                        raise RuntimeError("Inner error")
                    except RuntimeError:
                        raise ValueError("Outer error")
            
            # Should log the ValueError (the one that propagated)
            mock_handler.log_and_store_error.assert_called_once()
            logged_exception = mock_handler.log_and_store_error.call_args[0][0]
            assert isinstance(logged_exception, ValueError)
            assert str(logged_exception) == "Outer error"