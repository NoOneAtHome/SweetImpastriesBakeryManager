/**
 * Charts.js - Chart rendering and data fetching for Bakery Sensors Dashboard
 * 
 * This file contains all the charting logic for displaying sensor data using Chart.js
 */

// Global chart instances to manage chart lifecycle
let dashboardChart = null;
let sensorDetailChart = null;

/**
 * Fetch historical data from the backend API
 * @param {string} sensorId - The sensor ID to fetch data for
 * @param {string} startTime - Start time in ISO format (optional)
 * @param {string} endTime - End time in ISO format (optional)
 * @param {boolean} hourlyAverage - Whether to return hourly averaged data (optional)
 * @returns {Promise<Array>} Array of sensor readings
 */
async function fetchHistoricalData(sensorId, startTime = null, endTime = null, hourlyAverage = false) {
    try {
        let url = `/api/historical_data?sensor_id=${encodeURIComponent(sensorId)}`;
        
        if (startTime) {
            url += `&start_time=${encodeURIComponent(startTime)}`;
        }
        if (endTime) {
            url += `&end_time=${encodeURIComponent(endTime)}`;
        }
        if (hourlyAverage) {
            url += `&hourly_average=true`;
        }
        
        console.log(`Fetching data from: ${url}`);
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log(`Fetched ${data.length} data points for sensor ${sensorId}`);
        
        return data;
    } catch (error) {
        console.error('Error fetching historical data:', error);
        throw error;
    }
}

/**
 * Fetch historical data for multiple sensors from the backend API
 * @param {Array} sensorIds - Array of sensor IDs to fetch data for
 * @param {string} startTime - Start time in ISO format (optional)
 * @param {string} endTime - End time in ISO format (optional)
 * @param {boolean} hourlyAverage - Whether to return hourly averaged data (optional)
 * @returns {Promise<Object>} Object with sensor data organized by sensor ID
 */
async function fetchMultiSensorHistoricalData(sensorIds, startTime = null, endTime = null, hourlyAverage = false) {
    try {
        let url = `/api/multi_sensor_historical_data?sensor_ids=${encodeURIComponent(sensorIds.join(','))}`;
        
        if (startTime) {
            url += `&start_time=${encodeURIComponent(startTime)}`;
        }
        if (endTime) {
            url += `&end_time=${encodeURIComponent(endTime)}`;
        }
        if (hourlyAverage) {
            url += `&hourly_average=true`;
        }
        
        console.log(`Fetching multi-sensor data from: ${url}`);
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log(`Fetched data for ${Object.keys(data).length} sensors`);
        
        return data;
    } catch (error) {
        console.error('Error fetching multi-sensor historical data:', error);
        throw error;
    }
}

/**
 * Calculate time range based on time slice selection
 * @param {string} timeSlice - Time slice ('last_hour', 'today', '4h', '8h', '12h', '24h', '7d', '30d')
 * @returns {Object} Object with startTime and endTime in ISO format
 */
function calculateTimeRange(timeSlice) {
    const now = new Date();
    let startTime;
    
    switch (timeSlice) {
        case 'last_hour':
            startTime = new Date(now.getTime() - (60 * 60 * 1000)); // 1 hour ago
            break;
        case 'today':
            startTime = new Date(now);
            startTime.setHours(0, 0, 0, 0); // Start of today
            break;
        case '4h':
            startTime = new Date(now.getTime() - (4 * 60 * 60 * 1000)); // 4 hours ago
            break;
        case '8h':
            startTime = new Date(now.getTime() - (8 * 60 * 60 * 1000)); // 8 hours ago
            break;
        case '12h':
            startTime = new Date(now.getTime() - (12 * 60 * 60 * 1000)); // 12 hours ago
            break;
        case '24h':
            startTime = new Date(now.getTime() - (24 * 60 * 60 * 1000)); // 24 hours ago
            break;
        case '7d':
            startTime = new Date(now.getTime() - (7 * 24 * 60 * 60 * 1000)); // 7 days ago
            break;
        case '30d':
            startTime = new Date(now.getTime() - (30 * 24 * 60 * 60 * 1000)); // 30 days ago
            break;
        default:
            startTime = new Date(now.getTime() - (12 * 60 * 60 * 1000)); // Default to 12h
    }
    
    return {
        startTime: startTime.toISOString(),
        endTime: now.toISOString()
    };
}

