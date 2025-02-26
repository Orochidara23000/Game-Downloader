#!/bin/bash
# start.sh
export PORT="${PORT:-8080}"
echo "Starting application on port $PORT"
python main.py 