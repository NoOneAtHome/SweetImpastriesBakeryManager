"""
Database models for the Bakery Sensors application.

This module defines SQLAlchemy models for the sensors, sensor_readings, errors, and authentication tables.
"""

from datetime import datetime, UTC
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Sensor(Base):
    """
    Model for the sensors table.
    
    Stores information about individual sensors including their configuration
    and operational parameters.
    """
    __tablename__ = 'sensors'
    
    sensor_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    min_temp = Column(Float, nullable=False)
    max_temp = Column(Float, nullable=False)
    min_humidity = Column(Float, nullable=False)
    max_humidity = Column(Float, nullable=False)
    category = Column(String, nullable=True)  # New field for sensor categorization
    
    # Relationship to sensor readings
    readings = relationship("SensorReading", back_populates="sensor", cascade="all, delete-orphan")
    
    @property
    def display_name(self):
        """Return the display name for the sensor (currently just the name)."""
        return self.name
    
    def __repr__(self):
        return f"<Sensor(sensor_id='{self.sensor_id}', name='{self.name}', active={self.active}, category='{self.category}')>"


class SensorReading(Base):
    """
    Model for the sensor_readings table.
    
    Stores individual sensor measurements with timestamp, temperature, and humidity data.
    """
    __tablename__ = 'sensor_readings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sensor_id = Column(String, ForeignKey('sensors.sensor_id'), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    temperature = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    battery_voltage = Column(Float, nullable=True)
    
    # Relationship to sensor
    sensor = relationship("Sensor", back_populates="readings")
    
    def __init__(self, sensor_id, timestamp, temperature, humidity, battery_voltage=None):
        self.sensor_id = sensor_id
        self.timestamp = timestamp
        self.temperature = temperature
        self.humidity = humidity
        self.battery_voltage = battery_voltage
    
    def __repr__(self):
        return f"<SensorReading(id={self.id}, sensor_id='{self.sensor_id}', timestamp='{self.timestamp}', temp={self.temperature}, humidity={self.humidity}, battery_voltage={self.battery_voltage})>"


class Error(Base):
    """
    Model for the errors table.
    
    Stores application errors and exceptions with detailed information for debugging.
    """
    __tablename__ = 'errors'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    error_id = Column(String, unique=True, nullable=False)
    message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    level = Column(String, nullable=True, default='ERROR')
    source = Column(String, nullable=True, default='application')
    
    def __repr__(self):
        return f"<Error(id={self.id}, error_id='{self.error_id}', level='{self.level}', timestamp='{self.timestamp}')>"


class ManagerAuth(Base):
    """
    Model for the manager_auth table.
    
    Stores manager authentication information including PIN hash and session data.
    """
    __tablename__ = 'manager_auth'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    pin_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    
    def __repr__(self):
        return f"<ManagerAuth(id={self.id}, created_at='{self.created_at}')>"


class LoginAttempt(Base):
    """
    Model for the login_attempts table.
    
    Tracks failed login attempts for account lockout functionality.
    """
    __tablename__ = 'login_attempts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ip_address = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    success = Column(Boolean, nullable=False, default=False)
    
    def __repr__(self):
        return f"<LoginAttempt(id={self.id}, ip_address='{self.ip_address}', success={self.success}, timestamp='{self.timestamp}')>"


class ManagerSession(Base):
    """
    Model for the manager_sessions table.
    
    Stores active manager sessions for authentication tracking.
    """
    __tablename__ = 'manager_sessions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, unique=True, nullable=False)
    ip_address = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    
    def __repr__(self):
        return f"<ManagerSession(id={self.id}, session_id='{self.session_id}', active={self.active})>"


class SystemSettings(Base):
    """
    Model for the system_settings table.
    
    Stores configurable system settings that can be modified through the manager interface.
    """
    __tablename__ = 'system_settings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    setting_key = Column(String, unique=True, nullable=False)
    setting_value = Column(String, nullable=False)
    description = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    
    def __repr__(self):
        return f"<SystemSettings(key='{self.setting_key}', value='{self.setting_value}')>"