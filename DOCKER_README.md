# Docker Deployment Instructions

This guide provides instructions for building and running the Bakery Sensors application using Docker containers.

## Building the Docker Image

To build the Docker image for the Bakery Sensors application, run the following command from the project root directory:

```bash
docker build -t bakery-sensors-app .
docker save -o bakery-sensors-app.tar bakery-sensors-app   
```

This command will create a Docker image tagged as `bakery-sensors-app` using the Dockerfile in the current directory.

## Environment Variables Configuration

The application uses environment variables for configuration, which are loaded from a `.env` file in the project root. This file contains sensitive information like API credentials and application settings.

### Creating the .env File

If a `.env` file doesn't exist in your project root, create one by copying the example file:

```bash
cp .env.example .env
```

Then edit the `.env` file with your actual configuration values. Here's an example of the required content:

```env
# SensorPush API Configuration
SENSORPUSH_USERNAME=your_sensorpush_username
SENSORPUSH_PASSWORD=your_sensorpush_password

# Flask Application Configuration
SECRET_KEY=your-secret-key-here
FLASK_ENV=production
DEBUG=false

# Database Configuration
DATABASE_URL=sqlite:///db/sensor_dashboard.db

# Application Settings
DEFAULT_POLLING_INTERVAL=1
DATA_RETENTION_MONTHS=12

# Manager Authentication
MANAGER_PIN_HASH=your_hashed_pin_here

# Session Configuration
SESSION_TIMEOUT=3600
MAX_LOGIN_ATTEMPTS=4

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=sensor_dashboard.log
```

**Important:** Never commit the `.env` file to version control as it contains sensitive credentials. The `.env.example` file is provided as a template.

## Running with Docker Compose

To start the application and all its dependencies using Docker Compose, run:

```bash
docker-compose up -d
```

The `-d` flag runs the containers in detached mode (in the background). The Docker Compose configuration will automatically load environment variables from the `.env` file.

## Accessing the Application

Once the containers are running, you can access the Bakery Sensors application at:

```
http://localhost:8000
```

Open this URL in your web browser to interact with the sensor dashboard and monitoring interface.

## Stopping the Containers

To stop and remove all running containers, use:

```bash
docker-compose down
```

This command will stop all services defined in the docker-compose.yml file and remove the containers.

## Additional Commands

### View Running Containers
```bash
docker-compose ps
```

### View Container Logs
```bash
docker-compose logs
```

### View Logs for a Specific Service
```bash
docker-compose logs [service-name]
```

### Rebuild and Restart
```bash
docker-compose up -d --build