#!/usr/bin/env python3
"""
Steam Game Downloader
A SteamCMD-based game downloader with a Gradio interface
"""

import os
import re
import sys
import subprocess
import time
import threading
import logging
import psutil
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
import json
import requests
from dotenv import load_dotenv
import gradio as gr
from prometheus_client import Counter, Gauge, Histogram, start_http_server
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Response

# Load environment variables
load_dotenv()

#######################################################
# Configuration
#######################################################

class Config:
    """Application configuration"""
    # Server settings
    PORT = int(os.getenv('PORT', '8080'))
    PUBLIC_URL = os.getenv('PUBLIC_URL', '')
    RAILWAY_STATIC_URL = os.getenv('RAILWAY_STATIC_URL', '')
    
    # Paths
    APP_DIR = Path('/app')
    VOLUME_PATH = Path(os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '/data'))
    DOWNLOAD_PATH = Path(os.getenv('DOWNLOAD_PATH', '/app/downloads'))
    PUBLIC_PATH = Path(os.getenv('PUBLIC_PATH', '/app/public'))
    LOG_PATH = APP_DIR / 'logs'
    
    # SteamCMD
    STEAMCMD_PATH = APP_DIR / 'steamcmd' / 'steamcmd.sh'
    
    # Download settings
    MAX_DOWNLOADS = int(os.getenv('MAX_DOWNLOADS', '5'))
    
    # Monitoring
    ENABLE_METRICS = os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    METRICS_PORT = int(os.getenv('METRICS_PORT', '9090'))
    
    # Maintenance
    CLEANUP_INTERVAL = int(os.getenv('CLEANUP_INTERVAL', '3600'))  # 1 hour
    MAX_FILE_AGE = int(os.getenv('MAX_FILE_AGE', '86400'))  # 24 hours
    
    # Create required directories
    @classmethod
    def ensure_directories(cls):
        """Ensure all required directories exist"""
        for directory in [cls.DOWNLOAD_PATH, cls.PUBLIC_PATH, cls.LOG_PATH, cls.VOLUME_PATH]:
            directory.mkdir(parents=True, exist_ok=True)

#######################################################
# Logging Configuration
#######################################################

def setup_logging():
    """Configure application logging"""
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    
    # Ensure log directory exists
    Config.LOG_PATH.mkdir(parents=True, exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format,
        handlers=[
            logging.FileHandler(Config.LOG_PATH / "steam_downloader.log"),
            logging.StreamHandler(),
            logging.handlers.RotatingFileHandler(
                Config.LOG_PATH / "steam_downloader.log",
                maxBytes=10485760,  # 10MB
                backupCount=5
            )
        ]
    )
    return logging.getLogger("SteamDownloader")

logger = setup_logging()

#######################################################
# Metrics
#######################################################

# Application metrics
DOWNLOAD_COUNTER = Counter('steam_downloads_total', 'Total number of downloads')
DOWNLOAD_ERRORS = Counter('steam_download_errors_total', 'Total number of download errors')
ACTIVE_DOWNLOADS = Gauge('steam_active_downloads', 'Number of active downloads')
DOWNLOAD_SIZE = Histogram('steam_download_size_bytes', 'Download size in bytes')
DOWNLOAD_TIME = Histogram('steam_download_duration_seconds', 'Download duration in seconds')
DISK_USAGE = Gauge('steam_disk_usage_bytes', 'Disk usage in bytes')
MEMORY_USAGE = Gauge('steam_memory_usage_bytes', 'Memory usage in bytes')

#######################################################
# SteamCMD Manager
#######################################################

