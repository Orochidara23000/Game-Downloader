# Use a more specific Python version for better reproducibility
FROM python:3.9.18-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

# Install basic system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy installer script and requirements first
COPY steamcmd_installer.py requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run SteamCMD installer
RUN python steamcmd_installer.py

# Create necessary directories with correct permissions
RUN mkdir -p /app/downloads /app/public /app/logs /data && \
    chmod -R 755 /app && \
    chmod -R 755 /data

# Copy the rest of the application code
COPY . .

# Set environment variables
ENV PATH="/app/steamcmd:${PATH}"
ENV LD_LIBRARY_PATH="/app/steamcmd/linux32:${LD_LIBRARY_PATH}"
ENV RAILWAY_VOLUME_MOUNT_PATH="/data"

# Expose ports
EXPOSE ${PORT}
EXPOSE 9090

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=30s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Make start script executable
RUN chmod +x start.sh

# Run the application
CMD ["./start.sh"]
