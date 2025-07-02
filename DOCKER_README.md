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
DEFAULT_POLLING_INTERVAL=5
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
```

## Data Management Commands

### Purging Sensor Data

To purge all sensor data from the database, you can use the standalone `purge_data.py` script.

**1. Running in a running container:**

If your BakerySensors container is already running, you can execute the script inside it:

```bash
docker exec -it [container_name_or_id] python purge_data.py
```

Replace `[container_name_or_id]` with the actual name or ID of your running BakerySensors Docker container.

**2. One-off execution in a new container:**

For a one-off execution, or for scripting purposes, you can run the script in a new, temporary container. This method is useful if you don't have a container already running or want to ensure a clean environment for the command.

```bash
docker run --rm \
  -v /path/to/your/bakery_sensors_data:/app/instance \
  bakery_sensors_image_name \
  python purge_data.py
```

**3. Running locally (outside Docker):**

If you have the project files locally and want to purge data without using Docker:

```bash
python purge_data.py
```

**Important Notes:**
*   Replace `/path/to/your/bakery_sensors_data` with the actual host path where your `instance` folder (containing `bakery_sensors.sqlite`) is located. This ensures the script operates on your persistent database.
*   Replace `bakery_sensors_image_name` with the name of your Docker image (e.g., `bakery_sensors:latest`).
*   The `--rm` flag ensures the container is removed automatically after the script exits.
*   The script will prompt for confirmation before deleting data. Type `yes` to proceed.
*   The script provides clear feedback about the number of records found and deleted.