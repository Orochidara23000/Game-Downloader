#!/usr/bin/env python3
"""
Health check service for Steam Game Downloader
- Monitors application health
- Checks SteamCMD functionality
- Reports system metrics
"""
import os
import sys
import requests
import psutil
import logging
import json
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from flask import Flask, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/app/logs/health_check.log")
    ]
)
logger = logging.getLogger("HealthCheck")

# Constants
APP_PORT = int(os.environ.get("PORT", 8080))
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", 8081))
DATA_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/data"))
DOWNLOADS_DIR = DATA_DIR / "downloads"
PUBLIC_DIR = DATA_DIR / "public"
STEAMCMD_PATHS = [
    os.path.join(os.getcwd(), "steamcmd", "steamcmd.sh"),
    "/app/steamcmd/steamcmd.sh",
    "/usr/local/bin/steamcmd",
    shutil.which("steamcmd")
]

# Create Flask app
app = Flask(__name__)

def check_disk_space():
    """Check available disk space"""
    try:
        disk = psutil.disk_usage(str(DATA_DIR))
        return {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "percent_used": disk.percent,
            "status": "ok" if disk.percent < 90 else "warning" if disk.percent < 95 else "critical"
        }
    except Exception as e:
        logger.error(f"Error checking disk space: {e}")
        return {"status": "error", "message": str(e)}

def check_memory():
    """Check system memory"""
    try:
        memory = psutil.virtual_memory()
        return {
            "total_gb": round(memory.total / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "available_gb": round(memory.available / (1024**3), 2),
            "percent_used": memory.percent,
            "status": "ok" if memory.percent < 85 else "warning" if memory.percent < 95 else "critical"
        }
    except Exception as e:
        logger.error(f"Error checking memory: {e}")
        return {"status": "error", "message": str(e)}

def check_app_service():
    """Check if the main application is responding"""
    try:
        response = requests.get(f"http://localhost:{APP_PORT}/health", timeout=5)
        if response.status_code == 200:
            return {"status": "ok", "message": "Application is running"}
        else:
            return {"status": "error", "message": f"Application returned status code {response.status_code}"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to application: {e}")
        return {"status": "error", "message": f"Could not connect to application: {str(e)}"}

def check_steamcmd():
    """Check if SteamCMD is working with detailed path info"""
    messages = []
    found_steamcmd = False

    for steamcmd_path in STEAMCMD_PATHS:
        messages.append(f"Looking for steamcmd at: {steamcmd_path}")
        if os.path.exists(steamcmd_path):
            messages.append("steamcmd found.")
            if os.access(steamcmd_path, os.X_OK):
                messages.append("steamcmd is executable.")
                found_steamcmd = True
                break
            else:
                messages.append(f"WARNING: steamcmd is not executable! Permissions: {oct(os.stat(steamcmd_path).st_mode)}")
        else:
            messages.append(f"ERROR: steamcmd not found in {steamcmd_path}")
            # List directory contents for debugging
            parent_dir = os.path.dirname(steamcmd_path)
            if os.path.exists(parent_dir):
                messages.append(f"Contents of {parent_dir}: {os.listdir(parent_dir)}")
            else:
                messages.append(f"Directory {parent_dir} does not exist!")

    if not found_steamcmd:
        messages.append("ERROR: steamcmd not found in any of the specified locations.")

    return {"status": "ok" if found_steamcmd else "error", "messages": messages}

def check_7z():
    """Check if 7z is installed and accessible"""
    results = []
    for path in ['/usr/bin/7z', '/usr/local/bin/7z', shutil.which("7z")]:
        if path:
            results.append(f"Checking {path}: {os.path.exists(path)}")
    return {"status": "ok", "messages": results}

def check_downloads_dir():
    """Check if downloads directory is accessible"""
    try:
        if not DOWNLOADS_DIR.exists():
            return {"status": "warning", "message": "Downloads directory does not exist"}
            
        # Check if directory is writable
        temp_file = DOWNLOADS_DIR / f"test_{datetime.now().timestamp()}.tmp"
        try:
            with open(temp_file, 'w') as f:
                f.write("test")
            temp_file.unlink()
            return {"status": "ok", "message": "Downloads directory is writable"}
        except Exception as e:
            return {"status": "error", "message": f"Downloads directory is not writable: {str(e)}"}
    except Exception as e:
        logger.error(f"Error checking downloads directory: {e}")
        return {"status": "error", "message": str(e)}

@app.route('/health')
def health():
    """Simple health check endpoint"""
    return jsonify({"status": "healthy"})

@app.route('/status')
def status():
    """Detailed status check"""
    checks = {
        "disk": check_disk_space(),
        "memory": check_memory(),
        "app_service": check_app_service(),
        "steamcmd": check_steamcmd(),
        "7z": check_7z(),
        "downloads_directory": check_downloads_dir(),
        "timestamp": datetime.now().isoformat()
    }
    
    # Determine overall status
    if any(check["status"] == "error" for check in checks.values() if isinstance(check, dict) and "status" in check):
        checks["overall_status"] = "error"
    elif any(check["status"] == "critical" for check in checks.values() if isinstance(check, dict) and "status" in check):
        checks["overall_status"] = "critical"
    elif any(check["status"] == "warning" for check in checks.values() if isinstance(check, dict) and "status" in check):
        checks["overall_status"] = "warning"
    else:
        checks["overall_status"] = "ok"
    
    # Set response status code based on overall status
    status_code = 200
    if checks["overall_status"] in ["error", "critical"]:
        status_code = 500
    elif checks["overall_status"] == "warning":
        status_code = 429
    
    return jsonify(checks), status_code

def main():
    """Main function to run the health check service"""
    try:
        # Create logs directory
        Path("/app/logs").mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Starting health check service on port {HEALTH_PORT}")
        app.run(host='0.0.0.0', port=HEALTH_PORT)
    except Exception as e:
        logger.error(f"Failed to start health check service: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())