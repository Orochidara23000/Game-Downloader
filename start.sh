#!/bin/bash
# start.sh

# Create necessary directories
mkdir -p /app/downloads /app/public /app/logs /data/downloads /data/public

# Set default port
export PORT="${PORT:-8080}"

# Wait for needed system resources
sleep 2

# Ensure proper permissions
chmod -R 755 /app/steamcmd
chmod -R 777 /data

# Link Railway volume if available
if [ -d "/data" ]; then
    ln -sf /data/downloads /app/downloads
    ln -sf /data/public /app/public
    echo "Railway volume mounted and linked"
fi

# Start the application
echo "Starting application on port $PORT"
python main.py 