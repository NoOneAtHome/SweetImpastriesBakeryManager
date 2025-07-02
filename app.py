import logging
import sys

"""
Flask application for the Bakery Sensors Data Retrieval API.

This module implements the main Flask application with API endpoints for:
- Retrieving sensor configurations
- Getting latest sensor readings
- Accessing historical sensor data
- Manager authentication and settings
"""

from datetime import datetime, timedelta, UTC
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, request, render_template, redirect, url_for, session, flash
from flask_session import Session as FlaskSession
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func
from config import get_config, TestingConfig # Import TestingConfig
from database import get_db_session_context
from models import Sensor, SensorReading
from error_handling import handle_flask_error, log_info, log_warning, get_error_handler
from polling_service import PollingService, create_polling_service # Import PollingService
from auth import auth_manager, require_manager_auth, setup_initial_pin_from_args, AuthenticationError, AccountLockoutError
from settings_manager import SettingsManager, check_threshold_breach
from sensorpush_api import SensorPushAPI
from scripts.purge_sensor_data import purge_sensor_data_command

def create_app(config_name=None, config_class=None, start_polling_service=True):
    """
    Create and configure the Flask application.
    
    Args:
        config_name (str, optional): Configuration name to use
        config_class (class, optional): Configuration class to use directly
        start_polling_service (bool, optional): Whether to start the polling service (default: True)
        
    Returns:
        Flask: Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    print(f"create_app called with config_name: {config_name}, config_class: {config_class}")
    if config_class is not None:
        # Use the provided config class directly
        config = config_class
    elif config_name == 'testing':
        config = TestingConfig
    else:
        config = get_config(config_name)
    app.config.from_object(config)

    # Configure Flask-Session
    app.config['SESSION_TYPE'] = 'filesystem'
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True
    app.config['SESSION_KEY_PREFIX'] = 'sensor_dashboard:'
    app.config['SESSION_FILE_DIR'] = './flask_session'
    
    # Initialize Flask-Session
    FlaskSession(app)

    # Configure logging
    logging.basicConfig(level=config.LOG_LEVEL, stream=sys.stdout,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Add custom Jinja2 filter for local time conversion
    @app.template_filter('localtime')
    def localtime_filter(utc_datetime):
        """Convert UTC datetime to local time and format as string"""
        if utc_datetime is None:
            return None
        
        # Ensure the datetime is timezone-aware (UTC)
        if utc_datetime.tzinfo is None:
            utc_datetime = utc_datetime.replace(tzinfo=UTC)
        
        # Get the local timezone (Pacific Time for bakery location)
        local_tz = ZoneInfo('America/Los_Angeles')
        
        # Convert to local time
        local_time = utc_datetime.astimezone(local_tz)
        
        # Format and return as string
        return local_time.strftime('%Y-%m-%d %H:%M:%S')
    
    # Initialize and start the polling service if requested
    if start_polling_service:
        try:
            log_info("Initializing polling service within Flask application", "Flask App Factory")
            app.polling_service = create_polling_service(config_class=config)
            
            # Start the polling service
            if app.polling_service.start():
                log_info("Polling service started successfully within Flask application", "Flask App Factory")
                try:
                    app.polling_service.trigger_immediate_poll()
                    log_info("Triggered immediate sensor poll on application startup", "Flask App Factory")
                except Exception as e:
                    log_warning(f"Failed to trigger immediate poll on startup: {e}", "Flask App Factory")
            else:
                log_warning("Failed to start polling service within Flask application", "Flask App Factory")
                
        except Exception as e:
            log_warning(f"Error initializing polling service: {e}", "Flask App Factory")
            # Don't fail app creation if polling service fails
            app.polling_service = None
    else:
        log_info("Polling service initialization skipped", "Flask App Factory")
        app.polling_service = None
    
    # Register cleanup handler for polling service
    @app.teardown_appcontext
    def cleanup_polling_service(exception=None):
        """Clean up polling service when app context ends."""
        if hasattr(app, 'polling_service') and app.polling_service and app.polling_service.is_running():
            log_info("Stopping polling service during app context teardown", "Flask App Factory")
            app.polling_service.stop()
    
    # Register routes on this app instance
    register_routes(app)
    
    # Set up initial manager PIN if needed (checks for MANAGER_PIN env var)
    auth_manager.setup_initial_pin()
    
    # CLI commands are now registered only in create_cli_app() to avoid background service interference
    print(f"🔍 DEBUG: Skipping CLI command registration for main app (start_polling_service={start_polling_service})")
    
    return app


def create_cli_app(config_name=None, config_class=None):
    """
    Create and configure the Flask application for CLI commands.
    
    This version does not start background services to avoid interference
    with interactive CLI commands.
    
    Args:
        config_name (str, optional): Configuration name to use
        config_class (class, optional): Configuration class to use directly
        
    Returns:
        Flask: Configured Flask application instance without background services
    """
    print("🔍 DEBUG: create_cli_app() called - this will NOT start background services")
    app = create_app(config_name=config_name, config_class=config_class, start_polling_service=False)
    
    # Register CLI commands only on the CLI app to avoid background service interference
    print("🔍 DEBUG: Registering CLI commands on CLI app (background services disabled)")
    app.cli.add_command(purge_sensor_data_command)
    
    return app


def create_default_app():
    """
    Default app factory for Flask CLI.
    Creates app with default configuration and background services enabled.
    """
    print("🔍 DEBUG: create_default_app() called - this will START background services")
    return create_app()


def register_routes(app):
    """Register all routes on the given Flask app instance."""
    
    @app.route('/api/sensors', methods=['GET'])
    def get_sensors():
        """
        Get all configured sensors.
        
        Returns:
            JSON response with list of all sensors including their configuration.
        """
        try:
            log_info("Retrieving all sensors", "API /api/sensors")
            
            with get_db_session_context() as session:
                sensors = session.query(Sensor).all()
                
                log_info(f"Successfully retrieved {len(sensors)} sensors", "API /api/sensors")
                return jsonify({
                    'success': True,
                    'data': [serialize_sensor(sensor) for sensor in sensors],
                    'count': len(sensors)
                })
                
        except Exception as e:
            response, status_code = handle_flask_error(e, "API /api/sensors")
            return jsonify(response), status_code

    @app.route('/api/sensors/latest', methods=['GET'])
    def get_latest_readings():
        """
        Get the latest reading for each active sensor.
        
        Returns:
            JSON response with latest readings for all active sensors.
        """
        try:
            log_info("Retrieving latest sensor readings", "API /api/sensors/latest")
            
            with get_db_session_context() as session:
                # Get all active sensors
                active_sensors = session.query(Sensor).filter(Sensor.active == True).all()
                
                latest_readings = []
                
                for sensor in active_sensors:
                    # Get the latest reading for this sensor
                    latest_reading = session.query(SensorReading)\
                        .filter(SensorReading.sensor_id == sensor.sensor_id)\
                        .order_by(desc(SensorReading.timestamp))\
                        .first()
                    
                    if latest_reading:
                        reading_data = serialize_sensor_reading(latest_reading)
                        reading_data['sensor_name'] = sensor.name
                        latest_readings.append(reading_data)
                
                log_info(f"Successfully retrieved latest readings for {len(latest_readings)} sensors", "API /api/sensors/latest")
                return jsonify({
                    'success': True,
                    'data': latest_readings,
                    'count': len(latest_readings)
                })
                
        except Exception as e:
            response, status_code = handle_flask_error(e, "API /api/sensors/latest")
            return jsonify(response), status_code

    @app.route('/api/sensors/history', methods=['GET'])
    def get_sensor_history():
        """
        Get historical data for a specified sensor and time slice.
        
        Query Parameters:
            sensor_id (str): ID of the sensor to get history for
            time_slice (str): Time period ('last_hour', 'today', '24h', '7d', '30d')
            
        Returns:
            JSON response with historical sensor readings.
        """
        try:
            # Get query parameters
            sensor_id = request.args.get('sensor_id')
            time_slice = request.args.get('time_slice')
            
            log_info(f"Retrieving sensor history for sensor_id={sensor_id}, time_slice={time_slice}", "API /api/sensors/history")
            
            # Validate required parameters
            if not sensor_id:
                log_warning("Missing sensor_id parameter", "API /api/sensors/history")
                return jsonify({
                    'success': False,
                    'error': 'Missing required parameter: sensor_id'
                }), 400
                
            if not time_slice:
                log_warning("Missing time_slice parameter", "API /api/sensors/history")
                return jsonify({
                    'success': False,
                    'error': 'Missing required parameter: time_slice'
                }), 400
            
            # Validate time_slice
            try:
                start_time = get_time_filter(time_slice)
            except ValueError as e:
                log_warning(f"Invalid time_slice parameter: {time_slice}", "API /api/sensors/history")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 400
            
            with get_db_session_context() as session:
                # Verify sensor exists
                sensor = session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
                if not sensor:
                    log_warning(f"Sensor not found: {sensor_id}", "API /api/sensors/history")
                    return jsonify({
                        'success': False,
                        'error': f'Sensor not found: {sensor_id}'
                    }), 404
                
                # Get historical readings
                readings = session.query(SensorReading)\
                    .filter(and_(
                        SensorReading.sensor_id == sensor_id,
                        SensorReading.timestamp >= start_time
                    ))\
                    .order_by(desc(SensorReading.timestamp))\
                    .all()
                
                log_info(f"Successfully retrieved {len(readings)} historical readings for sensor {sensor_id}", "API /api/sensors/history")
                return jsonify({
                    'success': True,
                    'data': {
                        'sensor': serialize_sensor(sensor),
                        'readings': [serialize_sensor_reading(reading) for reading in readings],
                        'time_slice': time_slice,
                        'start_time': start_time.isoformat(),
                        'count': len(readings)
                    }
                })
                
        except Exception as e:
            response, status_code = handle_flask_error(e, "API /api/sensors/history")
            return jsonify(response), status_code

    @app.route('/devices/sensors', methods=['GET'])
    def get_devices_sensors():
        """
        Get sensor device information including battery voltage from SensorPush API.
        
        This endpoint fetches device information directly from the SensorPush API,
        which includes battery voltage data for each sensor.
        
        Returns:
            JSON response with sensor device information including battery voltage.
        """
        try:
            log_info("Retrieving sensor devices with battery voltage from SensorPush API", "API /devices/sensors")
            
            # Initialize SensorPush API client
            from flask import current_app
            api_client = SensorPushAPI()
            
            # Get devices/sensors data from SensorPush API
            devices_data = api_client.get_devices_sensors()
            
            log_info(f"Successfully retrieved device data for {len(devices_data)} sensors", "API /devices/sensors")
            return jsonify({
                'success': True,
                'data': devices_data,
                'count': len(devices_data)
            })
            
        except Exception as e:
            response, status_code = handle_flask_error(e, "API /devices/sensors")
            return jsonify(response), status_code

    @app.route('/api/historical_data', methods=['GET'])
    def get_historical_data():
        """
        Get historical sensor data for a specified sensor within a time range.
        
        Query Parameters:
            sensor_id (str): ID of the sensor to get data for (required)
            start_time (str): Start time in ISO format (optional, defaults to 24 hours ago)
            end_time (str): End time in ISO format (optional, defaults to now)
            hourly_average (str): If 'true', return hourly averaged data (optional, defaults to false)
            
        Returns:
            JSON response with historical sensor readings as an array of objects.
            Each object contains timestamp, temperature, and humidity.
            If hourly_average is true, data is grouped and averaged by hour.
        """
        try:
            # Get query parameters
            sensor_id = request.args.get('sensor_id')
            start_time_str = request.args.get('start_time')
            end_time_str = request.args.get('end_time')
            hourly_average_str = request.args.get('hourly_average', 'false').lower()
            hourly_average = hourly_average_str in ('true', '1', 'yes')
            
            log_info(f"Retrieving historical data for sensor_id={sensor_id}, start_time={start_time_str}, end_time={end_time_str}, hourly_average={hourly_average}", "API /api/historical_data")
            
            # Validate required parameters
            if not sensor_id:
                log_warning("Missing sensor_id parameter", "API /api/historical_data")
                return jsonify({
                    'success': False,
                    'error': 'Missing required parameter: sensor_id'
                }), 400
            
            # Set default time range (24 hours ago to now)
            now = datetime.now(UTC)
            default_start_time = now - timedelta(hours=24)
            
            # Parse start_time
            if start_time_str:
                try:
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    # Ensure timezone awareness
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=UTC)
                except ValueError:
                    log_warning(f"Invalid start_time format: {start_time_str}", "API /api/historical_data")
                    return jsonify({
                        'success': False,
                        'error': 'Invalid start_time format. Use ISO format (e.g., 2025-01-01T12:00:00Z)'
                    }), 400
            else:
                start_time = default_start_time
            
            # Parse end_time
            if end_time_str:
                try:
                    end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                    # Ensure timezone awareness
                    if end_time.tzinfo is None:
                        end_time = end_time.replace(tzinfo=UTC)
                except ValueError:
                    log_warning(f"Invalid end_time format: {end_time_str}", "API /api/historical_data")
                    return jsonify({
                        'success': False,
                        'error': 'Invalid end_time format. Use ISO format (e.g., 2025-01-01T12:00:00Z)'
                    }), 400
            else:
                end_time = now
            
            # Validate time range
            if start_time >= end_time:
                log_warning(f"Invalid time range: start_time ({start_time}) >= end_time ({end_time})", "API /api/historical_data")
                return jsonify({
                    'success': False,
                    'error': 'start_time must be before end_time'
                }), 400
            
            with get_db_session_context() as session:
                # Verify sensor exists
                sensor = session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
                if not sensor:
                    log_warning(f"Sensor not found: {sensor_id}", "API /api/historical_data")
                    return jsonify({
                        'success': False,
                        'error': f'Sensor not found: {sensor_id}'
                    }), 404
                
                if hourly_average:
                    # Get hourly averaged data using SQL aggregation
                    # Group by hour and calculate averages using SQLite's strftime function
                    readings = session.query(
                        func.strftime('%Y-%m-%d %H:00:00', SensorReading.timestamp).label('hour'),
                        func.avg(SensorReading.temperature).label('avg_temperature'),
                        func.avg(SensorReading.humidity).label('avg_humidity'),
                        func.avg(SensorReading.battery_voltage).label('battery_voltage')
                    ).filter(and_(
                        SensorReading.sensor_id == sensor_id,
                        SensorReading.timestamp >= start_time,
                        SensorReading.timestamp <= end_time
                    )).group_by(
                        func.strftime('%Y-%m-%d %H:00:00', SensorReading.timestamp)
                    ).order_by(
                        func.strftime('%Y-%m-%d %H:00:00', SensorReading.timestamp)
                    ).all()
                    
                    # Format hourly averaged data
                    historical_data = []
                    for reading in readings:
                        # Parse the strftime result back to datetime and convert to ISO format
                        hour_datetime = datetime.strptime(reading.hour, '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
                        historical_data.append({
                            'timestamp': hour_datetime.isoformat(),
                            'temperature': round(float(reading.avg_temperature), 2),
                            'humidity': round(float(reading.avg_humidity), 2),
                            'battery_voltage': round(float(reading.battery_voltage), 2) if reading.battery_voltage is not None else None
                        })
                else:
                    # Get raw historical readings within the time range
                    readings = session.query(SensorReading)\
                        .filter(and_(
                            SensorReading.sensor_id == sensor_id,
                            SensorReading.timestamp >= start_time,
                            SensorReading.timestamp <= end_time
                        ))\
                        .order_by(SensorReading.timestamp)\
                        .all()
                    
                    # Format response data as simple array of objects
                    historical_data = []
                    for reading in readings:
                        historical_data.append({
                            'timestamp': reading.timestamp.isoformat(),
                            'temperature': reading.temperature,
                            'humidity': reading.humidity,
                            'battery_voltage': reading.battery_voltage
                        })
                
                log_info(f"Successfully retrieved {len(historical_data)} historical readings for sensor {sensor_id}", "API /api/historical_data")
                
                # Handle case where no data is found
                if not historical_data:
                    log_info(f"No data found for sensor {sensor_id} in time range {start_time} to {end_time}", "API /api/historical_data")
                    return jsonify({
                        'name': sensor.name,
                        'min_temp': sensor.min_temp,
                        'max_temp': sensor.max_temp,
                        'data': []
                    })
                
                return jsonify({
                    'name': sensor.name,
                    'min_temp': sensor.min_temp,
                    'max_temp': sensor.max_temp,
                    'data': historical_data
                })
                
        except Exception as e:
            response, status_code = handle_flask_error(e, "API /api/historical_data")
            return jsonify(response), status_code

    @app.route('/api/multi_sensor_historical_data', methods=['GET'])
    def get_multi_sensor_historical_data():
        """
        Get historical sensor data for multiple sensors within a time range.
        
        Query Parameters:
            sensor_ids (str): Comma-separated list of sensor IDs (required)
            start_time (str): Start time in ISO format (optional, defaults to 24 hours ago)
            end_time (str): End time in ISO format (optional, defaults to now)
            hourly_average (str): If 'true', return hourly averaged data (optional, defaults to false)
            
        Returns:
            JSON response with historical sensor readings organized by sensor.
            Structure: {
                "sensor_id_1": {
                    "name": "Sensor Name",
                    "data": [{"timestamp": "...", "temperature": ..., "humidity": ...}, ...]
                },
                "sensor_id_2": {...}
            }
        """
        try:
            # Get query parameters
            sensor_ids_str = request.args.get('sensor_ids')
            start_time_str = request.args.get('start_time')
            end_time_str = request.args.get('end_time')
            hourly_average_str = request.args.get('hourly_average', 'false').lower()
            hourly_average = hourly_average_str in ('true', '1', 'yes')
            
            log_info(f"Retrieving multi-sensor historical data for sensor_ids={sensor_ids_str}, start_time={start_time_str}, end_time={end_time_str}, hourly_average={hourly_average}", "API /api/multi_sensor_historical_data")
            
            # Validate required parameters
            if not sensor_ids_str:
                log_warning("Missing sensor_ids parameter", "API /api/multi_sensor_historical_data")
                return jsonify({
                    'success': False,
                    'error': 'Missing required parameter: sensor_ids'
                }), 400
            
            # Parse sensor IDs
            sensor_ids = [sid.strip() for sid in sensor_ids_str.split(',') if sid.strip()]
            if not sensor_ids:
                log_warning("No valid sensor IDs provided", "API /api/multi_sensor_historical_data")
                return jsonify({
                    'success': False,
                    'error': 'No valid sensor IDs provided'
                }), 400
            
            # Set default time range (24 hours ago to now)
            now = datetime.now(UTC)
            default_start_time = now - timedelta(hours=24)
            
            # Parse start_time
            if start_time_str:
                try:
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=UTC)
                except ValueError:
                    log_warning(f"Invalid start_time format: {start_time_str}", "API /api/multi_sensor_historical_data")
                    return jsonify({
                        'success': False,
                        'error': 'Invalid start_time format. Use ISO format (e.g., 2025-01-01T12:00:00Z)'
                    }), 400
            else:
                start_time = default_start_time
            
            # Parse end_time
            if end_time_str:
                try:
                    end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                    if end_time.tzinfo is None:
                        end_time = end_time.replace(tzinfo=UTC)
                except ValueError:
                    log_warning(f"Invalid end_time format: {end_time_str}", "API /api/multi_sensor_historical_data")
                    return jsonify({
                        'success': False,
                        'error': 'Invalid end_time format. Use ISO format (e.g., 2025-01-01T12:00:00Z)'
                    }), 400
            else:
                end_time = now
            
            # Validate time range
            if start_time >= end_time:
                log_warning(f"Invalid time range: start_time ({start_time}) >= end_time ({end_time})", "API /api/multi_sensor_historical_data")
                return jsonify({
                    'success': False,
                    'error': 'start_time must be before end_time'
                }), 400
            
            result = {}
            
            with get_db_session_context() as session:
                # Process each sensor
                for sensor_id in sensor_ids:
                    # Verify sensor exists
                    sensor = session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
                    if not sensor:
                        log_warning(f"Sensor not found: {sensor_id}", "API /api/multi_sensor_historical_data")
                        continue  # Skip missing sensors instead of failing the entire request
                    
                    if hourly_average:
                        # Get hourly averaged data using SQL aggregation
                        readings = session.query(
                            func.strftime('%Y-%m-%d %H:00:00', SensorReading.timestamp).label('hour'),
                            func.avg(SensorReading.temperature).label('avg_temperature'),
                            func.avg(SensorReading.humidity).label('avg_humidity'),
                            func.avg(SensorReading.battery_voltage).label('battery_voltage')
                        ).filter(and_(
                            SensorReading.sensor_id == sensor_id,
                            SensorReading.timestamp >= start_time,
                            SensorReading.timestamp <= end_time
                        )).group_by(
                            func.strftime('%Y-%m-%d %H:00:00', SensorReading.timestamp)
                        ).order_by(
                            func.strftime('%Y-%m-%d %H:00:00', SensorReading.timestamp)
                        ).all()
                        
                        # Format hourly averaged data
                        historical_data = []
                        for reading in readings:
                            hour_datetime = datetime.strptime(reading.hour, '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
                            historical_data.append({
                                'timestamp': hour_datetime.isoformat(),
                                'temperature': round(float(reading.avg_temperature), 2),
                                'humidity': round(float(reading.avg_humidity), 2),
                                'battery_voltage': round(float(reading.battery_voltage), 2) if reading.battery_voltage is not None else None
                            })
                    else:
                        # Get raw historical readings within the time range
                        readings = session.query(SensorReading)\
                            .filter(and_(
                                SensorReading.sensor_id == sensor_id,
                                SensorReading.timestamp >= start_time,
                                SensorReading.timestamp <= end_time
                            ))\
                            .order_by(SensorReading.timestamp)\
                            .all()
                        
                        # Format response data
                        historical_data = []
                        for reading in readings:
                            historical_data.append({
                                'timestamp': reading.timestamp.isoformat(),
                                'temperature': reading.temperature,
                                'humidity': reading.humidity,
                                'battery_voltage': reading.battery_voltage
                            })
                    
                    # Add sensor data to result
                    result[sensor_id] = {
                        'name': sensor.name,
                        'min_temp': sensor.min_temp,
                        'max_temp': sensor.max_temp,
                        'data': historical_data
                    }
                
                log_info(f"Successfully retrieved multi-sensor historical data for {len(result)} sensors", "API /api/multi_sensor_historical_data")
                return jsonify(result)
                
        except Exception as e:
            response, status_code = handle_flask_error(e, "API /api/multi_sensor_historical_data")
            return jsonify(response), status_code

    @app.route('/api/categorized_sensor_history', methods=['GET'])
    def get_categorized_sensor_history():
        """
        Get historical sensor data for all sensors within a specific category.
        
        Query Parameters:
            category (str): Sensor category ('freezer', 'refrigerator', 'ambient') (required)
            start_time (str): Start time in ISO format (optional, defaults to 24 hours ago)
            end_time (str): End time in ISO format (optional, defaults to now)
            hourly_average (str): If 'true', return hourly averaged data (optional, defaults to false)
            
        Returns:
            JSON response with historical sensor readings organized by sensor within the category.
            Structure: {
                "success": true,
                "data": {
                    "sensor_id_1": {
                        "name": "Sensor Name",
                        "data": [{"timestamp": "...", "temperature": ..., "humidity": ...}, ...]
                    },
                    "sensor_id_2": {...}
                },
                "category": "freezer",
                "time_slice": "24h",
                "start_time": "ISO_FORMAT",
                "end_time": "ISO_FORMAT"
            }
        """
        try:
            # Get query parameters
            category = request.args.get('category')
            start_time_str = request.args.get('start_time')
            end_time_str = request.args.get('end_time')
            hourly_average_str = request.args.get('hourly_average', 'false').lower()
            hourly_average = hourly_average_str in ('true', '1', 'yes')
            
            log_info(f"Retrieving categorized sensor history for category={category}, start_time={start_time_str}, end_time={end_time_str}, hourly_average={hourly_average}", "API /api/categorized_sensor_history")
            
            # Validate required parameters
            if not category:
                log_warning("Missing category parameter", "API /api/categorized_sensor_history")
                return jsonify({
                    'success': False,
                    'error': 'Missing required parameter: category'
                }), 400
            
            # Set default time range (24 hours ago to now)
            now = datetime.now(UTC)
            default_start_time = now - timedelta(hours=24)
            
            # Parse start_time
            if start_time_str:
                try:
                    start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=UTC)
                except ValueError:
                    log_warning(f"Invalid start_time format: {start_time_str}", "API /api/categorized_sensor_history")
                    return jsonify({
                        'success': False,
                        'error': 'Invalid start_time format. Use ISO format (e.g., 2025-01-01T12:00:00Z)'
                    }), 400
            else:
                start_time = default_start_time
            
            # Parse end_time
            if end_time_str:
                try:
                    end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                    if end_time.tzinfo is None:
                        end_time = end_time.replace(tzinfo=UTC)
                except ValueError:
                    log_warning(f"Invalid end_time format: {end_time_str}", "API /api/categorized_sensor_history")
                    return jsonify({
                        'success': False,
                        'error': 'Invalid end_time format. Use ISO format (e.g., 2025-01-01T12:00:00Z)'
                    }), 400
            else:
                end_time = now
            
            # Validate time range
            if start_time >= end_time:
                log_warning(f"Invalid time range: start_time ({start_time}) >= end_time ({end_time})", "API /api/categorized_sensor_history")
                return jsonify({
                    'success': False,
                    'error': 'start_time must be before end_time'
                }), 400
            
            result = {}
            
            with get_db_session_context() as session:
                # Get all active sensors in the specified category
                sensors_in_category = session.query(Sensor).filter(
                    and_(Sensor.active == True, Sensor.category == category)
                ).all()
                
                if not sensors_in_category:
                    log_info(f"No active sensors found for category: {category}", "API /api/categorized_sensor_history")
                    return jsonify({
                        'success': True,
                        'data': {},
                        'category': category,
                        'start_time': start_time.isoformat(),
                        'end_time': end_time.isoformat()
                    })
                
                # Process each sensor in the category
                for sensor in sensors_in_category:
                    sensor_id = sensor.sensor_id
                    
                    if hourly_average:
                        # Get hourly averaged data using SQL aggregation
                        readings = session.query(
                            func.strftime('%Y-%m-%d %H:00:00', SensorReading.timestamp).label('hour'),
                            func.avg(SensorReading.temperature).label('avg_temperature'),
                            func.avg(SensorReading.humidity).label('avg_humidity'),
                            func.avg(SensorReading.battery_voltage).label('battery_voltage')
                        ).filter(and_(
                            SensorReading.sensor_id == sensor_id,
                            SensorReading.timestamp >= start_time,
                            SensorReading.timestamp <= end_time
                        )).group_by(
                            func.strftime('%Y-%m-%d %H:00:00', SensorReading.timestamp)
                        ).order_by(
                            func.strftime('%Y-%m-%d %H:00:00', SensorReading.timestamp)
                        ).all()
                        
                        # Format hourly averaged data
                        historical_data = []
                        for reading in readings:
                            hour_datetime = datetime.strptime(reading.hour, '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
                            historical_data.append({
                                'timestamp': hour_datetime.isoformat(),
                                'temperature': round(float(reading.avg_temperature), 2),
                                'humidity': round(float(reading.avg_humidity), 2),
                                'battery_voltage': round(float(reading.battery_voltage), 2) if reading.battery_voltage is not None else None
                            })
                    else:
                        # Get raw historical readings within the time range
                        readings = session.query(SensorReading)\
                            .filter(and_(
                                SensorReading.sensor_id == sensor_id,
                                SensorReading.timestamp >= start_time,
                                SensorReading.timestamp <= end_time
                            ))\
                            .order_by(SensorReading.timestamp)\
                            .all()
                        
                        # Format response data
                        historical_data = []
                        for reading in readings:
                            historical_data.append({
                                'timestamp': reading.timestamp.isoformat(),
                                'temperature': reading.temperature,
                                'humidity': reading.humidity,
                                'battery_voltage': reading.battery_voltage
                            })
                    
                    # Add sensor data to result
                    result[sensor_id] = {
                        'name': sensor.name,
                        'min_temp': sensor.min_temp,
                        'max_temp': sensor.max_temp,
                        'data': historical_data
                    }
                
                log_info(f"Successfully retrieved categorized sensor history for {len(result)} sensors in category {category}", "API /api/categorized_sensor_history")
                return jsonify({
                    'success': True,
                    'data': result,
                    'category': category,
                    'start_time': start_time.isoformat(),
                    'end_time': end_time.isoformat()
                })
                
        except Exception as e:
            response, status_code = handle_flask_error(e, "API /api/categorized_sensor_history")
            return jsonify(response), status_code

    # Web Interface Routes
    @app.route('/')
    def index():
        """
        Main dashboard page showing all sensors and their latest readings.
        """
        try:
            log_info("Loading main dashboard", "Web Interface")
            
            with get_db_session_context() as session:
                # Get all active sensors with their latest readings
                active_sensors = session.query(Sensor).filter(Sensor.active == True).all()
                
                sensors_with_readings = []
                categorized_sensor_ids = {
                    'freezer': [],
                    'refrigerator': [],
                    'ambient': [],
                    'other': []
                }
                current_utc_time = datetime.now(UTC)
                
                for sensor in active_sensors:
                    # Get the latest reading for this sensor
                    latest_reading = session.query(SensorReading)\
                        .filter(SensorReading.sensor_id == sensor.sensor_id)\
                        .order_by(desc(SensorReading.timestamp))\
                        .first()
                    
                    # Check for threshold breaches
                    threshold_info = check_threshold_breach(sensor, latest_reading)
                    
                    # Calculate if sensor is stale (more than 4 hours old)
                    is_stale = False
                    if latest_reading and latest_reading.timestamp:
                        # Ensure the timestamp is timezone-aware (UTC)
                        reading_timestamp = latest_reading.timestamp
                        if reading_timestamp.tzinfo is None:
                            reading_timestamp = reading_timestamp.replace(tzinfo=UTC)
                        
                        # Calculate time difference
                        time_difference = current_utc_time - reading_timestamp
                        is_stale = time_difference > timedelta(hours=4)
                    
                    sensor_data = {
                        'sensor': sensor,
                        'latest_reading': latest_reading,
                        'threshold_info': threshold_info,
                        'is_stale': is_stale
                    }
                    sensors_with_readings.append(sensor_data)
                
                # Categorize sensors by their category
                for sensor in active_sensors:
                    category = sensor.category if sensor.category else 'other'  # Default to 'other' if category is None
                    if category in categorized_sensor_ids:
                        categorized_sensor_ids[category].append(sensor.sensor_id)
                    else:
                        categorized_sensor_ids['other'].append(sensor.sensor_id)  # Handle unexpected categories
                
                log_info(f"Dashboard loaded with {len(sensors_with_readings)} active sensors", "Web Interface")
                log_info(f"Categorized sensors: {categorized_sensor_ids}", "Web Interface")
                return render_template('dashboard.html',
                                     sensors_data=sensors_with_readings,
                                     categorized_sensor_ids=categorized_sensor_ids)
                
        except Exception as e:
            log_warning(f"Error loading dashboard: {str(e)}", "Web Interface")
            return render_template('error.html', error="Failed to load dashboard"), 500

    @app.route('/sensor/<sensor_id>')
    def sensor_detail(sensor_id):
        """
        Detailed view for a specific sensor showing recent history.
        """
        try:
            log_info(f"Loading sensor detail for {sensor_id}", "Web Interface")
            
            with get_db_session_context() as session:
                # Get sensor information
                sensor = session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
                if not sensor:
                    log_warning(f"Sensor not found: {sensor_id}", "Web Interface")
                    return render_template('error.html', error=f"Sensor {sensor_id} not found"), 404
                
                # Get the latest reading for this sensor
                latest_reading = session.query(SensorReading)\
                    .filter(SensorReading.sensor_id == sensor_id)\
                    .order_by(desc(SensorReading.timestamp))\
                    .first()
                
                # Get recent readings (last 24 hours)
                start_time = datetime.now(UTC) - timedelta(hours=24)
                readings = session.query(SensorReading)\
                    .filter(and_(
                        SensorReading.sensor_id == sensor_id,
                        SensorReading.timestamp >= start_time
                    ))\
                    .order_by(desc(SensorReading.timestamp))\
                    .limit(100)\
                    .all()
                
                log_info(f"Sensor detail loaded for {sensor_id} with {len(readings)} readings", "Web Interface")
                return render_template('sensor_detail.html', sensor=sensor, readings=readings, latest_reading=latest_reading)
                
        except Exception as e:
            log_warning(f"Error loading sensor detail for {sensor_id}: {str(e)}", "Web Interface")
            return render_template('error.html', error="Failed to load sensor details"), 500

    # Manager Authentication Routes
    @app.route('/manager/login', methods=['GET', 'POST'])
    def manager_login():
        """
        Manager login page and authentication handler.
        """
        if request.method == 'GET':
            # Check if already logged in
            session_id = session.get('manager_session_id')
            if session_id and auth_manager.validate_session(session_id, request.remote_addr):
                return redirect(url_for('manager_settings'))
            
            return render_template('manager_login.html')
        
        # POST request - handle login
        try:
            pin = request.form.get('pin', '').strip()
            ip_address = request.remote_addr
            
            if not pin:
                return render_template('manager_login.html', error="PIN is required")
            
            # Attempt authentication
            success, result = auth_manager.authenticate(pin, ip_address)
            
            if success:
                # Store session ID
                session['manager_session_id'] = result
                session.permanent = True
                log_info(f"Manager login successful from {ip_address}", "Manager Login")
                return redirect(url_for('manager_settings'))
            else:
                # Authentication failed
                log_warning(f"Manager login failed from {ip_address}: {result}", "Manager Login")
                return render_template('manager_login.html', error=result)
                
        except AccountLockoutError as e:
            log_warning(f"Account lockout triggered from {request.remote_addr}", "Manager Login")
            return render_template('manager_login.html',
                                 error="Account is locked due to too many failed attempts. Please try again later.")
        except Exception as e:
            log_warning(f"Error during manager login: {str(e)}", "Manager Login")
            return render_template('manager_login.html', error="Login error occurred")

    @app.route('/manager/logout')
    def manager_logout():
        """
        Manager logout handler.
        """
        session_id = session.get('manager_session_id')
        if session_id:
            auth_manager.logout(session_id)
            session.pop('manager_session_id', None)
            log_info("Manager logged out", "Manager Logout")
        
        return redirect(url_for('index'))

    @app.route('/manager/settings')
    @require_manager_auth
    def manager_settings():
        """
        Manager settings panel.
        """
        try:
            config = get_config()
            
            # Get system statistics
            with get_db_session_context() as db_session:
                sensor_count = db_session.query(Sensor).filter(Sensor.active == True).count()
                reading_count = db_session.query(SensorReading).count()
            
            # Get current polling interval
            current_polling_interval = SettingsManager.get_polling_interval()
            
            return render_template('manager_settings.html',
                                 session_timeout=config.SESSION_TIMEOUT,
                                 max_attempts=config.MAX_LOGIN_ATTEMPTS,
                                 flask_env=config.FLASK_ENV,
                                 sensor_count=sensor_count,
                                 reading_count=reading_count,
                                 current_polling_interval=current_polling_interval,
                                 success=request.args.get('success'),
                                 error=request.args.get('error'))
                                 
        except Exception as e:
            log_warning(f"Error loading manager settings: {str(e)}", "Manager Settings")
            return render_template('error.html', error="Failed to load settings"), 500

    @app.route('/manager/change-pin', methods=['POST'])
    @require_manager_auth
    def manager_change_pin():
        """
        Handle manager PIN change requests.
        """
        try:
            current_pin = request.form.get('current_pin', '').strip()
            new_pin = request.form.get('new_pin', '').strip()
            confirm_pin = request.form.get('confirm_pin', '').strip()
            
            # Validate input
            if not all([current_pin, new_pin, confirm_pin]):
                return redirect(url_for('manager_settings', error="All fields are required"))
            
            if new_pin != confirm_pin:
                return redirect(url_for('manager_settings', error="New PIN and confirmation do not match"))
            
            if len(new_pin) < 6 or not new_pin.isdigit():
                return redirect(url_for('manager_settings', error="New PIN must be at least 6 digits and contain only numbers"))
            
            # Attempt PIN change
            session_id = session.get('manager_session_id')
            success, message = auth_manager.change_pin(current_pin, new_pin, session_id, request.remote_addr)
            
            if success:
                return redirect(url_for('manager_settings', success=message))
            else:
                return redirect(url_for('manager_settings', error=message))
                
        except Exception as e:
            log_warning(f"Error changing manager PIN: {str(e)}", "Manager Change PIN")
            return redirect(url_for('manager_settings', error="Error changing PIN"))

    @app.route('/manager/settings/sensors/<sensor_id>', methods=['GET', 'POST'])
    @require_manager_auth
    def manager_individual_sensor_settings(sensor_id):
        """
        Handle sensor configuration settings for a specific sensor.
        """
        try:
            with get_db_session_context() as db_session:
                sensor = db_session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
                if not sensor:
                    flash(f"Sensor {sensor_id} not found.", 'error')
                    return redirect(url_for('manager_sensor_settings'))

                if request.method == 'POST':
                    # Extract data from form
                    display_name = request.form.get('display_name', '').strip()
                    min_temp_str = request.form.get('min_temp')
                    max_temp_str = request.form.get('max_temp')
                    min_humidity_str = request.form.get('min_humidity')
                    max_humidity_str = request.form.get('max_humidity')
                    category = request.form.get('category')

                    # --- Server-side Validation ---
                    errors = []
                    if not display_name:
                        errors.append("Display name cannot be empty.")

                    try:
                        min_temp = float(min_temp_str)
                        max_temp = float(max_temp_str)
                        min_humidity = float(min_humidity_str)
                        max_humidity = float(max_humidity_str)
                    except (ValueError, TypeError):
                        errors.append("Threshold values must be valid numbers.")
                        min_temp, max_temp, min_humidity, max_humidity = None, None, None, None

                    if min_temp is not None and max_temp is not None:
                        if min_temp >= max_temp:
                            errors.append("Minimum temperature must be less than maximum temperature.")
                    
                    if min_humidity is not None and max_humidity is not None:
                        if min_humidity >= max_humidity:
                            errors.append("Minimum humidity must be less than maximum humidity.")
                        if not (0 <= min_humidity <= 100):
                            errors.append("Minimum humidity must be between 0 and 100.")
                        if not (0 <= max_humidity <= 100):
                            errors.append("Maximum humidity must be between 0 and 100.")

                    allowed_categories = ["freezer", "refrigerator", "ambient", "other"]
                    if category and category not in allowed_categories:
                        errors.append(f"Invalid category: {category}. Allowed categories are {', '.join(allowed_categories)}.")
                    elif not category:
                        category = None

                    if errors:
                        for error_msg in errors:
                            flash(error_msg, 'error')
                        # Re-render the page with current sensor data and errors
                        return render_template('manager_sensor_settings.html',
                                               sensor=sensor,
                                               categories=allowed_categories)

                    # Call settings_manager to update all settings
                    success = SettingsManager.update_sensor_full_settings(
                        sensor_id=sensor_id,
                        display_name=display_name,
                        min_temp=min_temp,
                        max_temp=max_temp,
                        min_humidity=min_humidity,
                        max_humidity=max_humidity,
                        category=category
                    )

                    if success:
                        flash(f"Sensor {sensor.name} settings updated successfully!", 'success')
                        return redirect(url_for('manager_sensor_settings', sensor_id=sensor_id))
                    else:
                        flash(f"Failed to update sensor {sensor.name} settings. Please try again.", 'error')
                        return redirect(url_for('manager_sensor_settings', sensor_id=sensor_id))

                # GET request - show sensor settings page for a specific sensor
                categories = ["freezer", "refrigerator", "ambient", "other"]
                return render_template('manager_sensor_settings.html',
                                       sensor=sensor,
                                       categories=categories)

        except Exception as e:
            log_warning(f"Error in sensor settings for {sensor_id}: {str(e)}", "Manager Settings")
            flash("An unexpected error occurred.", 'error')
            return render_template('error.html', error="Failed to load sensor settings"), 500

    @app.route('/manager/settings/sensors', methods=['GET', 'POST'])
    @require_manager_auth
    def manager_sensor_settings():
        """
        Handle sensor configuration settings list and legacy actions.
        """
        try:
            if request.method == 'POST':
                # Handle legacy sensor updates for backward compatibility
                sensor_id = request.form.get('sensor_id')
                action = request.form.get('action')
                
                if not sensor_id:
                    return redirect(url_for('manager_sensor_settings', error="Sensor ID is required"))
                
                with get_db_session_context() as db_session:
                    sensor = db_session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
                    if not sensor:
                        return redirect(url_for('manager_sensor_settings', error="Sensor not found"))
                    
                    if action == 'toggle_active':
                        sensor.active = not sensor.active
                        status = "activated" if sensor.active else "deactivated"
                        db_session.commit()
                        log_info(f"Sensor {sensor_id} {status}", "Manager Settings")
                        return redirect(url_for('manager_sensor_settings', success=f"Sensor {status}"))
            
            # GET request - show sensor settings page
            # Define available categories
            categories = ["freezer", "refrigerator", "ambient", "other"]
            
            with get_db_session_context() as db_session:
                sensors = db_session.query(Sensor).all()
                
            return render_template('manager_sensor_settings.html',
                                 sensors=sensors,
                                 categories=categories,
                                 success=request.args.get('success'),
                                 error=request.args.get('error'))
                                 
        except Exception as e:
            log_warning(f"Error in sensor settings: {str(e)}", "Manager Settings")
            return render_template('error.html', error="Failed to load sensor settings"), 500

    @app.route('/manager/sensors/refetch_names', methods=['POST'])
    @require_manager_auth
    def refetch_sensor_names():
        """
        Refetch sensor names from the SensorPush API and update them in the local database.
        """
        try:
            log_info("Starting sensor name refetch operation", "Refetch Sensor Names")
            
            # Get configuration for SensorPush API
            config = get_config()
            
            # Initialize SensorPush API client
            api_client = SensorPushAPI(config_class=config)
            
            # Authenticate with SensorPush API first
            log_info("Attempting to authenticate with SensorPush API", "Refetch Sensor Names")
            if not api_client.authenticate():
                raise Exception("Failed to authenticate with SensorPush API")
            log_info("Successfully authenticated with SensorPush API", "Refetch Sensor Names")
            
            # Fetch latest sensor metadata from SensorPush API
            log_info("Calling get_devices_sensors() to fetch sensor metadata", "Refetch Sensor Names")
            sensors_data = api_client.get_devices_sensors()
            log_info(f"Successfully retrieved sensor data: {len(sensors_data)} sensors", "Refetch Sensor Names")
            
            updated_count = 0
            
            # Process sensor data and update local database
            with get_db_session_context() as db_session:
                for sensor_id, sensor_info in sensors_data.items():
                    # Extract sensor name from API response
                    api_sensor_name = sensor_info.get('name', f'Sensor {sensor_id}')
                    
                    # Find corresponding sensor in local database
                    local_sensor = db_session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
                    
                    if local_sensor:
                        # Check if name differs and update if necessary
                        if local_sensor.name != api_sensor_name:
                            old_name = local_sensor.name
                            local_sensor.name = api_sensor_name
                            updated_count += 1
                            log_info(f"Updated sensor {sensor_id} name from '{old_name}' to '{api_sensor_name}'", "Refetch Sensor Names")
                    else:
                        log_info(f"Sensor {sensor_id} found in API but not in local database", "Refetch Sensor Names")
                
                # Commit all changes to database
                db_session.commit()
            
            # Prepare success message
            if updated_count > 0:
                success_message = f"Successfully updated {updated_count} sensor name(s) from SensorPush API"
            else:
                success_message = "All sensor names are already up to date"
            
            log_info(f"Sensor name refetch completed. Updated {updated_count} sensors", "Refetch Sensor Names")
            flash(success_message, 'success')
            return redirect(url_for('manager_sensor_settings', success=success_message))
            
        except Exception as e:
            error_message = f"Failed to refetch sensor names: {str(e)}"
            log_warning(error_message, "Refetch Sensor Names")
            flash(error_message, 'error')
            return redirect(url_for('manager_sensor_settings', error=error_message))

    @app.route('/manager/settings/polling', methods=['POST'])
    @require_manager_auth
    def manager_polling_settings():
        """
        Handle polling interval configuration.
        """
        try:
            interval_str = request.form.get('polling_interval', '').strip()
            
            if not interval_str:
                return redirect(url_for('manager_settings', error="Polling interval is required"))
            
            try:
                interval = int(interval_str)
                if interval < 1:
                    return redirect(url_for('manager_settings', error="Polling interval must be at least 1 minute"))
            except ValueError:
                return redirect(url_for('manager_settings', error="Invalid polling interval"))
            
            # Update the polling interval setting in database
            if SettingsManager.set_polling_interval(interval):
                # Update the polling service with the new interval
                from flask import current_app
                if hasattr(current_app, 'polling_service'):
                    current_app.polling_service.update_polling_interval(interval)
                    log_info(f"Polling interval updated to {interval} minutes and applied to service", "Manager Settings")
                else:
                    log_info(f"Polling interval updated to {interval} minutes in database", "Manager Settings")
                
                return redirect(url_for('manager_settings', success=f"Polling interval updated to {interval} minutes"))
            else:
                return redirect(url_for('manager_settings', error="Failed to update polling interval"))
                
        except Exception as e:
            log_warning(f"Error updating polling interval: {str(e)}", "Manager Settings")
            return redirect(url_for('manager_settings', error="Error updating polling interval"))

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        """Handle 404 errors."""
        log_warning(f"404 error: {request.url}", "Flask error handler")
        return jsonify({
            'success': False,
            'error': 'Endpoint not found'
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        """Handle 405 errors."""
        log_warning(f"405 error: {request.method} {request.url}", "Flask error handler")
        return jsonify({
            'success': False,
            'error': 'Method not allowed'
        }), 405

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        error_handler = get_error_handler()
        error_id = error_handler.log_and_store_error(error.original_exception if hasattr(error, 'original_exception') else Exception(str(error)), "Flask 500 error handler")
        return jsonify(error_handler.get_user_friendly_error(error_id)), 500


# Create Flask application instance
app = create_app()


def serialize_sensor(sensor):
    """
    Serialize a Sensor object to a dictionary.
    
    Args:
        sensor (Sensor): Sensor model instance
        
    Returns:
        dict: Serialized sensor data
    """
    return {
        'sensor_id': sensor.sensor_id,
        'name': sensor.name,
        'active': sensor.active,
        'min_temp': sensor.min_temp,
        'max_temp': sensor.max_temp,
        'min_humidity': sensor.min_humidity,
        'max_humidity': sensor.max_humidity,
        'category': sensor.category
    }


def serialize_sensor_reading(reading):
    """
    Serialize a SensorReading object to a dictionary.
    
    Args:
        reading (SensorReading): SensorReading model instance
        
    Returns:
        dict: Serialized sensor reading data
    """
    return {
        'id': reading.id,
        'sensor_id': reading.sensor_id,
        'timestamp': reading.timestamp.isoformat(),
        'temperature': reading.temperature,
        'humidity': reading.humidity,
        'battery_voltage': reading.battery_voltage
    }


def get_time_filter(time_slice):
    """
    Convert time slice string to datetime filter.
    
    Args:
        time_slice (str): Time slice identifier
        
    Returns:
        datetime: Start datetime for filtering
        
    Raises:
        ValueError: If time_slice is invalid
    """
    now = datetime.now(UTC)
    
    time_slice_map = {
        'last_hour': now - timedelta(hours=1),
        'today': now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC),
        '4h': now - timedelta(hours=4),
        '8h': now - timedelta(hours=8),
        '12h': now - timedelta(hours=12),
        '24h': now - timedelta(hours=24),
        '7d': now - timedelta(days=7),
        '30d': now - timedelta(days=30)
    }
    
    if time_slice not in time_slice_map:
        raise ValueError(f"Invalid time_slice. Must be one of: {', '.join(time_slice_map.keys())}")
    
    return time_slice_map[time_slice]


if __name__ == '__main__':
    # Set up initial PIN from command line arguments
    setup_initial_pin_from_args()
    
    # Get configuration first
    config = get_config()
    
    # Create the Flask application (polling service will be initialized automatically)
    app = create_app(config_class=config)

    log_info("Starting Flask application with integrated polling service", "Flask startup")

    app.run(
        debug=config.DEBUG,
        host='0.0.0.0',
        port=5000
    )