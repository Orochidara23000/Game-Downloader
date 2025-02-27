#!/bin/bash
set -e

echo "=== System Information ==="
uname -a
echo "=========================="

# Create and ensure required directories
mkdir -p /app/downloads /app/public /app/logs
mkdir -p /data/downloads /data/public

# Set permissions
chmod -R 755 /app/steamcmd
chmod -R 777 /data

# Set default port
export PORT="${PORT:-8080}"
export HOST="0.0.0.0"

# Output environment variables
echo "=== Environment Variables ==="
echo "PORT: $PORT"
echo "PUBLIC_URL: $PUBLIC_URL"
echo "RAILWAY_STATIC_URL: $RAILWAY_STATIC_URL"
echo "RAILWAY_PUBLIC_DOMAIN: $RAILWAY_PUBLIC_DOMAIN"
echo "============================"

# Link Railway volume if available
if [ -d "/data" ]; then
    ln -sf /data/downloads /app/downloads
    ln -sf /data/public /app/public
    echo "Railway volume mounted and linked"
fi

# Update SteamCMD
echo "Updating SteamCMD..."
python update_steamcmd.py

# Start the cleanup service in background
echo "Starting cleanup service..."
python cleanup.py &

# Start the application
echo "Starting application on port $PORT"
exec python main.py