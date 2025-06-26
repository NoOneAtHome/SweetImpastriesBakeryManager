#!/usr/bin/env python3
"""
Test script for the Manager Authentication system.

This script tests the core authentication functionality including:
- PIN setup and hashing
- Authentication with correct/incorrect PINs
- Account lockout after failed attempts
- Session management
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth import AuthManager, AccountLockoutError
from database import get_db_session_context
from models import ManagerAuth, LoginAttempt, ManagerSession
from config import get_config

def test_authentication_system():
    """Test the complete authentication system."""
    print("Testing Manager Authentication System")
    print("=" * 50)
    
    auth_manager = AuthManager()
    
    # Test 1: Initial PIN setup
    print("\n1. Testing initial PIN setup...")
    try:
        # Clear any existing auth data for clean test
        with get_db_session_context() as session:
            session.query(ManagerAuth).delete()
            session.query(LoginAttempt).delete()
            session.query(ManagerSession).delete()
            session.commit()
        
        result = auth_manager.setup_initial_pin("123456")
        print(f"   Initial PIN setup: {'SUCCESS' if result else 'FAILED'}")
        
        # Try to setup again (should fail)
        result = auth_manager.setup_initial_pin("654321")
        print(f"   Duplicate PIN setup prevention: {'SUCCESS' if not result else 'FAILED'}")
        
    except Exception as e:
        print(f"   ERROR: {e}")
    
    # Test 2: PIN validation
    print("\n2. Testing PIN validation...")
    try:
        # Test correct PIN
        success, session_id = auth_manager.authenticate("123456", "127.0.0.1")
        print(f"   Correct PIN authentication: {'SUCCESS' if success else 'FAILED'}")
        
        if success:
            # Test session validation
            valid = auth_manager.validate_session(session_id, "127.0.0.1")
            print(f"   Session validation: {'SUCCESS' if valid else 'FAILED'}")
            
            # Test logout
            logout_success = auth_manager.logout(session_id)
            print(f"   Logout: {'SUCCESS' if logout_success else 'FAILED'}")
        
    except Exception as e:
        print(f"   ERROR: {e}")
    
    # Test 3: Failed authentication and lockout
    print("\n3. Testing failed authentication and lockout...")
    try:
        failed_attempts = 0
        max_attempts = auth_manager.max_attempts
        
        for i in range(max_attempts + 1):
            try:
                success, message = auth_manager.authenticate("wrong_pin", "192.168.1.100")
                if not success:
                    failed_attempts += 1
                    print(f"   Failed attempt {failed_attempts}: {message}")
                else:
                    print(f"   ERROR: Authentication should have failed")
                    break
            except AccountLockoutError as e:
                print(f"   Account lockout triggered after {failed_attempts} attempts: SUCCESS")
                break
        
    except Exception as e:
        print(f"   ERROR: {e}")
    
    # Test 4: PIN change
    print("\n4. Testing PIN change...")
    try:
        # First authenticate with correct PIN
        success, session_id = auth_manager.authenticate("123456", "127.0.0.1")
        if success:
            # Try to change PIN
            change_success, message = auth_manager.change_pin("123456", "789012", session_id, "127.0.0.1")
            print(f"   PIN change: {'SUCCESS' if change_success else 'FAILED'} - {message}")
            
            if change_success:
                # Test authentication with new PIN
                success, _ = auth_manager.authenticate("789012", "127.0.0.1")
                print(f"   Authentication with new PIN: {'SUCCESS' if success else 'FAILED'}")
                
                # Test authentication with old PIN (should fail)
                success, _ = auth_manager.authenticate("123456", "127.0.0.1")
                print(f"   Authentication with old PIN (should fail): {'SUCCESS' if not success else 'FAILED'}")
        
    except Exception as e:
        print(f"   ERROR: {e}")
    
    # Test 5: Database records
    print("\n5. Checking database records...")
    try:
        with get_db_session_context() as session:
            auth_count = session.query(ManagerAuth).count()
            attempt_count = session.query(LoginAttempt).count()
            session_count = session.query(ManagerSession).count()
            
            print(f"   Manager auth records: {auth_count}")
            print(f"   Login attempt records: {attempt_count}")
            print(f"   Session records: {session_count}")
            
    except Exception as e:
        print(f"   ERROR: {e}")
    
    print("\n" + "=" * 50)
    print("Authentication system test completed!")

if __name__ == "__main__":
    test_authentication_system()