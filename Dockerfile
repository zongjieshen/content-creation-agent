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

# Create startup script that handles config copying
RUN echo '#!/bin/bash\
\
echo "Setting up Docker environment..."\
\
# Ensure the config directory exists\
mkdir -p /app/config\
\
# Ensure the data directory exists\
mkdir -p /app/data\
\
# Copy config.yaml from source to the config directory if it doesn't exist\
if [ ! -f /app/config/config.yaml ]; then\
    echo "Copying default config.yaml to /app/config/..."\
    cp /app/config.yaml /app/config/config.yaml\
fi\
\
# Ensure proper permissions\
chmod -R 755 /app/data /app/config\
\
echo "Starting application..."\
exec python main.py' > /app/startup.sh && chmod +x /app/startup.sh

# Create necessary directories
RUN mkdir -p uploads

# Expose ports
EXPOSE 8080 8000 8001 8002

# Use startup script as the command
CMD ["/app/startup.sh"]