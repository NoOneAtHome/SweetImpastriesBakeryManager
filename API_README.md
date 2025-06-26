# Bakery Sensors API Documentation

This document provides comprehensive information on how to use the local REST API endpoints for the Bakery Sensors dashboard application.

## Overview

The Bakery Sensors API provides programmatic access to sensor data through REST endpoints. All endpoints return JSON data and are available on the same host as the dashboard application (typically `http://localhost:5000`).

## Base URL

```
http://localhost:5000
```

## Available Endpoints

### 1. Get All Sensors

**Endpoint:** `GET /api/sensors`

**Description:** Returns a list of all configured sensors with their basic information.

**Parameters:** None

**Response Format:**
```json
[
  {
    "sensor_id": "string",
    "name": "string",
    "active": boolean
  }
]
```

**Example Request:**
```bash
curl -X GET http://localhost:5000/api/sensors
```

**Example Response:**
```json
[
  {
    "sensor_id": "HT.12345",
    "name": "Kitchen Sensor",
    "active": true
  },
  {
    "sensor_id": "HT.67890",
    "name": "Storage Room Sensor",
    "active": true
  }
]
```

### 2. Get Latest Readings

**Endpoint:** `GET /api/sensors/latest`

**Description:** Returns the most recent readings from all active sensors.

**Parameters:** None

**Response Format:**
```json
[
  {
    "sensor_id": "string",
    "temperature": number,
    "humidity": number,
    "timestamp": "string"
  }
]
```

**Example Request:**
```bash
curl -X GET http://localhost:5000/api/sensors/latest
```

**Example Response:**
```json
[
  {
    "sensor_id": "HT.12345",
    "temperature": 22.5,
    "humidity": 45.2,
    "timestamp": "2025-06-26T13:30:00Z"
  },
  {
    "sensor_id": "HT.67890",
    "temperature": 18.7,
    "humidity": 52.1,
    "timestamp": "2025-06-26T13:29:45Z"
  }
]
```

### 3. Get Historical Data

**Endpoint:** `GET /api/sensors/history`

**Description:** Returns historical data for a specific sensor within a specified time range.

**Required Parameters:**
- `sensor_id` (string) - The ID of the sensor
- `time_slice` (string) - Time range for historical data

**Supported Time Slices:**
- `24h` - Last 24 hours
- `7d` - Last 7 days
- `30d` - Last 30 days

**Response Format:**
```json
[
  {
    "sensor_id": "string",
    "temperature": number,
    "humidity": number,
    "timestamp": "string"
  }
]
```

**Example Request:**
```bash
curl -X GET "http://localhost:5000/api/sensors/history?sensor_id=HT.12345&time_slice=24h"
```

**Example Response:**
```json
[
  {
    "sensor_id": "HT.12345",
    "temperature": 22.5,
    "humidity": 45.2,
    "timestamp": "2025-06-26T13:30:00Z"
  },
  {
    "sensor_id": "HT.12345",
    "temperature": 22.3,
    "humidity": 44.8,
    "timestamp": "2025-06-26T13:00:00Z"
  }
]
```

## Usage Examples

### JavaScript/Fetch

```javascript
// Get all sensors
fetch('/api/sensors')
  .then(response => response.json())
  .then(data => console.log('Sensors:', data))
  .catch(error => console.error('Error:', error));

// Get latest readings
fetch('/api/sensors/latest')
  .then(response => response.json())
  .then(data => console.log('Latest readings:', data))
  .catch(error => console.error('Error:', error));

// Get historical data
const sensorId = 'HT.12345';
const timeSlice = '24h';
fetch(`/api/sensors/history?sensor_id=${sensorId}&time_slice=${timeSlice}`)
  .then(response => response.json())
  .then(data => console.log('Historical data:', data))
  .catch(error => console.error('Error:', error));
```

### Python/Requests

```python
import requests
import json

# Base URL
base_url = 'http://localhost:5000'

# Get all sensors
response = requests.get(f'{base_url}/api/sensors')
sensors = response.json()
print('Sensors:', json.dumps(sensors, indent=2))

# Get latest readings
response = requests.get(f'{base_url}/api/sensors/latest')
latest_readings = response.json()
print('Latest readings:', json.dumps(latest_readings, indent=2))

# Get historical data
sensor_id = 'HT.12345'
time_slice = '24h'
response = requests.get(f'{base_url}/api/sensors/history', 
                       params={'sensor_id': sensor_id, 'time_slice': time_slice})
historical_data = response.json()
print('Historical data:', json.dumps(historical_data, indent=2))
```

### cURL

```bash
# Get all sensors
curl -X GET http://localhost:5000/api/sensors

# Get latest readings
curl -X GET http://localhost:5000/api/sensors/latest

# Get historical data
curl -X GET "http://localhost:5000/api/sensors/history?sensor_id=HT.12345&time_slice=24h"

# Pretty print JSON response
curl -X GET http://localhost:5000/api/sensors/latest | python -m json.tool
```

### PowerShell (Windows)

```powershell
# Get all sensors
Invoke-RestMethod -Uri "http://localhost:5000/api/sensors" -Method Get

# Get latest readings
Invoke-RestMethod -Uri "http://localhost:5000/api/sensors/latest" -Method Get

# Get historical data
$sensorId = "HT.12345"
$timeSlice = "24h"
Invoke-RestMethod -Uri "http://localhost:5000/api/sensors/history?sensor_id=$sensorId&time_slice=$timeSlice" -Method Get
```

## Error Handling

All endpoints return appropriate HTTP status codes:

- `200 OK` - Request successful
- `400 Bad Request` - Invalid parameters
- `404 Not Found` - Sensor not found
- `500 Internal Server Error` - Server error

Error responses include a JSON object with error details:

```json
{
  "error": "Error description",
  "status": 400
}
```

## Rate Limiting

Currently, there are no rate limits imposed on API requests. However, it's recommended to implement reasonable request intervals to avoid overwhelming the system.

## Data Formats

### Timestamps
All timestamps are returned in ISO 8601 format (UTC): `YYYY-MM-DDTHH:MM:SSZ`

### Temperature
Temperature values are returned in Celsius as floating-point numbers.

### Humidity
Humidity values are returned as percentages (0-100) as floating-point numbers.

## Integration Tips

1. **Polling Frequency**: For real-time monitoring, poll the `/api/sensors/latest` endpoint every 30-60 seconds.

2. **Error Handling**: Always implement proper error handling for network requests and API responses.

3. **Data Validation**: Validate sensor data before processing, especially temperature and humidity ranges.

4. **Caching**: Consider implementing client-side caching for sensor lists that don't change frequently.

5. **Monitoring**: Use the historical data endpoint for trend analysis and reporting.

## Support

For technical support or questions about the API, please refer to the main project documentation or contact the development team.