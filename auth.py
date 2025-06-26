"""
Authentication module for Manager PIN-based authentication.

This module implements PIN-based authentication for Manager access with:
- Secure PIN hashing using bcrypt
- Session management
- Account lockout after failed attempts
- Initial PIN setup via command-line argument
"""

import os
import sys
import secrets
import bcrypt
from datetime import datetime, timedelta, UTC
from typing import Optional, Tuple
from flask import request, session
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from database import get_db_session_context
from models import ManagerAuth, LoginAttempt, ManagerSession
from config import get_config
from error_handling import log_info, log_warning, log_error


class AuthenticationError(Exception):
    """Custom exception for authentication errors."""
    pass


class AccountLockoutError(AuthenticationError):
    """Exception raised when account is locked due to too many failed attempts."""
    pass


class AuthManager:
    """
    Manager for PIN-based authentication system.
    
    Handles PIN validation, session management, and account lockout functionality.
    """
    
    def __init__(self):
        self.config = get_config()
        self.max_attempts = self.config.MAX_LOGIN_ATTEMPTS
        self.session_timeout = self.config.SESSION_TIMEOUT
        
    def hash_pin(self, pin: str) -> str:
        """
        Hash a PIN using bcrypt.
        
        Args:
            pin (str): Plain text PIN
            
        Returns:
            str: Hashed PIN
        """
        if not self._validate_pin_format(pin):
            raise ValueError("PIN must be at least 6 digits and contain only numbers")
            
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(pin.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def verify_pin(self, pin: str, hashed_pin: str) -> bool:
        """
        Verify a PIN against its hash.
        
        Args:
            pin (str): Plain text PIN
            hashed_pin (str): Hashed PIN from database
            
        Returns:
            bool: True if PIN matches, False otherwise
        """
        try:
            return bcrypt.checkpw(pin.encode('utf-8'), hashed_pin.encode('utf-8'))
        except Exception as e:
            log_error(f"Error verifying PIN: {str(e)}", "AuthManager.verify_pin")
            return False
    
    def _validate_pin_format(self, pin: str) -> bool:
        """
        Validate PIN format (minimum 6 characters, numbers only).
        
        Args:
            pin (str): PIN to validate
            
        Returns:
            bool: True if valid format, False otherwise
        """
        return len(pin) >= 6 and pin.isdigit()
    
    def setup_initial_pin(self, pin: str = None) -> bool:
        """
        Set up the initial manager PIN.
        
        Args:
            pin (str, optional): PIN to set. If None, uses default "000000"
            
        Returns:
            bool: True if setup successful, False if PIN already exists
        """
        if pin is None:
            pin = "000000"  # Development default
            
        try:
            with get_db_session_context() as db_session:
                # Check if PIN already exists
                existing_auth = db_session.query(ManagerAuth).first()
                if existing_auth:
                    log_warning("Manager PIN already exists, skipping setup", "AuthManager.setup_initial_pin")
                    return False
                
                # Create new manager auth record
                hashed_pin = self.hash_pin(pin)
                manager_auth = ManagerAuth(pin_hash=hashed_pin)
                db_session.add(manager_auth)
                db_session.commit()
                
                log_info(f"Initial manager PIN set up successfully", "AuthManager.setup_initial_pin")
                return True
                
        except Exception as e:
            log_error(f"Error setting up initial PIN: {str(e)}", "AuthManager.setup_initial_pin")
            return False
    
    def authenticate(self, pin: str, ip_address: str) -> Tuple[bool, Optional[str]]:
        """
        Authenticate a manager using PIN.
        
        Args:
            pin (str): PIN to authenticate
            ip_address (str): IP address of the request
            
        Returns:
            Tuple[bool, Optional[str]]: (success, session_id or error_message)
            
        Raises:
            AccountLockoutError: If account is locked due to too many failed attempts
        """
        try:
            # Check if account is locked
            if self._is_account_locked(ip_address):
                raise AccountLockoutError("Account is locked due to too many failed login attempts")
            
            with get_db_session_context() as db_session:
                # Get manager auth record
                manager_auth = db_session.query(ManagerAuth).first()
                if not manager_auth:
                    log_warning("No manager PIN configured", "AuthManager.authenticate")
                    self._record_login_attempt(db_session, ip_address, False)
                    return False, "Authentication not configured"
                
                # Verify PIN
                if self.verify_pin(pin, manager_auth.pin_hash):
                    # Successful authentication
                    session_id = self._create_session(db_session, ip_address)
                    self._record_login_attempt(db_session, ip_address, True)
                    self._clear_failed_attempts(db_session, ip_address)
                    
                    log_info(f"Manager authentication successful from {ip_address}", "AuthManager.authenticate")
                    return True, session_id
                else:
                    # Failed authentication
                    self._record_login_attempt(db_session, ip_address, False)
                    failed_count = self._get_recent_failed_attempts(db_session, ip_address)
                    
                    log_warning(f"Manager authentication failed from {ip_address} (attempt {failed_count}/{self.max_attempts})", "AuthManager.authenticate")
                    
                    if failed_count >= self.max_attempts:
                        raise AccountLockoutError("Account locked due to too many failed attempts")
                    
                    return False, f"Invalid PIN. {self.max_attempts - failed_count} attempts remaining."
                    
        except AccountLockoutError:
            raise
        except Exception as e:
            log_error(f"Error during authentication: {str(e)}", "AuthManager.authenticate")
            return False, "Authentication error occurred"
    
    def _create_session(self, db_session: Session, ip_address: str) -> str:
        """
        Create a new manager session.
        
        Args:
            db_session (Session): Database session
            ip_address (str): IP address of the request
            
        Returns:
            str: Session ID
        """
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=self.session_timeout)
        
        # Deactivate any existing sessions for this IP
        db_session.query(ManagerSession)\
            .filter(ManagerSession.ip_address == ip_address)\
            .update({'active': False})
        
        # Create new session
        manager_session = ManagerSession(
            session_id=session_id,
            ip_address=ip_address,
            expires_at=expires_at
        )
        db_session.add(manager_session)
        db_session.commit()
        
        return session_id
    
    def validate_session(self, session_id: str, ip_address: str) -> bool:
        """
        Validate a manager session.
        
        Args:
            session_id (str): Session ID to validate
            ip_address (str): IP address of the request
            
        Returns:
            bool: True if session is valid, False otherwise
        """
        try:
            with get_db_session_context() as db_session:
                session_record = db_session.query(ManagerSession)\
                    .filter(and_(
                        ManagerSession.session_id == session_id,
                        ManagerSession.ip_address == ip_address,
                        ManagerSession.active == True,
                        ManagerSession.expires_at > datetime.now(UTC)
                    )).first()
                
                return session_record is not None
                
        except Exception as e:
            log_error(f"Error validating session: {str(e)}", "AuthManager.validate_session")
            return False
    
    def logout(self, session_id: str) -> bool:
        """
        Logout a manager session.
        
        Args:
            session_id (str): Session ID to logout
            
        Returns:
            bool: True if logout successful, False otherwise
        """
        try:
            with get_db_session_context() as db_session:
                db_session.query(ManagerSession)\
                    .filter(ManagerSession.session_id == session_id)\
                    .update({'active': False})
                db_session.commit()
                
                log_info("Manager session logged out", "AuthManager.logout")
                return True
                
        except Exception as e:
            log_error(f"Error during logout: {str(e)}", "AuthManager.logout")
            return False
    
    def _record_login_attempt(self, db_session: Session, ip_address: str, success: bool):
        """Record a login attempt."""
        attempt = LoginAttempt(
            ip_address=ip_address,
            success=success
        )
        db_session.add(attempt)
        db_session.commit()
    
    def _get_recent_failed_attempts(self, db_session: Session, ip_address: str) -> int:
        """Get count of recent failed attempts for an IP address."""
        # Look at attempts in the last hour
        since = datetime.now(UTC) - timedelta(hours=1)
        
        count = db_session.query(LoginAttempt)\
            .filter(and_(
                LoginAttempt.ip_address == ip_address,
                LoginAttempt.success == False,
                LoginAttempt.timestamp >= since
            )).count()
        
        return count
    
    def _is_account_locked(self, ip_address: str) -> bool:
        """Check if account is locked for an IP address."""
        try:
            with get_db_session_context() as db_session:
                failed_count = self._get_recent_failed_attempts(db_session, ip_address)
                return failed_count >= self.max_attempts
        except Exception:
            return False
    
    def _clear_failed_attempts(self, db_session: Session, ip_address: str):
        """Clear failed attempts for an IP address after successful login."""
        # We don't actually delete them, just record the successful attempt
        # The time-based filtering in _get_recent_failed_attempts handles the rest
        pass
    
    def change_pin(self, current_pin: str, new_pin: str, session_id: str, ip_address: str) -> Tuple[bool, str]:
        """
        Change the manager PIN.
        
        Args:
            current_pin (str): Current PIN
            new_pin (str): New PIN
            session_id (str): Valid session ID
            ip_address (str): IP address of the request
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            # Validate session
            if not self.validate_session(session_id, ip_address):
                return False, "Invalid session"
            
            # Validate new PIN format
            if not self._validate_pin_format(new_pin):
                return False, "New PIN must be at least 6 digits and contain only numbers"
            
            with get_db_session_context() as db_session:
                manager_auth = db_session.query(ManagerAuth).first()
                if not manager_auth:
                    return False, "Authentication not configured"
                
                # Verify current PIN
                if not self.verify_pin(current_pin, manager_auth.pin_hash):
                    return False, "Current PIN is incorrect"
                
                # Update PIN
                manager_auth.pin_hash = self.hash_pin(new_pin)
                manager_auth.updated_at = datetime.now(UTC)
                db_session.commit()
                
                log_info(f"Manager PIN changed successfully from {ip_address}", "AuthManager.change_pin")
                return True, "PIN changed successfully"
                
        except Exception as e:
            log_error(f"Error changing PIN: {str(e)}", "AuthManager.change_pin")
            return False, "Error changing PIN"


# Global auth manager instance
auth_manager = AuthManager()


def require_manager_auth(f):
    """
    Decorator to require manager authentication for a route.
    
    Usage:
        @app.route('/manager/settings')
        @require_manager_auth
        def settings():
            return render_template('settings.html')
    """
    from functools import wraps
    from flask import redirect, url_for, session as flask_session
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_id = flask_session.get('manager_session_id')
        ip_address = request.remote_addr
        
        if not session_id or not auth_manager.validate_session(session_id, ip_address):
            log_warning(f"Unauthorized access attempt to {request.endpoint} from {ip_address}", "require_manager_auth")
            return redirect(url_for('manager_login'))
        
        return f(*args, **kwargs)
    
    return decorated_function


def setup_initial_pin_from_args():
    """
    Set up initial PIN from command-line arguments.
    
    Checks for --initial-pin argument and sets up the PIN if provided.
    """
    if '--initial-pin' in sys.argv:
        try:
            pin_index = sys.argv.index('--initial-pin') + 1
            if pin_index < len(sys.argv):
                initial_pin = sys.argv[pin_index]
                if auth_manager.setup_initial_pin(initial_pin):
                    print(f"Initial manager PIN set up successfully")
                else:
                    print("Manager PIN already exists, skipping setup")
            else:
                print("Error: --initial-pin requires a PIN value")
        except Exception as e:
            print(f"Error setting up initial PIN: {e}")
    else:
        # Try to set up default PIN if none exists
        auth_manager.setup_initial_pin()