/**
 * Process raw sensor data into Chart.js format
 * @param {Array} rawData - Raw sensor data from API
 * @returns {Object} Processed data for Chart.js
 */
function processDataForChart(rawData) {
    const labels = [];
    const temperatureData = [];
    
    rawData.forEach(reading => {
        // Ensure timestamp is parsed as UTC and then converted to local time
        // The backend sends ISO strings with 'Z' suffix or '+00:00' timezone
        let timestamp;
        if (reading.timestamp.endsWith('Z') || reading.timestamp.includes('+')) {
            // Already has timezone info, parse directly
            timestamp = new Date(reading.timestamp);
        } else {
            // Assume UTC if no timezone info
            timestamp = new Date(reading.timestamp + 'Z');
        }
        
        labels.push(timestamp);
        temperatureData.push(reading.temperature);
    });
    
    return {
        labels,
        temperatureData
    };
}

/**
 * Define color palette for multiple sensor lines
 */
const SENSOR_COLORS = [
    '#007e15',  // Green (original color)
    '#dc3545',  // Red
    '#007bff',  // Blue
    '#fd7e14',  // Orange
    '#6f42c1',  // Purple
    '#20c997',  // Teal
    '#e83e8c',  // Pink
    '#6c757d',  // Gray
    '#28a745',  // Success green
    '#17a2b8',  // Info blue
    '#ffc107',  // Warning yellow
    '#343a40'   // Dark gray
];

/**
 * Process multi-sensor data into Chart.js format
 * @param {Object} multiSensorData - Data from multi-sensor API organized by sensor ID
 * @returns {Object} Processed data for Chart.js with multiple datasets
 */
function processMultiSensorDataForChart(multiSensorData) {
    const datasets = [];
    const allTimestamps = new Set();
    
    // Collect all unique timestamps across all sensors
    Object.values(multiSensorData).forEach(sensorInfo => {
        sensorInfo.data.forEach(reading => {
            // Ensure consistent timestamp parsing
            let timestamp;
            if (reading.timestamp.endsWith('Z') || reading.timestamp.includes('+')) {
                timestamp = reading.timestamp;
            } else {
                timestamp = reading.timestamp + 'Z';
            }
            allTimestamps.add(timestamp);
        });
    });
    
    // Sort timestamps and convert to Date objects
    const sortedTimestamps = Array.from(allTimestamps).sort().map(ts => new Date(ts));
    
    // Create datasets for each sensor with temperature-based separation
    let colorIndex = 0;
    Object.entries(multiSensorData).forEach(([sensorId, sensorInfo]) => {
        const sensorName = sensorInfo.name || sensorId;
        const color = SENSOR_COLORS[colorIndex % SENSOR_COLORS.length];
        
        // Initialize arrays for warm and cold temperature data points
        const warmDataPoints = [];
        const coldDataPoints = [];
        
        // Process each data point and categorize by temperature
        sensorInfo.data.forEach(reading => {
            // Ensure timestamp is parsed as UTC and then converted to local time
            let timestamp;
            if (reading.timestamp.endsWith('Z') || reading.timestamp.includes('+')) {
                // Already has timezone info, parse directly
                timestamp = new Date(reading.timestamp);
            } else {
                // Assume UTC if no timezone info
                timestamp = new Date(reading.timestamp + 'Z');
            }
            
            const dataPoint = {
                x: timestamp,
                y: reading.temperature
            };
            
            // Categorize data points based on temperature thresholds
            if (reading.temperature >= 35) {
                warmDataPoints.push(dataPoint);
            } else if (reading.temperature <= 5) {
                coldDataPoints.push(dataPoint);
            }
            // Note: Temperatures between 5 and 35 degrees are not included in either dataset
        });
        
        // Convert hex color to rgba for background
        const hexToRgba = (hex, alpha) => {
            const r = parseInt(hex.slice(1, 3), 16);
            const g = parseInt(hex.slice(3, 5), 16);
            const b = parseInt(hex.slice(5, 7), 16);
            return `rgba(${r}, ${g}, ${b}, ${alpha})`;
        };
        
        // Create warm temperature dataset if there are warm data points
        if (warmDataPoints.length > 0) {
            datasets.push({
                label: sensorName + ' (Warm)',
                data: warmDataPoints,
                borderColor: color,
                backgroundColor: hexToRgba(color, 0.1),
                borderWidth: 2,
                fill: false,
                tension: 0.1,
                yAxisID: 'yWarm'
            });
        }
        
        // Create cold temperature dataset if there are cold data points
        if (coldDataPoints.length > 0) {
            datasets.push({
                label: sensorName + ' (Cold)',
                data: coldDataPoints,
                borderColor: color,
                backgroundColor: hexToRgba(color, 0.1),
                borderWidth: 2,
                fill: false,
                tension: 0.1,
                yAxisID: 'yCold'
            });
        }
        
        colorIndex++;
    });
    
    return {
        labels: sortedTimestamps,
        datasets: datasets
    };
}

