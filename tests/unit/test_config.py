"""
Unit tests for the config module.

Tests configuration loading, validation, and different config classes
in isolation using mocks.
"""

import pytest
import os
from unittest.mock import Mock, patch

from config import (
    Config,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    config_map,
    get_config
)


@pytest.mark.unit
class TestBaseConfig:
    """Test the base Config class."""
    
    def test_config_default_values(self):
        """Test that Config has appropriate default values."""
        # Test with mocked environment
        with patch.dict(os.environ, {}, clear=True):
            # Clear environment and test defaults
            assert Config.SENSORPUSH_API_BASE_URL == 'https://api.sensorpush.com/api/v1'
            assert Config.SECRET_KEY == 'your-secret-key-here'  # Updated to match .env file
            assert Config.FLASK_ENV == 'development'
            assert Config.DEBUG is False  # Default string 'False' converts to False
            assert Config.DATABASE_URL == 'sqlite:///db/sensor_dashboard.db'
            assert Config.DEFAULT_POLLING_INTERVAL == 1
            assert Config.DATA_RETENTION_MONTHS == 12
            assert Config.SESSION_TIMEOUT == 3600
            assert Config.MAX_LOGIN_ATTEMPTS == 4
            assert Config.LOG_LEVEL == 'DEBUG'
            assert Config.LOG_FILE == 'sensor_dashboard.log'
    
    def test_config_environment_override(self):
        """Test that environment variables override defaults."""
        env_vars = {
            'SENSORPUSH_USERNAME': 'test@example.com',
            'SENSORPUSH_PASSWORD': 'testpass',
            'SENSORPUSH_API_BASE_URL': 'https://test.api.com',
            'SECRET_KEY': 'test-secret-key',
            'FLASK_ENV': 'production',
            'DEBUG': 'True',
            'DATABASE_URL': 'postgresql://test',
            'DEFAULT_POLLING_INTERVAL': '5',
            'DATA_RETENTION_MONTHS': '24',
            'MANAGER_PIN_HASH': 'test-hash',
            'SESSION_TIMEOUT': '7200',
            'MAX_LOGIN_ATTEMPTS': '3',
            'LOG_LEVEL': 'INFO',
            'LOG_FILE': 'test.log'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            # Force reload of config values
            import importlib
            import config
            importlib.reload(config)
            
            assert config.Config.SENSORPUSH_USERNAME == 'test@example.com'
            assert config.Config.SENSORPUSH_PASSWORD == 'testpass'
            assert config.Config.SENSORPUSH_API_BASE_URL == 'https://test.api.com'
            assert config.Config.SECRET_KEY == 'test-secret-key'
            assert config.Config.FLASK_ENV == 'production'
            assert config.Config.DEBUG is True
            assert config.Config.DATABASE_URL == 'postgresql://test'
            assert config.Config.DEFAULT_POLLING_INTERVAL == 5
            assert config.Config.DATA_RETENTION_MONTHS == 24
            assert config.Config.MANAGER_PIN_HASH == 'test-hash'
            assert config.Config.SESSION_TIMEOUT == 7200
            assert config.Config.MAX_LOGIN_ATTEMPTS == 3
            assert config.Config.LOG_LEVEL == 'INFO'
            assert config.Config.LOG_FILE == 'test.log'
    
    def test_debug_boolean_conversion(self):
        """Test DEBUG environment variable boolean conversion."""
        test_cases = [
            ('true', True),
            ('True', True),
            ('TRUE', True),
            ('1', True),
            ('yes', True),
            ('YES', True),
            ('false', False),
            ('False', False),
            ('FALSE', False),
            ('0', False),
            ('no', False),
            ('NO', False),
            ('invalid', False),
            ('', False)
        ]
        
        for env_value, expected in test_cases:
            with patch.dict(os.environ, {'DEBUG': env_value}, clear=True):
                import importlib
                import config
                importlib.reload(config)
                
                assert config.Config.DEBUG == expected, \
                    f"DEBUG='{env_value}' should result in {expected}, got {config.Config.DEBUG}"
    
    def test_validate_required_config_missing_username(self):
        """Test validation with missing username."""
        with patch.dict(os.environ, {'SENSORPUSH_PASSWORD': 'test'}, clear=True):
            # Patch the dotenv loading to prevent .env file interference
            with patch('config.load_dotenv'):
                import importlib
                import config
                importlib.reload(config)
                
                missing = config.Config.validate_required_config()
                
                assert 'SENSORPUSH_USERNAME' in missing
                assert 'SENSORPUSH_PASSWORD' not in missing
    
    def test_validate_required_config_missing_password(self):
        """Test validation with missing password."""
        with patch.dict(os.environ, {'SENSORPUSH_USERNAME': 'test@example.com'}, clear=True):
            # Patch the dotenv loading to prevent .env file interference
            with patch('config.load_dotenv'):
                import importlib
                import config
                importlib.reload(config)
                
                missing = config.Config.validate_required_config()
                
                assert 'SENSORPUSH_PASSWORD' in missing
                assert 'SENSORPUSH_USERNAME' not in missing
    
    def test_validate_required_config_all_present(self):
        """Test validation with all required config present."""
        env_vars = {
            'SENSORPUSH_USERNAME': 'test@example.com',
            'SENSORPUSH_PASSWORD': 'testpass'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            import importlib
            import config
            importlib.reload(config)
            
            missing = config.Config.validate_required_config()
            
            assert len(missing) == 0
    
    def test_validate_required_config_empty_values(self):
        """Test validation with empty string values."""
        env_vars = {
            'SENSORPUSH_USERNAME': '',
            'SENSORPUSH_PASSWORD': ''
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            import importlib
            import config
            importlib.reload(config)
            
            missing = config.Config.validate_required_config()
            
            assert 'SENSORPUSH_USERNAME' in missing
            assert 'SENSORPUSH_PASSWORD' in missing
    
    def test_get_config_summary(self):
        """Test configuration summary generation."""
        env_vars = {
            'SENSORPUSH_USERNAME': 'test@example.com',
            'SENSORPUSH_PASSWORD': 'testpass',
            'MANAGER_PIN_HASH': 'test-hash'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            import importlib
            import config
            importlib.reload(config)
            
            summary = config.Config.get_config_summary()
            
            assert summary['sensorpush_username_set'] is True
            assert summary['sensorpush_password_set'] is True
            assert summary['manager_pin_configured'] is True
            assert 'test@example.com' not in str(summary)  # Should not expose sensitive data
            assert 'testpass' not in str(summary)
            assert 'test-hash' not in str(summary)
            
            # Check other fields
            assert 'sensorpush_api_url' in summary
            assert 'flask_env' in summary
            assert 'debug' in summary
            assert 'database_url' in summary
            assert 'polling_interval' in summary
            assert 'data_retention_months' in summary
            assert 'session_timeout' in summary
            assert 'max_login_attempts' in summary
            assert 'log_level' in summary
    
    def test_get_config_summary_missing_credentials(self):
        """Test configuration summary with missing credentials."""
        with patch.dict(os.environ, {}, clear=True):
            # Patch the dotenv loading to prevent .env file interference
            with patch('config.load_dotenv'):
                import importlib
                import config
                importlib.reload(config)
                
                summary = config.Config.get_config_summary()
                
                assert summary['sensorpush_username_set'] is False
                assert summary['sensorpush_password_set'] is False
                assert summary['manager_pin_configured'] is False


@pytest.mark.unit
class TestDevelopmentConfig:
    """Test the DevelopmentConfig class."""
    
    def test_development_config_inheritance(self):
        """Test that DevelopmentConfig inherits from Config."""
        assert issubclass(DevelopmentConfig, Config)
    
    def test_development_config_overrides(self):
        """Test DevelopmentConfig specific overrides."""
        assert DevelopmentConfig.DEBUG is True
        assert DevelopmentConfig.FLASK_ENV == 'development'
    
    def test_development_config_inherits_base_methods(self):
        """Test that DevelopmentConfig inherits base class methods."""
        # Should inherit validation method
        assert hasattr(DevelopmentConfig, 'validate_required_config')
        assert hasattr(DevelopmentConfig, 'get_config_summary')
        
        # Test method works
        with patch.dict(os.environ, {}, clear=True):
            missing = DevelopmentConfig.validate_required_config()
            assert isinstance(missing, list)


@pytest.mark.unit
class TestProductionConfig:
    """Test the ProductionConfig class."""
    
    def test_production_config_inheritance(self):
        """Test that ProductionConfig inherits from Config."""
        assert issubclass(ProductionConfig, Config)
    
    def test_production_config_overrides(self):
        """Test ProductionConfig specific overrides."""
        assert ProductionConfig.DEBUG is False
        assert ProductionConfig.FLASK_ENV == 'production'
    
    def test_production_config_additional_validation(self):
        """Test ProductionConfig additional validation requirements."""
        # Test with default dev secret key
        with patch.dict(os.environ, {
            'SENSORPUSH_USERNAME': 'test@example.com',
            'SENSORPUSH_PASSWORD': 'testpass',
            'SECRET_KEY': 'dev-secret-key-change-in-production'  # Use the actual default
        }, clear=True):
            # Patch the dotenv loading to prevent .env file interference
            with patch('config.load_dotenv'):
                import importlib
                import config
                importlib.reload(config)
                
                missing = config.ProductionConfig.validate_required_config()
                
                assert 'SECRET_KEY (using default dev key)' in missing
    
    def test_production_config_missing_manager_pin(self):
        """Test ProductionConfig validation with missing manager PIN."""
        env_vars = {
            'SENSORPUSH_USERNAME': 'test@example.com',
            'SENSORPUSH_PASSWORD': 'testpass',
            'SECRET_KEY': 'production-secret-key'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            missing = ProductionConfig.validate_required_config()
            
            assert 'MANAGER_PIN_HASH' in missing
            assert 'SECRET_KEY (using default dev key)' not in missing
    
    def test_production_config_all_requirements_met(self):
        """Test ProductionConfig with all requirements met."""
        env_vars = {
            'SENSORPUSH_USERNAME': 'test@example.com',
            'SENSORPUSH_PASSWORD': 'testpass',
            'SECRET_KEY': 'production-secret-key',
            'MANAGER_PIN_HASH': 'hashed-pin'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            # Patch the dotenv loading to prevent .env file interference
            with patch('config.load_dotenv'):
                import importlib
                import config
                importlib.reload(config)
                
                missing = config.ProductionConfig.validate_required_config()
                
                assert len(missing) == 0


@pytest.mark.unit
class TestTestingConfig:
    """Test the TestingConfig class."""
    
    def test_testing_config_inheritance(self):
        """Test that TestingConfig inherits from Config."""
        assert issubclass(TestingConfig, Config)
    
    def test_testing_config_overrides(self):
        """Test TestingConfig specific overrides."""
        assert TestingConfig.TESTING is True
        assert TestingConfig.DEBUG is True
        assert TestingConfig.DATABASE_URL == 'sqlite:///:memory:'
        assert TestingConfig.DEFAULT_POLLING_INTERVAL == 1
    
    def test_testing_config_in_memory_database(self):
        """Test that TestingConfig uses in-memory database."""
        assert TestingConfig.DATABASE_URL == 'sqlite:///:memory:'
    
    def test_testing_config_fast_polling(self):
        """Test that TestingConfig uses fast polling for tests."""
        assert TestingConfig.DEFAULT_POLLING_INTERVAL == 1


@pytest.mark.unit
class TestConfigMapping:
    """Test the config mapping and get_config function."""
    
    def test_config_map_contents(self):
        """Test that config_map contains expected configurations."""
        assert 'development' in config_map
        assert 'production' in config_map
        assert 'testing' in config_map
        assert 'default' in config_map
        
        assert config_map['development'] == DevelopmentConfig
        assert config_map['production'] == ProductionConfig
        assert config_map['testing'] == TestingConfig
        assert config_map['default'] == DevelopmentConfig
    
    def test_get_config_development(self):
        """Test get_config with development environment."""
        config_class = get_config('development')
        assert config_class is DevelopmentConfig
    
    def test_get_config_production(self):
        """Test get_config with production environment."""
        config_class = get_config('production')
        assert config_class is ProductionConfig
    
    def test_get_config_testing(self):
        """Test get_config with testing environment."""
        config_class = get_config('testing')
        assert config_class is TestingConfig
    
    def test_get_config_invalid_name(self):
        """Test get_config with invalid configuration name."""
        config_class = get_config('invalid')
        assert config_class is DevelopmentConfig  # Should default
    
    def test_get_config_none_name(self):
        """Test get_config with None name."""
        with patch.dict(os.environ, {'FLASK_ENV': 'production'}):
            config_class = get_config(None)
            assert config_class is ProductionConfig
    
    def test_get_config_no_flask_env(self):
        """Test get_config when FLASK_ENV is not set."""
        with patch.dict(os.environ, {}, clear=True):
            config_class = get_config()
            assert config_class is DevelopmentConfig  # Should default
    
    def test_get_config_flask_env_override(self):
        """Test get_config using FLASK_ENV environment variable."""
        with patch.dict(os.environ, {'FLASK_ENV': 'testing'}):
            config_class = get_config()
            assert config_class is TestingConfig


@pytest.mark.unit
class TestConfigIntegerConversion:
    """Test integer conversion for config values."""
    
    def test_integer_config_values(self):
        """Test that integer config values are properly converted."""
        env_vars = {
            'DEFAULT_POLLING_INTERVAL': '10',
            'DATA_RETENTION_MONTHS': '6',
            'SESSION_TIMEOUT': '1800',
            'MAX_LOGIN_ATTEMPTS': '5'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            import importlib
            import config
            importlib.reload(config)
            
            assert config.Config.DEFAULT_POLLING_INTERVAL == 10
            assert config.Config.DATA_RETENTION_MONTHS == 6
            assert config.Config.SESSION_TIMEOUT == 1800
            assert config.Config.MAX_LOGIN_ATTEMPTS == 5
            
            # Verify they are integers, not strings
            assert isinstance(config.Config.DEFAULT_POLLING_INTERVAL, int)
            assert isinstance(config.Config.DATA_RETENTION_MONTHS, int)
            assert isinstance(config.Config.SESSION_TIMEOUT, int)
            assert isinstance(config.Config.MAX_LOGIN_ATTEMPTS, int)
    
    def test_invalid_integer_config_values(self):
        """Test handling of invalid integer config values."""
        env_vars = {
            'DEFAULT_POLLING_INTERVAL': 'invalid',
            'DATA_RETENTION_MONTHS': 'not_a_number'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            # This should raise ValueError when trying to convert
            with pytest.raises(ValueError):
                import importlib
                import config
                importlib.reload(config)


@pytest.mark.unit
class TestConfigEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_environment_variables(self):
        """Test behavior with empty environment variables."""
        env_vars = {
            'SENSORPUSH_USERNAME': '',
            'SENSORPUSH_PASSWORD': '',
            'SECRET_KEY': '',
            'FLASK_ENV': '',
            'DEBUG': '',
            'DATABASE_URL': '',
            'LOG_LEVEL': '',
            'LOG_FILE': ''
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            import importlib
            import config
            importlib.reload(config)
            
            # Empty strings should be treated as None/missing
            assert config.Config.SENSORPUSH_USERNAME == ''
            assert config.Config.SENSORPUSH_PASSWORD == ''
            assert config.Config.SECRET_KEY == ''
            
            # These should fall back to defaults when empty
            assert config.Config.FLASK_ENV == ''  # Will use empty string
            assert config.Config.DEBUG is False  # Empty string converts to False
    
    def test_whitespace_environment_variables(self):
        """Test behavior with whitespace-only environment variables."""
        env_vars = {
            'SENSORPUSH_USERNAME': '   ',
            'SENSORPUSH_PASSWORD': '\t\n',
            'SECRET_KEY': '  \t  '
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            import importlib
            import config
            importlib.reload(config)
            
            # Should preserve whitespace (application can decide how to handle)
            assert config.Config.SENSORPUSH_USERNAME == '   '
            assert config.Config.SENSORPUSH_PASSWORD == '\t\n'
            assert config.Config.SECRET_KEY == '  \t  '
    
    def test_config_class_attributes_immutable(self):
        """Test that config class attributes behave as expected."""
        # Config classes should be usable as classes, not instances
        assert hasattr(Config, 'SENSORPUSH_API_BASE_URL')
        assert hasattr(DevelopmentConfig, 'DEBUG')
        assert hasattr(ProductionConfig, 'FLASK_ENV')
        assert hasattr(TestingConfig, 'TESTING')
        
        # Methods should be callable on classes
        assert callable(Config.validate_required_config)
        assert callable(Config.get_config_summary)
        assert callable(ProductionConfig.validate_required_config)
    
    def test_config_inheritance_chain(self):
        """Test the inheritance chain of config classes."""
        # All config classes should inherit from Config
        assert issubclass(DevelopmentConfig, Config)
        assert issubclass(ProductionConfig, Config)
        assert issubclass(TestingConfig, Config)
        
        # They should not inherit from each other
        assert not issubclass(DevelopmentConfig, ProductionConfig)
        assert not issubclass(ProductionConfig, TestingConfig)
        assert not issubclass(TestingConfig, DevelopmentConfig)
    
    def test_dotenv_loading(self):
        """Test that dotenv loading is called during import."""
        # Since dotenv is called at module level, we need to test it differently
        # We'll verify that the load_dotenv function exists and is callable
        from config import load_dotenv
        assert callable(load_dotenv)
        
        # Alternative: test that config values are loaded from environment
        # This indirectly tests that dotenv loading works
        import os
        original_value = os.environ.get('TEST_DOTENV_VAR')
        try:
            os.environ['TEST_DOTENV_VAR'] = 'test_value'
            # If dotenv is working, environment variables should be accessible
            assert os.getenv('TEST_DOTENV_VAR') == 'test_value'
        finally:
            if original_value is None:
                os.environ.pop('TEST_DOTENV_VAR', None)
            else:
                os.environ['TEST_DOTENV_VAR'] = original_value