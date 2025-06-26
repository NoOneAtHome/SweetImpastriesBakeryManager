# Sensor Monitoring Dashboard PRD - Sweet Impastries

## 1. Overview

Sweet Impastries is developing a custom web-based sensor monitoring dashboard to support food safety compliance and operational efficiency. This system will integrate with the SensorPush Gateway Cloud API to retrieve real-time and historical environmental data (e.g., temperature and humidity) from multiple bakery sensors. Data will be stored locally in a SQLite database and visualized for bakery staff in a simple, mobile-friendly web interface. The dashboard will allow staff to quickly identify sensor anomalies, track historical trends, and ensure regulatory compliance for food storage conditions.

## 2. Goals & Objectives

- **Real-time Monitoring**: Display the current readings for each SensorPush device with updates every minute (defined as "near real-time" for this application). Refresh interval should be user-configurable globally in whole-minute increments.
- **Historical Data Access**: View data over selectable time slices: Last hour, Today, Past 24 hours, Past 7 days, Past 30 days.
- **Graphical Visualization**: Line graphs showing temperature and humidity over time.
- **Sensor Filtering**: Filter dashboard data by individual sensor.
- **Mobile-Friendly Design**: Optimized for iPads and tablets.
- **Local Data Storage**: Store data in SQLite for simplicity and persistence.
- **Offline Access**: Deferred to post-MVP phase due to low priority.

## 3. User Stories

### As a Bakery Staff Member
- View live sensor readings.
- Filter by sensor.
- Select time slices for trend analysis.
- View readable line graphs.
- Adjust data refresh rate.
- Use the dashboard on a tablet.

### As a Bakery Manager (PIN-authenticated)
- All Staff permissions.
- Rename sensors.
- Adjust polling intervals.
- Set min/max thresholds.
- Activate/deactivate sensors.
- Configure system settings.
- *(Stretch Goal)* Export historical data.

## 4. Functional Requirements

### 4.1 Data Integration
- Connect to SensorPush API with secure token.
- Retrieve and store timestamp, temperature, humidity, sensor ID/name.

### 4.2 Real-Time Data Display
- Display latest data per sensor.
- Configurable polling interval (global setting, whole minutes only).

### 4.3 Graphing & Visualization
- Line graphs per sensor.
- Time slices: Last hour, Today, 24h, 7d, 30d.
- Zoom and hover for details.

### 4.4 Filtering & Selection
- Filter by sensor.
- Custom sensor names.

### 4.5 Threshold Alerts
- Configurable min/max thresholds per sensor.
- Visual alerts on threshold breach (combination of text color change and icon display).

### 4.6 Settings Panel
- Rename sensors.
- Adjust intervals.
- Set thresholds.
- Toggle sensor activation.

### 4.7 Responsive Design
- Mobile-friendly layout.
- Touch support.

### 4.8 Data Management
- Retain data for minimum 6 months, with automatic purging after 1 year or on-demand deletion.
- *(Stretch Goal)* Export to CSV.

### 4.9 Error Handling and Logging
- Store all errors and stack traces in the database with unique error IDs.
- Display user-facing errors in plain business language.
- Reference database error ID in user error messages for troubleshooting.
- Log system errors for debugging and monitoring purposes.

## 5. Non-Functional Requirements

### 5.1 Performance
- Load graphs in under 2 seconds.

### 5.2 Reliability
- Retry on API failure.

### 5.3 Usability
- Intuitive design for non-technical staff.

### 5.4 Maintainability
- Use Python + Flask/FastAPI for ease of dev.

### 5.5 Scalability
- Support 10+ sensors, 6 months of data.

### 5.6 Security
- SensorPush API credentials (username/password) stored as environment variables.
- OAuth token obtained and managed securely by application.
- PIN-based auth for manager access with session management.
- PIN requirements: minimum 6 characters, numbers only.
- PIN stored using secure hashing.
- Account lockout after 4 failed attempts.
- Initial PIN set via command-line argument on first run (development default: 000000).

## 6. Technical Requirements

### 6.1 Tech Stack
- Python 3.11+, Flask/FastAPI
- SQLite
- Chart.js or Plotly.js
- Docker-based deployment (optimized for small image size)

### 6.2 SensorPush API
- Use `/samples` and `/status` endpoints.
- Auth via token.

### 6.3 Database Schema
**sensors**
- sensor_id (text, PK)
- name (text)
- active (bool)
- min_temp, max_temp (float)
- min_humidity, max_humidity (float)

**sensor_readings**
- id (int, PK)
- sensor_id (FK)
- timestamp (datetime)
- temperature, humidity (float)

### 6.4 API Polling Service
- Background task via `apscheduler` or similar.
- Deduplicate and store readings.

### 6.5 Web Interface
- Responsive graphs.
- Dropdowns for sensor/time slice selection.
- Settings panel.

### 6.6 Authentication
- PIN-based login for Managers only.
- Staff view is read-only.

### 6.7 User Roles
- **Staff**: View only, no login required.
- **Manager**: Full access via PIN login.

## 7. UI/UX Requirements

### 7.1 General Design
- Clean layout, responsive design.
- Color-coded alerting.

### 7.2 Dashboard View
- Sensor list with live data.
- Graph panel with time slice controls.
- Clean and simple graph appearance (specific styling determined in UI design phase).

### 7.3 Settings Panel
- PIN required.
- Thresholds, sensor names, polling rate editable.

### 7.4 Navigation
- Tabs for Dashboard, Settings, About.
- Protected routes for Manager.

### 7.5 Visual Alerts
- Highlight out-of-range data with color change and icon indicators.
- Combined visual approach for threshold breaches.

### 7.6 Accessibility
- Colorblind-safe.
- Touch targets min 44x44px.

## 8. Milestones & Timeline

### Phase 1: Requirements Finalization
- ✅ June 26, 2025

### Phase 2: UI Design & Mockups
- 🎯 June 28, 2025

### Phase 3: Core Backend Dev
- 🎯 Start: June 29, 2025 | End: July 5, 2025

### Phase 4: Frontend Dev
- 🎯 End: July 10, 2025

### Phase 5: Management Features
- 🎯 End: July 14, 2025

### Phase 6: Testing & QA
- 🎯 End: July 17, 2025

### Phase 7: Deployment & Docs
- 🎯 End: July 19, 2025

### Phase 8: Stretch Goals (Optional)
- CSV Export, Offline Mode
- 🎯 Post-MVP, Late July 2025