/**
 * Create Chart.js configuration for sensor data
 * @param {Object} processedData - Processed data from processDataForChart or processMultiSensorDataForChart
 * @param {string} title - Chart title
 * @param {boolean} hourlyAverage - Whether the data is hourly averaged
 * @param {boolean} isMultiSensor - Whether this is multi-sensor data (optional)
 * @returns {Object} Chart.js configuration object
 */
function createChartConfig(processedData, title, hourlyAverage = false, isMultiSensor = false) {
    // Handle both single sensor and multi-sensor data formats
    let datasets;
    if (isMultiSensor || Array.isArray(processedData.datasets)) {
        // Multi-sensor data - datasets are already prepared
        datasets = processedData.datasets;
    } else {
        // Single sensor data - create single dataset
        datasets = [
            {
                label: 'Temperature (°C)',
                data: processedData.temperatureData,
                borderColor: '#007e15',
                backgroundColor: 'rgba(0, 126, 21, 0.1)',
                borderWidth: 2,
                fill: false,
                tension: 0.1,
                yAxisID: 'y'
            }
        ];
    }
    
    return {
        type: 'line',
        data: {
            labels: processedData.labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: title,
                    font: {
                        size: 16,
                        weight: 'bold'
                    },
                    color: '#667eea'
                },
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        title: function(context) {
                            const date = new Date(context[0].parsed.x);
                            return date.toLocaleString();
                        },
                        label: function(context) {
                            const label = context.dataset.label;
                            const value = context.parsed.y;
                            return `${label}: ${value.toFixed(1)}°C`;
                        }
                    }
                },
                zoom: {
                    zoom: {
                        wheel: {
                            enabled: true,
                        },
                        pinch: {
                            enabled: true
                        },
                        mode: 'xy',
                        scaleMode: 'xy'
                    },
                    pan: {
                        enabled: true,
                        mode: 'xy',
                        scaleMode: 'xy'
                    }
                }
            },
            scales: {
                x: {
                    type: 'time',
                    adapters: {
                        date: {
                            zone: 'local'  // Force local timezone display
                        }
                    },
                    time: hourlyAverage ? {
                        unit: 'hour',
                        displayFormats: {
                            hour: 'MMM dd HH:00',
                            day: 'MMM dd',
                            week: 'MMM dd',
                            month: 'MMM yyyy'
                        },
                        tooltipFormat: 'MMM dd, yyyy HH:00'
                    } : {
                        displayFormats: {
                            minute: 'HH:mm',
                            hour: 'MMM dd HH:mm',
                            day: 'MMM dd',
                            week: 'MMM dd',
                            month: 'MMM yyyy'
                        },
                        tooltipFormat: 'MMM dd, yyyy HH:mm:ss'
                    },
                    title: {
                        display: true,
                        text: 'Time (Local)'
                    }
                },
                yWarm: {
                    id: 'yWarm',
                    type: 'linear',
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Warm Temp (°C)',
                        color: '#007e15'
                    },
                    grid: {
                        drawOnChartArea: true
                    },
                    min: 35
                },
                yCold: {
                    id: 'yCold',
                    type: 'linear',
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Cold Temp (°C)',
                        color: '#0000FF'
                    },
                    grid: {
                        drawOnChartArea: false
                    },
                    max: 5
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            }
        }
    };
}

