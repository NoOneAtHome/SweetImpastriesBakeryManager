#!/usr/bin/env python3
"""
Manager PIN Reset Tool for BakerySensors

This command-line utility allows administrators to reset the manager PIN
with proper validation, logging, and security measures.

Usage:
    python reset_manager_pin.py [options]
    
Options:
    --pin PIN           Set specific PIN (must be 6+ digits)
    --interactive       Interactive mode to enter PIN securely
    --force             Force reset without confirmation
    --clear-sessions    Clear all existing manager sessions
    --clear-attempts    Clear all failed login attempts
    --help              Show this help message

Examples:
    python reset_manager_pin.py --interactive
    python reset_manager_pin.py --pin 123456 --force
    python reset_manager_pin.py --pin 789012 --clear-sessions --clear-attempts
"""

import sys
import argparse
import getpass
from datetime import datetime, UTC
from typing import Optional

# Import project modules
from database import get_db_session_context, init_database
from models import ManagerAuth, LoginAttempt, ManagerSession
from auth import AuthManager
from error_handling import log_info, log_warning, log_error
from config import get_config


class PinResetTool:
    """Manager PIN reset utility with comprehensive validation and logging."""
    
    def __init__(self):
        self.auth_manager = AuthManager()
        self.config = get_config()
        
    def validate_pin(self, pin: str) -> tuple[bool, str]:
        """
        Validate PIN format and security requirements.
        
        Args:
            pin (str): PIN to validate
            
        Returns:
            tuple[bool, str]: (is_valid, error_message)
        """
        if not pin:
            return False, "PIN cannot be empty"
            
        if not pin.isdigit():
            return False, "PIN must contain only numbers"
            
        if len(pin) < 6:
            return False, "PIN must be at least 6 digits long"
            
        if len(pin) > 20:
            return False, "PIN must be no more than 20 digits long"
            
        # Check for weak patterns
        if pin == "000000" or pin == "123456" or pin == "111111":
            return False, "PIN is too weak. Avoid common patterns like 000000, 123456, or repeated digits"
            
        # Check for sequential patterns
        if len(set(pin)) == 1:  # All same digits
            return False, "PIN cannot be all the same digit"
            
        return True, ""
    
    def get_current_pin_info(self) -> Optional[dict]:
        """
        Get information about the current PIN setup.
        
        Returns:
            dict: PIN information or None if no PIN exists
        """
        try:
            with get_db_session_context() as db_session:
                manager_auth = db_session.query(ManagerAuth).first()
                if manager_auth:
                    return {
                        'exists': True,
                        'created_at': manager_auth.created_at,
                        'updated_at': manager_auth.updated_at,
                        'id': manager_auth.id
                    }
                return {'exists': False}
        except Exception as e:
            log_error(f"Error checking current PIN info: {str(e)}", "PinResetTool.get_current_pin_info")
            return None
    
    def clear_failed_attempts(self) -> bool:
        """
        Clear all failed login attempts.
        
        Returns:
            bool: True if successful
        """
        try:
            with get_db_session_context() as db_session:
                deleted_count = db_session.query(LoginAttempt).delete()
                db_session.commit()
                log_info(f"Cleared {deleted_count} failed login attempts", "PinResetTool.clear_failed_attempts")
                return True
        except Exception as e:
            log_error(f"Error clearing failed attempts: {str(e)}", "PinResetTool.clear_failed_attempts")
            return False
    
    def clear_manager_sessions(self) -> bool:
        """
        Clear all active manager sessions.
        
        Returns:
            bool: True if successful
        """
        try:
            with get_db_session_context() as db_session:
                deleted_count = db_session.query(ManagerSession).delete()
                db_session.commit()
                log_info(f"Cleared {deleted_count} manager sessions", "PinResetTool.clear_manager_sessions")
                return True
        except Exception as e:
            log_error(f"Error clearing manager sessions: {str(e)}", "PinResetTool.clear_manager_sessions")
            return False
    
    def reset_pin(self, new_pin: str, clear_sessions: bool = False, clear_attempts: bool = False) -> bool:
        """
        Reset the manager PIN.
        
        Args:
            new_pin (str): New PIN to set
            clear_sessions (bool): Whether to clear existing sessions
            clear_attempts (bool): Whether to clear failed login attempts
            
        Returns:
            bool: True if successful
        """
        # Validate PIN
        is_valid, error_msg = self.validate_pin(new_pin)
        if not is_valid:
            print(f"❌ PIN validation failed: {error_msg}")
            return False
        
        try:
            with get_db_session_context() as db_session:
                # Get current PIN info for logging
                current_info = self.get_current_pin_info()
                
                # Delete existing PIN
                deleted_count = db_session.query(ManagerAuth).delete()
                
                # Create new PIN
                hashed_pin = self.auth_manager.hash_pin(new_pin)
                new_auth = ManagerAuth(pin_hash=hashed_pin)
                db_session.add(new_auth)
                db_session.commit()
                
                # Log the reset
                if current_info and current_info.get('exists'):
                    log_info("Manager PIN reset successfully (existing PIN replaced)", "PinResetTool.reset_pin")
                else:
                    log_info("Manager PIN created successfully (no previous PIN)", "PinResetTool.reset_pin")
                
                print("✅ Manager PIN reset successfully!")
                
                # Clear sessions if requested
                if clear_sessions:
                    if self.clear_manager_sessions():
                        print("✅ All manager sessions cleared")
                    else:
                        print("⚠️  Warning: Failed to clear manager sessions")
                
                # Clear failed attempts if requested
                if clear_attempts:
                    if self.clear_failed_attempts():
                        print("✅ All failed login attempts cleared")
                    else:
                        print("⚠️  Warning: Failed to clear failed login attempts")
                
                return True
                
        except Exception as e:
            log_error(f"Error resetting PIN: {str(e)}", "PinResetTool.reset_pin")
            print(f"❌ Error resetting PIN: {str(e)}")
            return False
    
    def interactive_reset(self, clear_sessions: bool = False, clear_attempts: bool = False) -> bool:
        """
        Interactive PIN reset with secure input.
        
        Args:
            clear_sessions (bool): Whether to clear existing sessions
            clear_attempts (bool): Whether to clear failed login attempts
            
        Returns:
            bool: True if successful
        """
        print("\n🔐 Interactive Manager PIN Reset")
        print("=" * 40)
        
        # Show current PIN status
        current_info = self.get_current_pin_info()
        if current_info:
            if current_info.get('exists'):
                print(f"📋 Current PIN status: EXISTS")
                print(f"   Created: {current_info['created_at']}")
                print(f"   Updated: {current_info['updated_at']}")
            else:
                print("📋 Current PIN status: NOT SET")
        
        print("\n📝 PIN Requirements:")
        print("   • Must be 6-20 digits long")
        print("   • Must contain only numbers")
        print("   • Avoid weak patterns (000000, 123456, etc.)")
        print("   • Cannot be all the same digit")
        
        # Get new PIN
        while True:
            try:
                new_pin = getpass.getpass("\n🔑 Enter new PIN (input hidden): ")
                confirm_pin = getpass.getpass("🔑 Confirm new PIN: ")
                
                if new_pin != confirm_pin:
                    print("❌ PINs do not match. Please try again.")
                    continue
                
                is_valid, error_msg = self.validate_pin(new_pin)
                if not is_valid:
                    print(f"❌ {error_msg}")
                    continue
                
                break
                
            except KeyboardInterrupt:
                print("\n\n❌ Operation cancelled by user")
                return False
        
        # Confirm reset
        print(f"\n⚠️  This will reset the manager PIN.")
        if clear_sessions:
            print("   • All manager sessions will be cleared")
        if clear_attempts:
            print("   • All failed login attempts will be cleared")
        
        try:
            confirm = input("\n❓ Are you sure you want to proceed? (yes/no): ").lower().strip()
            if confirm not in ['yes', 'y']:
                print("❌ Operation cancelled")
                return False
        except KeyboardInterrupt:
            print("\n\n❌ Operation cancelled by user")
            return False
        
        # Perform reset
        return self.reset_pin(new_pin, clear_sessions, clear_attempts)


