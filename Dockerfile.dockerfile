FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    METRICS_PORT=9090 \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=8080 \
    GRADIO_ROOT_PATH=/

# Install system dependencies
RUN apt-get update && apt-get install -y \
    lib32gcc-s1 \
    lib32stdc++6 \
    libstdc++6:i386 \
    curl \
    wget \
    procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create necessary directories
RUN mkdir -p /app/downloads /app/public /app/logs /data/downloads /data/public && \
    chmod -R 755 /app && \
    chmod -R 755 /data

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download and install SteamCMD
RUN mkdir -p /app/steamcmd && \
    cd /app/steamcmd && \
    wget https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz && \
    tar -xvzf steamcmd_linux.tar.gz && \
    rm steamcmd_linux.tar.gz && \
    chmod +x steamcmd.sh && \
    ./steamcmd.sh +quit

# Copy application code
COPY . .

# Make scripts executable
RUN chmod +x start.sh
RUN chmod +x /app/steamcmd/steamcmd.sh

# Expose ports
EXPOSE ${PORT}
EXPOSE ${METRICS_PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run application
CMD ["./start.sh"]
