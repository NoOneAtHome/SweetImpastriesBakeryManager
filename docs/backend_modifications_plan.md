# Backend Modifications Plan: Sensor Settings Update

This document outlines the detailed plan for modifying the backend to support a single form submission for updating a sensor's display name, thresholds, and category.

## 1. Changes to `app.py`

The existing `/manager/sensor_settings/<sensor_id>` route will be updated to handle a single POST request containing all the sensor settings data.

**Current Route Context:**
The `manager_sensor_settings` route in `app.py` currently handles multiple actions (`rename`, `toggle_active`, `update_thresholds`, `update_category`) based on an `action` hidden input field. This needs to be refactored to accept all relevant fields in a single POST request for a specific sensor.

**Proposed Modifications:**

*   **Modify the existing `manager_sensor_settings` route to accept `POST` requests for a specific `sensor_id`:**
    *   Change the route decorator to include `/<sensor_id>`: `@app.route('/manager/sensor_settings/<sensor_id>', methods=['GET', 'POST'])`.
    *   Remove the `action` parameter from the form data processing.
    *   Extract all relevant fields (`display_name`, `min_temp`, `max_temp`, `min_humidity`, `max_humidity`, `category`) directly from `request.form`.
    *   Pass these extracted values to a new or modified function in `settings_manager.py`.

*   **Data Extraction (Pseudo-code):**
    ```python
    # Inside the POST block of manager_sensor_settings(sensor_id)
    sensor_id = sensor_id # Already available from route parameter
    display_name = request.form.get('display_name', '').strip()
    min_temp_str = request.form.get('min_temp')
    max_temp_str = request.form.get('max_temp')
    min_humidity_str = request.form.get('min_humidity')
    max_humidity_str = request.form.get('max_humidity')
    category = request.form.get('category')
    ```

*   **Data Validation:**
    *   Perform server-side validation for all incoming data.
    *   Ensure `display_name` is not empty.
    *   Convert threshold values to `float` and handle `ValueError`.
    *   Validate that `min_temp < max_temp` and `min_humidity < max_humidity`.
    *   Validate `min_humidity` and `max_humidity` are within 0-100 range.
    *   Validate `category` against a predefined list of allowed categories (e.g., "freezer", "refrigerator", "ambient", "other").

*   **Call `settings_manager.py`:**
    *   Introduce a new function in `settings_manager.py` (e.g., `update_sensor_full_settings`) that takes `sensor_id`, `display_name`, `min_temp`, `max_temp`, `min_humidity`, `max_humidity`, and `category` as arguments.
    *   Call this function from `app.py` after validation.

*   **Handle Success and Error Responses:**
    *   If `settings_manager.update_sensor_full_settings` returns `True` (success), redirect back to the sensor settings page for that specific sensor with a success message.
    *   If `settings_manager.update_sensor_full_settings` returns `False` (failure) or validation fails, redirect back with an error message.
    *   Use `flash` messages for better user feedback.

**Pseudo-code for `app.py` (modified `manager_sensor_settings`):**

```python
@app.route('/manager/sensor_settings/<sensor_id>', methods=['GET', 'POST'])
@require_manager_auth
def manager_sensor_settings(sensor_id):
    try:
        with get_db_session_context() as db_session:
            sensor = db_session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()
            if not sensor:
                flash(f"Sensor {sensor_id} not found.", 'error')
                return redirect(url_for('manager_settings')) # Redirect to general manager settings if sensor not found

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
                    min_temp, max_temp, min_humidity, max_humidity = None, None, None, None # Set to None to prevent further validation errors

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
                elif not category: # Allow category to be empty/None if not selected
                    category = None

                if errors:
                    for error_msg in errors:
                        flash(error_msg, 'error')
                    # Re-render the page with current sensor data and errors
                    return render_template('manager_sensor_settings.html',
                                           sensor=sensor, # Pass the original sensor object
                                           categories=allowed_categories,
                                           success=request.args.get('success'),
                                           error=request.args.get('error')) # Keep existing flash messages

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
                                   sensor=sensor, # Pass the specific sensor object
                                   categories=categories,
                                   success=request.args.get('success'),
                                   error=request.args.get('error'))

    except Exception as e:
        log_warning(f"Error in sensor settings for {sensor_id}: {str(e)}", "Manager Settings")
        flash("An unexpected error occurred.", 'error')
        return render_template('error.html', error="Failed to load sensor settings"), 500

# The existing /manager/sensor_settings route (without sensor_id) will need to be modified
# to redirect to a list of sensors or the dashboard, or removed if no longer needed.
# For now, I'll assume it will be updated to list all sensors for management.
@app.route('/manager/sensor_settings', methods=['GET'])
@require_manager_auth
def manager_sensor_settings_list():
    try:
        with get_db_session_context() as db_session:
            sensors = db_session.query(Sensor).all()
        categories = ["freezer", "refrigerator", "ambient", "other"]
        return render_template('manager_sensor_settings.html',
                               sensors=sensors, # Pass all sensors
                               categories=categories,
                               success=request.args.get('success'),
                               error=request.args.get('error'))
    except Exception as e:
        log_warning(f"Error loading sensor settings list: {str(e)}", "Manager Settings")
        return render_template('error.html', error="Failed to load sensor settings list"), 500
```