def main():
    """Main entry point for the PIN reset tool."""
    parser = argparse.ArgumentParser(
        description="Manager PIN Reset Tool for BakerySensors",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python reset_manager_pin.py --interactive
  python reset_manager_pin.py --pin 123456 --force
  python reset_manager_pin.py --pin 789012 --clear-sessions --clear-attempts
        """
    )
    
    parser.add_argument('--pin', type=str, help='Set specific PIN (must be 6+ digits)')
    parser.add_argument('--interactive', action='store_true', help='Interactive mode to enter PIN securely')
    parser.add_argument('--force', action='store_true', help='Force reset without confirmation')
    parser.add_argument('--clear-sessions', action='store_true', help='Clear all existing manager sessions')
    parser.add_argument('--clear-attempts', action='store_true', help='Clear all failed login attempts')
    
    args = parser.parse_args()
    
    # Show help if no arguments
    if len(sys.argv) == 1:
        parser.print_help()
        return 1
    
    print("🏭 BakerySensors Manager PIN Reset Tool")
    print("=" * 50)
    
    # Initialize database
    try:
        init_database()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {str(e)}")
        return 1
    
    # Create reset tool
    reset_tool = PinResetTool()
    
    # Handle interactive mode
    if args.interactive:
        success = reset_tool.interactive_reset(args.clear_sessions, args.clear_attempts)
        return 0 if success else 1
    
    # Handle PIN argument
    if args.pin:
        # Validate PIN
        is_valid, error_msg = reset_tool.validate_pin(args.pin)
        if not is_valid:
            print(f"❌ PIN validation failed: {error_msg}")
            return 1
        
        # Confirm if not forced
        if not args.force:
            current_info = reset_tool.get_current_pin_info()
            if current_info and current_info.get('exists'):
                print("⚠️  A manager PIN already exists.")
            
            print(f"⚠️  This will set the manager PIN to: {args.pin}")
            if args.clear_sessions:
                print("   • All manager sessions will be cleared")
            if args.clear_attempts:
                print("   • All failed login attempts will be cleared")
            
            try:
                confirm = input("\n❓ Are you sure you want to proceed? (yes/no): ").lower().strip()
                if confirm not in ['yes', 'y']:
                    print("❌ Operation cancelled")
                    return 1
            except KeyboardInterrupt:
                print("\n\n❌ Operation cancelled by user")
                return 1
        
        # Perform reset
        success = reset_tool.reset_pin(args.pin, args.clear_sessions, args.clear_attempts)
        return 0 if success else 1
    
    # If no PIN or interactive mode specified
    print("❌ Error: You must specify either --pin or --interactive mode")
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())