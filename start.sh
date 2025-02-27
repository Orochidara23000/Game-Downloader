#!/bin/bash
set -e

echo "=== System Information ==="
uname -a
echo "=========================="

echo "=== Directory Structure ==="
mkdir -p /app/downloads /app/public /app/logs /data/downloads /data/public
ls -la /app
ls -la /data
echo "==========================="

echo "=== Python Information ==="
which python
python --version
pip --version
echo "=========================="

echo "=== Environment Variables ==="
env | grep -E 'PORT|PUBLIC|RAILWAY|HOST'
echo "============================="

# Set default port
export PORT="${PORT:-8080}"
export HOST="0.0.0.0"

# Link Railway volume if available
if [ -d "/data" ]; then
    ln -sf /data/downloads /app/downloads
    ln -sf /data/public /app/public
    echo "Railway volume mounted and linked"
fi

# Install dependencies explicitly
echo "=== Installing Dependencies ==="
pip install flask requests
echo "=============================="

# Start the application
echo "Starting application on port $PORT"
exec python main.py 