/**
 * Render a sensor chart on the specified canvas
 * @param {string} canvasId - ID of the canvas element
 * @param {string} sensorId - Sensor ID to fetch data for
 * @param {string} timeSlice - Time slice for data range
 * @param {string} title - Chart title
 * @param {boolean} hourlyAverage - Whether to display hourly averaged data
 */
async function renderSensorChart(canvasId, sensorId, timeSlice = 'today', title = 'Sensor Data', hourlyAverage = true) {
    try {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas element with ID '${canvasId}' not found`);
            return;
        }
        
        // Show loading state
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#f0f0f0';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#666';
        ctx.font = '16px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Loading chart data...', canvas.width / 2, canvas.height / 2);
        
        // Calculate time range
        const timeRange = calculateTimeRange(timeSlice);
        
        // Fetch data
        const rawData = await fetchHistoricalData(sensorId, timeRange.startTime, timeRange.endTime, hourlyAverage);
        
        if (rawData.length === 0) {
            // Show no data message
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#f0f0f0';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#999';
            ctx.font = '16px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('No data available for the selected time range', canvas.width / 2, canvas.height / 2);
            return;
        }
        
        // Process data
        const processedData = processDataForChart(rawData);
        
        // Create chart configuration
        const config = createChartConfig(processedData, title, hourlyAverage);
        
        // Destroy existing chart if it exists
        if (canvasId === 'dashboardChart' && dashboardChart) {
            dashboardChart.destroy();
        } else if (canvasId === 'sensorDetailChart' && sensorDetailChart) {
            sensorDetailChart.destroy();
        }
        
        // Create new chart
        const chart = new Chart(ctx, config);
        
        // Store chart instance for future reference
        if (canvasId === 'dashboardChart') {
            dashboardChart = chart;
        } else if (canvasId === 'sensorDetailChart') {
            sensorDetailChart = chart;
        }
        
        console.log(`Chart rendered successfully for sensor ${sensorId} on canvas ${canvasId}`);
        
    } catch (error) {
        console.error('Error rendering chart:', error);
        
        // Show error message on canvas
        const canvas = document.getElementById(canvasId);
        if (canvas) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#f8d7da';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#721c24';
            ctx.font = '16px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('Error loading chart data', canvas.width / 2, canvas.height / 2);
        }
    }
}

/**
 * Reset zoom on a chart
 * @param {string} canvasId - ID of the canvas element
 */
function resetChartZoom(canvasId) {
    let chart = null;
    
    if (canvasId === 'dashboardChart' && dashboardChart) {
        chart = dashboardChart;
    } else if (canvasId === 'sensorDetailChart' && sensorDetailChart) {
        chart = sensorDetailChart;
    }
    
    if (chart && chart.resetZoom) {
        chart.resetZoom();
        console.log(`Zoom reset for chart: ${canvasId}`);
    } else {
        console.warn(`Chart not found or resetZoom not available for: ${canvasId}`);
    }
}

/**
 * Render dashboard overview chart with data from multiple sensors
 * @param {Array} sensorIds - Array of sensor IDs to include
 * @param {string} timeSlice - Time slice for data range
 * @param {boolean} hourlyAverage - Whether to display hourly averaged data
 */
async function renderDashboardChart(sensorIds, timeSlice = '12h', hourlyAverage = true) {
    try {
        const canvas = document.getElementById('dashboardChart');
        if (!canvas) {
            console.error('Dashboard chart canvas not found');
            return;
        }
        
        // Show loading state
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#f0f0f0';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#666';
        ctx.font = '16px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Loading chart data...', canvas.width / 2, canvas.height / 2);
        
        if (!sensorIds || sensorIds.length === 0) {
            console.warn('No sensor IDs provided for dashboard chart');
            return;
        }
        
        // Calculate time range
        const timeRange = calculateTimeRange(timeSlice);
        
        // Fetch data for all sensors
        const multiSensorData = await fetchMultiSensorHistoricalData(
            sensorIds,
            timeRange.startTime,
            timeRange.endTime,
            hourlyAverage
        );
        
        if (Object.keys(multiSensorData).length === 0) {
            // Show no data message
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#f0f0f0';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#999';
            ctx.font = '16px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('No data available for the selected sensors and time range', canvas.width / 2, canvas.height / 2);
            return;
        }
        
        // Process data for chart
        const processedData = processMultiSensorDataForChart(multiSensorData);
        
        // Create chart title
        const timeLabel = getTimeSliceLabel(timeSlice);
        const title = `Sensor Overview - ${timeLabel}${hourlyAverage ? ' (Hourly Average)' : ''}`;
        
        // Create chart configuration
        const config = createChartConfig(processedData, title, hourlyAverage, true);
        
        // Destroy existing chart if it exists
        if (dashboardChart) {
            dashboardChart.destroy();
        }
        
        // Create new chart
        dashboardChart = new Chart(ctx, config);
        
        console.log(`Multi-sensor dashboard chart rendered successfully with ${Object.keys(multiSensorData).length} sensors`);
        
    } catch (error) {
        console.error('Error rendering dashboard chart:', error);
        
        // Show error message on canvas
        const canvas = document.getElementById('dashboardChart');
        if (canvas) {
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#f8d7da';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#721c24';
            ctx.font = '16px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('Error loading chart data', canvas.width / 2, canvas.height / 2);
        }
    }
}

/**
 * Handle time slice selection change
 * @param {string} canvasId - Canvas ID to update
 * @param {string} sensorId - Sensor ID
 * @param {string} timeSlice - New time slice
 */
function handleTimeSliceChange(canvasId, sensorId, timeSlice) {
    const title = `Sensor Data - ${getTimeSliceLabel(timeSlice)}`;
    renderSensorChart(canvasId, sensorId, timeSlice, title);
}

/**
 * Get human-readable label for time slice
 * @param {string} timeSlice - Time slice code
 * @returns {string} Human-readable label
 */
function getTimeSliceLabel(timeSlice) {
    const labels = {
        'last_hour': 'Last Hour',
        'today': 'Today',
        '4h': 'Last 4 Hours',
        '8h': 'Last 8 Hours',
        '12h': 'Last 12 Hours',
        '24h': 'Last 24 Hours',
        '7d': 'Last 7 Days',
        '30d': 'Last 30 Days'
    };
    return labels[timeSlice] || 'Last 12 Hours';
}

// Export functions for global access
window.renderSensorChart = renderSensorChart;
window.renderDashboardChart = renderDashboardChart;
window.handleTimeSliceChange = handleTimeSliceChange;
window.fetchHistoricalData = fetchHistoricalData;
window.fetchMultiSensorHistoricalData = fetchMultiSensorHistoricalData;
window.processMultiSensorDataForChart = processMultiSensorDataForChart;