class SteamCMDManager:
    """Manages SteamCMD installation and operations"""
    
    @staticmethod
    def verify_installation():
        """Verify SteamCMD installation"""
        logger.info("Verifying SteamCMD installation...")
        
        if not Config.STEAMCMD_PATH.exists():
            logger.error(f"SteamCMD not found at {Config.STEAMCMD_PATH}")
            return False
            
        if not os.access(Config.STEAMCMD_PATH, os.X_OK):
            logger.error(f"SteamCMD not executable at {Config.STEAMCMD_PATH}")
            return False
            
        try:
            # Test run SteamCMD
            result = subprocess.run(
                [str(Config.STEAMCMD_PATH), '+quit'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"SteamCMD test failed: {result.stderr}")
                return False
                
            logger.info("SteamCMD verification completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"SteamCMD verification failed: {str(e)}")
            return False
    
    @staticmethod
    def update():
        """Update SteamCMD"""
        logger.info("Updating SteamCMD...")
        try:
            result = subprocess.run(
                [str(Config.STEAMCMD_PATH), '+login', 'anonymous', '+quit'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.warning(f"Failed to update SteamCMD: {result.stderr}")
                return False
                
            return True
            
        except Exception as e:
            logger.warning(f"Failed to update SteamCMD: {str(e)}")
            return False
    
    @staticmethod
    def download_game(app_id, username='anonymous', password=None, guard_code=None, 
                      platform='windows', install_dir=None):
        """Download a game using SteamCMD"""
        try:
            install_dir = install_dir or Config.DOWNLOAD_PATH / str(app_id)
            os.makedirs(install_dir, exist_ok=True)
            
            # Build command
            cmd = [
                str(Config.STEAMCMD_PATH),
                '+login'
            ]
            
            # Handle authentication
            if username == 'anonymous':
                cmd.append('anonymous')
            else:
                cmd.append(username)
                if password:
                    cmd.append(password)
                if guard_code:
                    cmd.append(guard_code)
            
            # Add download commands
            cmd.extend([
                f'+force_install_dir {install_dir}',
                f'+app_update {app_id} validate',
                '+quit'
            ])
            
            # Start download process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            return process, install_dir
            
        except Exception as e:
            logger.error(f"Failed to start download for app {app_id}: {str(e)}")
            DOWNLOAD_ERRORS.inc()
            return None, None

#######################################################
# Download Manager
#######################################################

class DownloadManager:
    """Manages game downloads and tracking"""
    _active_downloads = {}
    _lock = threading.Lock()
    
    @classmethod
    def get_active_downloads(cls) -> Dict:
        """Get all active downloads"""
        with cls._lock:
            return cls._active_downloads.copy()
    
    @classmethod
    def start_download(cls, app_id, username='anonymous', password=None, guard_code=None):
        """Start a new download"""
        try:
            # Check active download count
            with cls._lock:
                if len(cls._active_downloads) >= Config.MAX_DOWNLOADS:
                    logger.warning(f"Maximum number of downloads reached ({Config.MAX_DOWNLOADS})")
                    return False, "Maximum number of concurrent downloads reached"
                
                if app_id in cls._active_downloads:
                    logger.warning(f"App {app_id} is already being downloaded")
                    return False, "This game is already being downloaded"
            
            # Start download
            process, install_dir = SteamCMDManager.download_game(
                app_id, username, password, guard_code
            )
            
            if not process:
                return False, "Failed to start download"
            
            # Create download entry
            download_info = {
                'app_id': app_id,
                'status': 'downloading',
                'process': process,
                'install_dir': install_dir,
                'start_time': time.time(),
                'progress': 0,
                'eta': None,
                'speed': None,
                'size': None,
                'username': username
            }
            
            # Add to active downloads
            with cls._lock:
                cls._active_downloads[app_id] = download_info
                ACTIVE_DOWNLOADS.set(len(cls._active_downloads))
            
            # Start monitoring thread
            threading.Thread(
                target=cls._monitor_download,
                args=(app_id,),
                daemon=True
            ).start()
            
            DOWNLOAD_COUNTER.inc()
            logger.info(f"Started download for app {app_id}")
            return True, "Download started"
            
        except Exception as e:
            logger.error(f"Error starting download for app {app_id}: {str(e)}")
            DOWNLOAD_ERRORS.inc()
            return False, f"Error: {str(e)}"
    
    @classmethod
    def _monitor_download(cls, app_id):
        """Monitor download progress"""
        try:
            with cls._lock:
                if app_id not in cls._active_downloads:
                    return
                
                download = cls._active_downloads[app_id]
                process = download['process']
            
            start_time = download['start_time']
            output = ""
            
            while process.poll() is None:
                line = process.stdout.readline().strip()
                if line:
                    output += line + "\n"
                    
                    # Update progress based on output
                    progress_info = cls._parse_progress(line, start_time)
                    if progress_info:
                        with cls._lock:
                            if app_id in cls._active_downloads:
                                cls._active_downloads[app_id].update(progress_info)
                
                time.sleep(0.1)
            
            # Process completed
            exit_code = process.returncode
            
            with cls._lock:
                if app_id in cls._active_downloads:
                    if exit_code == 0:
                        cls._active_downloads[app_id]['status'] = 'completed'
                        cls._active_downloads[app_id]['progress'] = 100
                        logger.info(f"Download completed for app {app_id}")
                        
                        # Generate download links
                        cls._generate_download_links(app_id)
                    else:
                        cls._active_downloads[app_id]['status'] = 'failed'
                        logger.error(f"Download failed for app {app_id} with exit code {exit_code}")
                        DOWNLOAD_ERRORS.inc()
                    
                    # Clean up process reference
                    cls._active_downloads[app_id]['process'] = None
                    ACTIVE_DOWNLOADS.set(len([d for d in cls._active_downloads.values() if d['status'] == 'downloading']))
            
        except Exception as e:
            logger.error(f"Error monitoring download for app {app_id}: {str(e)}")
            with cls._lock:
                if app_id in cls._active_downloads:
                    cls._active_downloads[app_id]['status'] = 'failed'
                    cls._active_downloads[app_id]['error'] = str(e)
                    cls._active_downloads[app_id]['process'] = None
                    ACTIVE_DOWNLOADS.set(len([d for d in cls._active_downloads.values() if d['status'] == 'downloading']))
            DOWNLOAD_ERRORS.inc()
    
    @staticmethod
    def _parse_progress(line, start_time):
        """Parse progress information from SteamCMD output"""
        progress_info = {}
        
        # Extract progress percentage
        progress_match = re.search(r'Update state \(0x\d+\) (\d+)\.(\d+)', line)
        if progress_match:
            progress = int(progress_match.group(1))
            progress_info['progress'] = min(progress, 100)
            
            # Calculate ETA
            if progress > 0:
                elapsed = time.time() - start_time
                eta = elapsed * (100 - progress) / progress
                progress_info['eta'] = eta
                progress_info['elapsed'] = elapsed
        
        # Extract download speed
        speed_match = re.search(r'downloading, progress: (\d+.\d+) MiB', line)
        if speed_match:
            size = float(speed_match.group(1))
            progress_info['size'] = size * 1024 * 1024  # Convert to bytes
        
        return progress_info
    
    @classmethod
    def _generate_download_links(cls, app_id):
        """Generate download links for completed download"""
        try:
            with cls._lock:
                if app_id not in cls._active_downloads:
                    return
                
                download = cls._active_downloads[app_id]
                install_dir = download['install_dir']
            
            # Create public directory if needed
            public_dir = Config.PUBLIC_PATH / str(app_id)
            public_dir.mkdir(parents=True, exist_ok=True)
            
            # Create symlinks or copy files
            links = []
            for root, _, files in os.walk(install_dir):
                for file in files:
                    file_path = Path(root) / file
                    rel_path = file_path.relative_to(install_dir)
                    public_path = public_dir / rel_path
                    
                    # Create parent directories
                    public_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Create symlink or copy
                    try:
                        if not public_path.exists():
                            # Try symlink first
                            try:
                                os.symlink(file_path, public_path)
                            except OSError:
                                # Fall back to copy if symlink fails
                                shutil.copy2(file_path, public_path)
                    except Exception as e:
                        logger.error(f"Failed to create link for {file_path}: {str(e)}")
                    
                    # Generate URL
                    if public_path.exists():
                        url_path = f"/public/{app_id}/{rel_path}"
                        links.append({
                            'filename': file,
                            'size': file_path.stat().st_size,
                            'path': str(rel_path),
                            'url': url_path
                        })
            
            # Update download with links
            with cls._lock:
                if app_id in cls._active_downloads:
                    cls._active_downloads[app_id]['links'] = links
            
        except Exception as e:
            logger.error(f"Error generating download links for app {app_id}: {str(e)}")
    
    @classmethod
    def get_download_status(cls, app_id):
        """Get status of a specific download"""
        with cls._lock:
            return cls._active_downloads.get(app_id)
    
    @classmethod
    def cancel_download(cls, app_id):
        """Cancel an active download"""
        with cls._lock:
            if app_id not in cls._active_downloads:
                return False, "Download not found"
            
            download = cls._active_downloads[app_id]
            if download['status'] != 'downloading':
                return False, f"Download is in {download['status']} state and cannot be cancelled"
            
            process = download['process']
            if process:
                try:
                    process.terminate()
                    download['status'] = 'cancelled'
                    download['process'] = None
                    ACTIVE_DOWNLOADS.set(len([d for d in cls._active_downloads.values() if d['status'] == 'downloading']))
                    logger.info(f"Download cancelled for app {app_id}")
                    return True, "Download cancelled"
                except Exception as e:
                    logger.error(f"Failed to cancel download for app {app_id}: {str(e)}")
                    return False, f"Failed to cancel download: {str(e)}"
            else:
                return False, "Download process not found"

#######################################################
# Maintenance Tasks
#######################################################

def cleanup_old_files(directory, max_age_hours=24):
    """Clean up files older than the specified age"""
    try:
        now = datetime.now()
        max_age = timedelta(hours=max_age_hours)
        directory_path = Path(directory)
        
        if not directory_path.exists():
            logger.warning(f"Directory does not exist: {directory}")
            return
            
        for item in directory_path.glob('**/*'):
            if item.is_file():
                file_age = now - datetime.fromtimestamp(item.stat().st_mtime)
                if file_age > max_age:
                    try:
                        item.unlink()
                        logger.info(f"Removed old file: {item}")
                    except Exception as e:
                        logger.error(f"Failed to remove file {item}: {str(e)}")
    except Exception as e:
        logger.error(f"Error in cleanup_old_files: {str(e)}")

def update_system_metrics():
    """Update system metrics for monitoring"""
    try:
        # Update disk usage metrics
        disk = shutil.disk_usage(Config.VOLUME_PATH)
        DISK_USAGE.set(disk.used)
        
        # Update memory usage metrics
        MEMORY_USAGE.set(psutil.Process().memory_info().rss)
    except Exception as e:
        logger.error(f"Error updating system metrics: {str(e)}")

def cleanup_background():
    """Background task for cleanup and metrics update"""
    while True:
        try:
            # Clean up old downloads
            cleanup_old_files(Config.DOWNLOAD_PATH, max_age_hours=24)
            cleanup_old_files(Config.PUBLIC_PATH, max_age_hours=48)
            
            # Clean up old logs
            cleanup_old_files(Config.LOG_PATH, max_age_hours=72)
            
            # Update metrics
            update_system_metrics()
            
            logger.debug("Cleanup and metrics update completed")
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")
        
        time.sleep(Config.CLEANUP_INTERVAL)

#######################################################
# API Endpoints
#######################################################

# Create FastAPI app
api = FastAPI(
    title="Steam Game Downloader",
    description="A SteamCMD-based game downloader with monitoring and health checks",
    version="1.0.0"
)

@api.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check if SteamCMD is available
        if not Config.STEAMCMD_PATH.exists():
            return Response(
                content=json.dumps({
                    "status": "unhealthy",
                    "reason": "SteamCMD not found",
                    "timestamp": datetime.utcnow().isoformat()
                }),
                status_code=503,
                media_type="application/json"
            )
        
        # Check if required directories exist and are writable
        required_dirs = [Config.DOWNLOAD_PATH, Config.PUBLIC_PATH, Config.LOG_PATH, Config.VOLUME_PATH]
        for directory in required_dirs:
            if not directory.exists():
                return Response(
                    content=json.dumps({
                        "status": "unhealthy",
                        "reason": f"Required directory missing: {directory}",
                        "timestamp": datetime.utcnow().isoformat()
                    }),
                    status_code=503,
                    media_type="application/json"
                )
            if not os.access(directory, os.W_OK):
                return Response(
                    content=json.dumps({
                        "status": "unhealthy",
                        "reason": f"Directory not writable: {directory}",
                        "timestamp": datetime.utcnow().isoformat()
                    }),
                    status_code=503,
                    media_type="application/json"
                )
        
        # Check system resources
        disk = shutil.disk_usage(Config.VOLUME_PATH)
        if disk.free < 1024 * 1024 * 1024:  # Less than 1GB free
            return Response(
                content=json.dumps({
                    "status": "unhealthy",
                    "reason": "Insufficient disk space",
                    "timestamp": datetime.utcnow().isoformat()
                }),
                status_code=503,
                media_type="application/json"
            )
        
        # Update metrics
        update_system_metrics()
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "steamcmd_status": "available"
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return Response(
            content=json.dumps({
                "status": "unhealthy",
                "reason": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }),
            status_code=503,
            media_type="application/json"
        )

@api.get("/metrics/system")
async def get_metrics():
    """System metrics endpoint"""
    try:
        disk = shutil.disk_usage(Config.VOLUME_PATH)
        memory = psutil.virtual_memory()
        
        return {
            "disk_total": disk.total,
            "disk_used": disk.used,
            "disk_free": disk.free,
            "memory_total": memory.total,
            "memory_used": memory.used,
            "memory_free": memory.available,
            "cpu_percent": psutil.cpu_percent(),
            "active_downloads": ACTIVE_DOWNLOADS._value.get(),
            "total_downloads": DOWNLOAD_COUNTER._value.get(),
            "error_count": DOWNLOAD_ERRORS._value.get()
        }
    except Exception as e:
        logger.error(f"Error getting metrics: {str(e)}")
        return {"error": str(e)}, 500

@api.get("/status")
async def get_status():
    """Application status endpoint"""
    return {
        "status": "running",
        "version": "1.0.0",
        "uptime": time.time() - psutil.Process().create_time(),
        "active_downloads": len([d for d in DownloadManager.get_active_downloads().values() if d['status'] == 'downloading']),
        "public_url": Config.PUBLIC_URL,
        "railway_url": Config.RAILWAY_STATIC_URL,
        "volume_path": str(Config.VOLUME_PATH)
    }

@api.get("/downloads")
async def list_downloads():
    """List all downloads"""
    active_downloads = DownloadManager.get_active_downloads()
    
    # Filter sensitive information
    result = {}
    for app_id, download in active_downloads.items():
        result[app_id] = {
            'app_id': download['app_id'],
            'status': download['status'],
            'progress': download['progress'],
            'eta': download['eta'],
            'speed': download['speed'],
            'size': download['size'],
            'start_time': download['start_time'],
            'links': download.get('links', [])
        }
    
    return result

#######################################################
# Gradio Interface
#######################################################

def create_gradio_interface():
    """Create Gradio web interface"""
    with gr.Blocks(title="Steam Game Downloader") as interface:
        gr.Markdown("# Steam Game Downloader")
        gr.Markdown("Enter your Steam credentials and app ID to download games")
        
        with gr.Row():
            with gr.Column():
                steam_username = gr.Textbox(label="Steam Username", placeholder="anonymous", value="anonymous")
                steam_password = gr.Textbox(label="Steam Password", type="password", visible=False)
                steam_guard = gr.Textbox(label="Steam Guard Code", visible=False)
                app_id = gr.Textbox(label="App ID", placeholder="Enter Steam App ID")
                
                def toggle_login_fields(username):
                    return {
                        steam_password: gr.update(visible=username != "anonymous"),
                        steam_guard: gr.update(visible=username != "anonymous")
                    }
                
                steam_username.change(toggle_login_fields, inputs=steam_username, outputs=[steam_password, steam_guard])
                
                download_btn = gr.Button("Download Game")
                status_text = gr.Markdown("Ready to download")
            
            with gr.Column():
                download_info = gr.JSON(label="Download Status")
                refresh_btn = gr.Button("Refresh Status")
        
        def start_download(username, password, guard, game_id):
            if not game_id:
                return "Please enter an App ID"
            
            success, message = DownloadManager.start_download(
                game_id,
                username=username,
                password=password if username != "anonymous" else None,
                guard_code=guard if username != "anonymous" else None
            )
            
            if success:
                return f"Download started for App ID {game_id}"
            else:
                return f"Error: {message}"
        
        def get_status():
            downloads = DownloadManager.get_active_downloads()
            # Filter sensitive info
            for download in downloads.values():
                if 'process' in download:
                    download['process'] = str(download['process'])
            return downloads
        
        download_btn.click(
            start_download,
            inputs=[steam_username, steam_password, steam_guard, app_id],
            outputs=status_text
        )
        
        refresh_btn.click(get_status, outputs=download_info)
        
        # Auto-refresh status every 5 seconds
        gr.on(
            triggers=[interface.load, gr.every(5)],
            fn=get_status,
            outputs=download_info
        )
    
    return interface

#######################################################
# Main Application
#######################################################

def main():
    """Main application entry point"""
    try:
        # Ensure required directories exist
        Config.ensure_directories()
        
        # Verify SteamCMD installation
        if not SteamCMDManager.verify_installation():
            logger.error("SteamCMD verification failed. Exiting.")
            sys.exit(1)
        
        # Update SteamCMD
        SteamCMDManager.update()
        
        # Create Gradio interface
        gradio_app = create_gradio_interface()
        
        # Log startup information
        logger.info(f"Starting server on port {Config.PORT}")
        logger.info(f"Public URL: {Config.PUBLIC_URL}")
        logger.info(f"Railway Static URL: {Config.RAILWAY_STATIC_URL}")
        logger.info(f"Volume Path: {Config.VOLUME_PATH}")
        
        # Start background tasks
        background_thread = threading.Thread(target=cleanup_background, daemon=True)
        background_thread.start()
        
        # Start metrics server if enabled
        if Config.ENABLE_METRICS:
            start_http_server(Config.METRICS_PORT)
            logger.info(f"Metrics server started on port {Config.METRICS_PORT}")
        
        # Mount Gradio app to FastAPI
        final_app = gr.mount_gradio_app(api, gradio_app, path="/")
        
        # Start the server
        uvicorn.run(
            final_app,
            host="0.0.0.0",
            port=Config.PORT,
            log_level="info",
            proxy_headers=True,
            forwarded_allow_ips="*"
        )
    
    except Exception as e:
        logger.critical(f"Fatal error in main application: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
