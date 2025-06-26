# Manager PIN Reset Guide

This guide explains how to reset the manager PIN for the BakerySensors application using the provided command-line tool.

## Overview

The `reset_manager_pin.py` tool provides a secure way to reset the manager PIN with proper validation, logging, and security measures.

## Prerequisites

- Python environment with project dependencies installed
- Access to the project directory
- Database file (`db/sensor_dashboard.db`) accessible

## Usage Options

### 1. Interactive Mode (Recommended)

The safest way to reset the PIN with hidden input:

```bash
python reset_manager_pin.py --interactive
```

This mode will:
- Show current PIN status
- Prompt for new PIN with hidden input
- Validate PIN strength
- Require confirmation before proceeding
- Provide clear feedback

### 2. Direct PIN Setting

Set a specific PIN directly:

```bash
python reset_manager_pin.py --pin YOUR_NEW_PIN
```

Example:
```bash
python reset_manager_pin.py --pin 789012
```

### 3. Force Reset (No Confirmation)

Reset without confirmation prompts:

```bash
python reset_manager_pin.py --pin YOUR_NEW_PIN --force
```

### 4. Reset with Cleanup

Reset PIN and clear sessions/failed attempts:

```bash
python reset_manager_pin.py --pin YOUR_NEW_PIN --clear-sessions --clear-attempts
```

## PIN Requirements

- **Length**: 6-20 digits
- **Format**: Numbers only
- **Security**: Avoid weak patterns like:
  - `000000` (all zeros)
  - `123456` (sequential)
  - `111111` (repeated digits)
  - Any single repeated digit

## Command Options

| Option | Description |
|--------|-------------|
| `--pin PIN` | Set specific PIN (must meet requirements) |
| `--interactive` | Interactive mode with hidden input |
| `--force` | Skip confirmation prompts |
| `--clear-sessions` | Clear all active manager sessions |
| `--clear-attempts` | Clear all failed login attempts |
| `--help` | Show help message |

## Examples

### Basic Interactive Reset
```bash
python reset_manager_pin.py --interactive
```

### Quick Reset with Strong PIN
```bash
python reset_manager_pin.py --pin 987654 --force
```

### Complete Reset (PIN + Cleanup)
```bash
python reset_manager_pin.py --pin 456789 --clear-sessions --clear-attempts --force
```

### Check Help
```bash
python reset_manager_pin.py --help
```

## Security Features

### PIN Validation
- Checks for minimum length (6 digits)
- Prevents weak patterns
- Ensures numeric-only format
- Validates against common weak PINs

### Logging
- All operations are logged with timestamps
- Success and failure events recorded
- IP addresses and session information tracked

### Session Management
- Option to clear all active sessions
- Failed login attempt cleanup
- Secure session invalidation

## Troubleshooting

### Common Issues

**"PIN validation failed"**
- Ensure PIN is 6+ digits
- Use only numbers
- Avoid weak patterns like 123456

**"Database initialization failed"**
- Check database file permissions
- Ensure SQLite database is accessible
- Verify project dependencies are installed

**"Operation cancelled"**
- User interrupted with Ctrl+C
- Confirmation was declined
- Normal behavior for safety

### Error Recovery

If the tool fails partway through:
1. Check the log files for detailed error information
2. Verify database integrity
3. Re-run the tool with `--force` if needed
4. Contact system administrator if issues persist

## Security Best Practices

1. **Use Interactive Mode**: Prevents PIN from appearing in command history
2. **Choose Strong PINs**: Avoid predictable patterns
3. **Clear Sessions**: Use `--clear-sessions` when resetting forgotten PINs
4. **Monitor Logs**: Check application logs after PIN changes
5. **Test Access**: Verify new PIN works before closing terminal

## Integration with Application

After resetting the PIN:
1. The new PIN takes effect immediately
2. All existing sessions are optionally cleared
3. Failed login attempts are optionally reset
4. Manager can log in with the new PIN at `/manager/login`

## Backup and Recovery

Before resetting:
- Consider backing up the database file
- Note the current PIN if known
- Ensure you have administrative access to the system

## Support

For additional help:
- Check application logs in `sensor_dashboard.log`
- Review the tool's help: `python reset_manager_pin.py --help`
- Examine the source code in `reset_manager_pin.py`