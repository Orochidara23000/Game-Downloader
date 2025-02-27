import os
import re
import sys
import subprocess
import time
import threading
import logging
import psutil
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import json
import requests
from dotenv import load_dotenv
import gradio as gr
from prometheus_client import Counter, Gauge, Histogram, start_http_server
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import socket
from flask import Flask, render_template_string, request, jsonify

# Load environment variables
load_dotenv()

# Configure logging with more detail
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler("logs/steam_downloader.log"),
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            "logs/steam_downloader.log",
            maxBytes=10485760,  # 10MB
            backupCount=5
        )
    ]
)
logger = logging.getLogger("SteamDownloader")

# Enhanced metrics
DOWNLOAD_COUNTER = Counter('steam_downloads_total', 'Total number of downloads')
DOWNLOAD_ERRORS = Counter('steam_download_errors_total', 'Total number of download errors')
ACTIVE_DOWNLOADS = Gauge('steam_active_downloads', 'Number of active downloads')
DOWNLOAD_SIZE = Histogram('steam_download_size_bytes', 'Download size in bytes')
DOWNLOAD_TIME = Histogram('steam_download_duration_seconds', 'Download duration in seconds')
DISK_USAGE = Gauge('steam_disk_usage_bytes', 'Disk usage in bytes')
MEMORY_USAGE = Gauge('steam_memory_usage_bytes', 'Memory usage in bytes')

# Railway configuration
PORT = int(os.getenv('PORT', '8080'))
HOST = os.getenv('HOST', '0.0.0.0')
PUBLIC_URL = os.getenv('PUBLIC_URL', '')
RAILWAY_STATIC_URL = os.getenv('RAILWAY_STATIC_URL', '')
VOLUME_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '/data')

# Print all environment variables for debugging
logger.info("=== ENVIRONMENT VARIABLES ===")
for key, value in os.environ.items():
    logger.info(f"{key}: {value}")
logger.info("============================")

# Attempt to get external IP (for debugging)
try:
    hostname = socket.gethostname()
    ip_address = socket.gethostbyname(hostname)
    logger.info(f"Hostname: {hostname}")
    logger.info(f"IP Address: {ip_address}")
except Exception as e:
    logger.error(f"Could not get IP: {e}")

# Create Flask app
app = Flask(__name__)

# HTML template for our simple interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Steam Game Downloader</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; max-width: 800px; margin: 0 auto; }
        h1 { color: #333; }
        .container { background: #f5f5f5; padding: 20px; border-radius: 5px; margin-top: 20px; }
        input, button { padding: 10px; margin: 10px 0; }
        button { background: #4CAF50; color: white; border: none; cursor: pointer; }
        button:hover { background: #45a049; }
        #result { margin-top: 20px; padding: 10px; background: #e9e9e9; border-radius: 5px; display: none; }
    </style>
</head>
<body>
    <h1>Steam Game Downloader</h1>
    
    <div class="container">
        <h2>Download a Steam Game</h2>
        <p>Enter the Steam App ID to download.</p>
        
        <div>
            <input type="text" id="appId" placeholder="Enter Steam App ID">
            <button onclick="downloadGame()">Download Game</button>
        </div>
        
        <div id="result"></div>
    </div>

    <script>
        function downloadGame() {
            const appId = document.getElementById('appId').value;
            if (!appId) {
                alert('Please enter a valid App ID');
                return;
            }
            
            fetch('/api/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({app_id: appId}),
            })
            .then(response => response.json())
            .then(data => {
                const resultDiv = document.getElementById('result');
                resultDiv.textContent = data.message;
                resultDiv.style.display = 'block';
            })
            .catch(error => {
                console.error('Error:', error);
                alert('An error occurred. Please try again.');
            });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Serve the main page"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})

@app.route('/api/download', methods=['POST'])
def download():
    """API endpoint to start a download"""
    data = request.json
    app_id = data.get('app_id')
    
    if not app_id:
        return jsonify({"success": False, "message": "Please provide an App ID"})
    
    logger.info(f"Download requested for App ID: {app_id}")
    
    # In a real implementation, we would start the download here
    return jsonify({
        "success": True, 
        "message": f"Download started for App ID: {app_id}"
    })

@app.route('/debug')
def debug():
    """Debug information endpoint"""
    env_vars = {k: v for k, v in os.environ.items() if k.startswith(('PORT', 'HOST', 'PUBLIC', 'RAILWAY'))}
    
    try:
        # Get disk space
        disk = subprocess.check_output("df -h", shell=True).decode('utf-8')
    except:
        disk = "Could not get disk information"
    
    try:
        # Get network information
        network = subprocess.check_output("ifconfig || ip addr", shell=True).decode('utf-8')
    except:
        network = "Could not get network information"
    
    return jsonify({
        "environment": env_vars,
        "disk": disk,
        "network": network
    })

if __name__ == '__main__':
    # Log important information
    logger.info(f"Starting Flask server on port {PORT}")
    logger.info(f"Access the web interface at the Railway-provided URL")
    logger.info(f"Health check available at /health")
    logger.info(f"Debug information available at /debug")
    
    # Start the Flask server
    app.run(host='0.0.0.0', port=PORT)