## 2. Changes to `settings_manager.py`

A new static method will be added to the `SettingsManager` class to handle the combined update of sensor properties.

*   **New Function:** `update_sensor_full_settings`
    *   **Signature:**
        ```python
        @staticmethod
        def update_sensor_full_settings(
            sensor_id: str,
            display_name: str,
            min_temp: float,
            max_temp: float,
            min_humidity: float,
            max_humidity: float,
            category: Optional[str]
        ) -> bool:
        ```
    *   **Logic:**
        1.  Obtain a database session.
        2.  Retrieve the `Sensor` object using `sensor_id`.
        3.  If the sensor is not found, log a warning and return `False`.
        4.  Update the `name`, `min_temp`, `max_temp`, `min_humidity`, `max_humidity`, and `category` attributes of the `Sensor` object.
        5.  Commit the changes to the database.
        6.  Handle `SQLAlchemyError` for database transaction issues.
        7.  Return `True` on success, `False` on failure.

*   **Atomicity:**
    *   By performing all updates within a single database session and committing them at once, SQLAlchemy ensures atomicity. If any part of the update fails (e.g., a database constraint violation), the entire transaction will be rolled back, preventing partial updates.

**Pseudo-code for `settings_manager.py`:**

```python
# Add to SettingsManager class
from sqlalchemy.exc import SQLAlchemyError
from database import get_db_session_context
from models import Sensor # Import Sensor model

class SettingsManager:
    # ... existing methods ...

    @staticmethod
    def update_sensor_full_settings(
        sensor_id: str,
        display_name: str,
        min_temp: float,
        max_temp: float,
        min_humidity: float,
        max_humidity: float,
        category: Optional[str]
    ) -> bool:
        """
        Update a sensor's display name, thresholds, and category in a single operation.

        Args:
            sensor_id: The ID of the sensor to update.
            display_name: The new display name for the sensor.
            min_temp: The new minimum temperature threshold.
            max_temp: The new maximum temperature threshold.
            min_humidity: The new minimum humidity threshold.
            max_humidity: The new maximum humidity threshold.
            category: The new category for the sensor (can be None).

        Returns:
            True if the update was successful, False otherwise.
        """
        try:
            with get_db_session_context() as db_session:
                sensor = db_session.query(Sensor).filter(Sensor.sensor_id == sensor_id).first()

                if not sensor:
                    log_warning(f"Sensor with ID '{sensor_id}' not found for update.", "SettingsManager.update_sensor_full_settings")
                    return False

                # Update sensor properties
                sensor.name = display_name
                sensor.min_temp = min_temp
                sensor.max_temp = max_temp
                sensor.min_humidity = min_humidity
                sensor.max_humidity = max_humidity
                sensor.category = category

                db_session.commit()
                log_info(f"Sensor '{sensor_id}' (name: '{display_name}') settings updated successfully.", "SettingsManager.update_sensor_full_settings")
                return True

        except SQLAlchemyError as e:
            log_warning(f"Database error updating sensor '{sensor_id}' settings: {str(e)}", "SettingsManager.update_sensor_full_settings")
            db_session.rollback() # Ensure rollback on error
            return False
        except Exception as e:
            log_warning(f"An unexpected error occurred while updating sensor '{sensor_id}' settings: {str(e)}", "SettingsManager.update_sensor_full_settings")
            return False
```

## 3. Data Model Considerations

*   As confirmed earlier, the `Sensor` model in `models.py` already includes a `category` field (`category = Column(String, nullable=True)`). Therefore, no schema migrations are needed for this task.

## Backend Flow Diagram

```mermaid
graph TD
    A[User Submits Form in manager_sensor_settings.html] --> B(POST /manager/sensor_settings/<sensor_id>)
    B --> C{app.py: manager_sensor_settings(sensor_id)}
    C --> D{Extract Form Data: display_name, min_temp, max_temp, min_humidity, max_humidity, category}
    D --> E{Validate Data}
    E -- Validation Fails --> F{Flash Error Message}
    F --> G{Re-render manager_sensor_settings.html with errors}
    E -- Validation Success --> H{Call SettingsManager.update_sensor_full_settings()}
    H --> I{settings_manager.py: update_sensor_full_settings()}
    I --> J{Get DB Session}
    J --> K{Query Sensor by ID}
    K -- Sensor Not Found --> L{Log Warning, Return False}
    K -- Sensor Found --> M{Update Sensor Object Properties}
    M --> N{Commit DB Session}
    N -- Commit Fails (SQLAlchemyError) --> O{Rollback DB Session, Log Warning, Return False}
    N -- Commit Success --> P{Log Success, Return True}
    I -- Returns False --> Q{Flash Error Message}
    Q --> R{Redirect to /manager/sensor_settings/<sensor_id>}
    I -- Returns True --> S{Flash Success Message}
    S --> R
    R --> T[User Sees Updated Settings or Error]