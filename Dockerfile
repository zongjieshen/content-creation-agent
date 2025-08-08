FROM python:3.11-slim

WORKDIR /app

# Set environment variable to indicate Docker environment
ENV IS_DOCKER=true
ENV DOCKER_CONFIG_PATH=/app/config
ENV DOCKER_DATA_PATH=/app/data

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Create necessary directories and copy config
RUN mkdir -p /app/uploads /app/config /app/data && \
    cp /app/config.yaml /app/config/config.yaml && \
    chmod -R 755 /app/config /app/data

# Expose ports
EXPOSE 8080 8000 8001 8002

# Use the original command
CMD ["python", "main.py"]