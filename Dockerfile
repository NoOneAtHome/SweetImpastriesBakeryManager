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

# Expose port 8000
EXPOSE 8000

# Define command to run the Flask application using gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]