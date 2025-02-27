# Use a more specific Python version for better reproducibility
FROM python:3.9.18-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

# Install system dependencies and SteamCMD
RUN dpkg --add-architecture i386 && \
    apt-get update && apt-get install -y \
    lib32gcc-s1 \
    lib32stdc++6 \
    libc6-i386 \
    libstdc++6:i386 \
    curl \
    wget \
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/steamcmd \
    && cd /app/steamcmd \
    && wget https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz \
    && tar -xvzf steamcmd_linux.tar.gz \
    && rm steamcmd_linux.tar.gz \
    && ./steamcmd.sh +quit

# Set working directory
WORKDIR /app

# Create necessary directories with correct permissions
RUN mkdir -p /app/downloads /app/public /app/logs /data && \
    chmod -R 755 /app && \
    chmod -R 777 /data  # Ensure write permissions for all users

# Copy dependency file and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Set environment variables
ENV PATH="/app/steamcmd:${PATH}"
ENV LD_LIBRARY_PATH="/app/steamcmd/linux32:${LD_LIBRARY_PATH}"
ENV RAILWAY_VOLUME_MOUNT_PATH="/data"

# Expose ports
EXPOSE ${PORT}
EXPOSE 9090

# Add healthcheck that waits for Gradio to be ready
HEALTHCHECK --interval=30s --timeout=30s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Make start script executable
RUN chmod +x start.sh

# Run the application
CMD ["./start.sh"]
