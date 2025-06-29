# Use Python 3.11 slim buster as base image
FROM python:3.11-slim-buster

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create db directory and set permissions
RUN mkdir -p /app/db && chmod 777 /app/db

# Copy all application files
COPY . .

# Copy the Gunicorn configuration file
COPY gunicorn_config.py /app/gunicorn_config.py

# Expose port 8000
EXPOSE 8000

# Command to run the application with Gunicorn and the new config file
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "-c", "gunicorn_config.py", "app:app"]