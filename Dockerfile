FROM python:3.11-slim

WORKDIR /app

# Set environment variable to indicate Docker environment
ENV IS_DOCKER=true

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

# Create uploads directory
RUN mkdir -p uploads

# Expose ports
EXPOSE 8080 8000 8001 8002

# Command to run the application
CMD ["python", "main.py"]