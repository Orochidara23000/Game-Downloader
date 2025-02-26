# Use a more specific Python version for better reproducibility
FROM python:3.9.18-slim

# Install system dependencies and SteamCMD
RUN dpkg --add-architecture i386 && \
    apt-get update && apt-get install -y \
    lib32gcc-s1 \
    lib32stdc++6 \
    libc6-i386 \
    libstdc++6:i386 \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/steamcmd \
    && cd /app/steamcmd \
    && wget https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz \
    && tar -xvzf steamcmd_linux.tar.gz \
    && rm steamcmd_linux.tar.gz \
    && ./steamcmd.sh +quit

# Set working directory
WORKDIR /app

# Copy dependency file and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/downloads /app/public /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/steamcmd:${PATH}"
ENV LD_LIBRARY_PATH="/app/steamcmd/linux32:${LD_LIBRARY_PATH}"
ENV PORT="8080"

# Expose the port (Railway will override this)
EXPOSE ${PORT}

# Add healthcheck with longer interval and timeout
HEALTHCHECK --interval=30s --timeout=30s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Make start script executable and run it
COPY start.sh .
RUN chmod +x start.sh
CMD ["./start.sh"]
