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
 * @returns {Promise<Array>} Array of sensor readings
 */
async function fetchHistoricalData(sensorId, startTime = null, endTime = null) {
    try {
        let url = `/api/historical_data?sensor_id=${encodeURIComponent(sensorId)}`;
        
        if (startTime) {
            url += `&start_time=${encodeURIComponent(startTime)}`;
        }
        if (endTime) {
            url += `&end_time=${encodeURIComponent(endTime)}`;
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
 * Calculate time range based on time slice selection
 * @param {string} timeSlice - Time slice ('last_hour', 'today', '24h', '7d', '30d')
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
            startTime = new Date(now.getTime() - (24 * 60 * 60 * 1000)); // Default to 24h
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
    const humidityData = [];
    
    rawData.forEach(reading => {
        const timestamp = new Date(reading.timestamp);
        labels.push(timestamp);
        temperatureData.push(reading.temperature);
        humidityData.push(reading.humidity);
    });
    
    return {
        labels,
        temperatureData,
        humidityData
    };
}

/**
 * Create Chart.js configuration for sensor data
 * @param {Object} processedData - Processed data from processDataForChart
 * @param {string} title - Chart title
 * @returns {Object} Chart.js configuration object
 */
function createChartConfig(processedData, title) {
    return {
        type: 'line',
        data: {
            labels: processedData.labels,
            datasets: [
                {
                    label: 'Temperature (°C)',
                    data: processedData.temperatureData,
                    borderColor: '#007e15',
                    backgroundColor: 'rgba(0, 126, 21, 0.1)',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y'
                },
                {
                    label: 'Humidity (%)',
                    data: processedData.humidityData,
                    borderColor: '#3498db',
                    backgroundColor: 'rgba(52, 152, 219, 0.1)',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y1'
                }
            ]
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
                            if (label.includes('Temperature')) {
                                return `${label}: ${value.toFixed(1)}°C`;
                            } else {
                                return `${label}: ${value.toFixed(1)}%`;
                            }
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        displayFormats: {
                            hour: 'MMM dd HH:mm',
                            day: 'MMM dd',
                            week: 'MMM dd',
                            month: 'MMM yyyy'
                        }
                    },
                    title: {
                        display: true,
                        text: 'Time'
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: {
                        display: true,
                        text: 'Temperature (°C)',
                        color: '#007e15'
                    },
                    grid: {
                        drawOnChartArea: false,
                    },
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: {
                        display: true,
                        text: 'Humidity (%)',
                        color: '#3498db'
                    },
                    grid: {
                        drawOnChartArea: true,
                    },
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
 */
async function renderSensorChart(canvasId, sensorId, timeSlice = '24h', title = 'Sensor Data') {
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
        const rawData = await fetchHistoricalData(sensorId, timeRange.startTime, timeRange.endTime);
        
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
        const config = createChartConfig(processedData, title);
        
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
 * Render dashboard overview chart with data from multiple sensors
 * @param {Array} sensorIds - Array of sensor IDs to include
 * @param {string} timeSlice - Time slice for data range
 */
async function renderDashboardChart(sensorIds, timeSlice = '24h') {
    try {
        const canvas = document.getElementById('dashboardChart');
        if (!canvas) {
            console.error('Dashboard chart canvas not found');
            return;
        }
        
        // For now, just render the first sensor's data
        // In the future, this could be enhanced to show multiple sensors
        if (sensorIds && sensorIds.length > 0) {
            await renderSensorChart('dashboardChart', sensorIds[0], timeSlice, 'Sensor Overview - Last 24 Hours');
        }
        
    } catch (error) {
        console.error('Error rendering dashboard chart:', error);
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
        '24h': 'Last 24 Hours',
        '7d': 'Last 7 Days',
        '30d': 'Last 30 Days'
    };
    return labels[timeSlice] || 'Last 24 Hours';
}

// Export functions for global access
window.renderSensorChart = renderSensorChart;
window.renderDashboardChart = renderDashboardChart;
window.handleTimeSliceChange = handleTimeSliceChange;
window.fetchHistoricalData = fetchHistoricalData;