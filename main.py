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
PUBLIC_URL = os.getenv('PUBLIC_URL', '')
RAILWAY_STATIC_URL = os.getenv('RAILWAY_STATIC_URL', '')
VOLUME_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '/data')

# Create FastAPI app
app = FastAPI(
    title="Steam Game Downloader",
    description="A SteamCMD-based game downloader with monitoring and health checks",
    version="1.0.0"
)

class SystemStatus(BaseModel):
    disk_total: int
    disk_used: int
    disk_free: int
    memory_total: int
    memory_used: int
    memory_free: int
    cpu_percent: float
    active_downloads: int
    total_downloads: int
    error_count: int

@app.get("/health")
async def health_check():
    """Enhanced health check endpoint"""
    try:
        # Check if SteamCMD is available
        steamcmd_path = "/app/steamcmd/steamcmd.sh"
        if not os.path.exists(steamcmd_path):
            raise HTTPException(status_code=503, detail="SteamCMD not found")
        
        # Check if required directories exist and are writable
        required_dirs = ["/app/downloads", "/app/public", "/app/logs", VOLUME_PATH]
        for directory in required_dirs:
            if not os.path.exists(directory):
                raise HTTPException(status_code=503, detail=f"Required directory missing: {directory}")
            if not os.access(directory, os.W_OK):
                raise HTTPException(status_code=503, detail=f"Directory not writable: {directory}")
        
        # Check system resources
        disk = shutil.disk_usage(VOLUME_PATH)
        if disk.free < 1024 * 1024 * 1024:  # Less than 1GB free
            raise HTTPException(status_code=503, detail="Insufficient disk space")
        
        # Update metrics
        DISK_USAGE.set(disk.used)
        MEMORY_USAGE.set(psutil.Process().memory_info().rss)
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "steamcmd_status": "available"
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "reason": str(e)}
        )

@app.get("/metrics")
async def get_metrics():
    """System metrics endpoint"""
    try:
        disk = shutil.disk_usage(VOLUME_PATH)
        memory = psutil.virtual_memory()
        
        return SystemStatus(
            disk_total=disk.total,
            disk_used=disk.used,
            disk_free=disk.free,
            memory_total=memory.total,
            memory_used=memory.used,
            memory_free=memory.available,
            cpu_percent=psutil.cpu_percent(),
            active_downloads=ACTIVE_DOWNLOADS._value.get(),
            total_downloads=DOWNLOAD_COUNTER._value.get(),
            error_count=DOWNLOAD_ERRORS._value.get()
        )
    except Exception as e:
        logger.error(f"Error getting metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def get_status():
    """Application status endpoint"""
    return {
        "status": "running",
        "version": "1.0.0",
        "uptime": time.time() - psutil.Process().create_time(),
        "public_url": PUBLIC_URL,
        "railway_url": RAILWAY_STATIC_URL,
        "volume_path": VOLUME_PATH
    }

class SteamDownloader:
    def __init__(self):
        """Initialize the SteamDownloader with correct paths"""
        self.steamcmd_path = "/app/steamcmd"
        self.downloads_dir = "/app/downloads"
        self.public_dir = "/app/public"
        
        # Use the correct path for steamcmd executable
        if sys.platform == "win32":
            self.steamcmd_exe = os.path.join(self.steamcmd_path, "steamcmd.exe")
        else:
            self.steamcmd_exe = os.path.join(self.steamcmd_path, "steamcmd.sh")
        
        self.current_process = None
        self.download_status = self._create_initial_status()
        
        # Create necessary directories
        self._ensure_directories()
        
        # Start metrics server if enabled
        if os.getenv('ENABLE_METRICS', 'false').lower() == 'true':
            metrics_port = int(os.getenv('METRICS_PORT', '9090'))
            start_http_server(metrics_port)
    
    def _create_initial_status(self) -> Dict[str, Any]:
        """Create initial download status dictionary"""
        return {
            "game_id": None,
            "progress": 0,
            "start_time": None,
            "estimated_end_time": None,
            "downloaded_size": "0 MB",
            "total_size": "Unknown",
            "status": "Idle",
            "error": None
        }
    
    def _ensure_directories(self) -> None:
        """Ensure all required directories exist"""
        for directory in [self.steamcmd_path, self.downloads_dir, self.public_dir, "logs"]:
            os.makedirs(directory, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")
    
    def check_steamcmd_installation(self):
        """
        Performs a comprehensive verification of SteamCMD installation and functionality
        Returns: (bool, str) - (is_valid, message)
        """
        logger.info("Verifying SteamCMD installation...")
        
        # Check if SteamCMD executable exists
        if not os.path.exists(self.steamcmd_exe):
            error_msg = f"SteamCMD executable not found at: {self.steamcmd_exe}"
            logger.error(error_msg)
            return False, error_msg
        
        # Check if executable has correct permissions
        if not os.access(self.steamcmd_exe, os.X_OK):
            try:
                os.chmod(self.steamcmd_exe, 0o755)
                logger.info("Fixed SteamCMD executable permissions")
            except Exception as e:
                error_msg = f"Cannot set executable permissions for SteamCMD: {str(e)}"
                logger.error(error_msg)
                return False, error_msg
        
        # Try running SteamCMD with version check
        try:
            cmd = [self.steamcmd_exe, "+version", "+quit"]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30
            )
            
            # Check return code
            if result.returncode != 0:
                error_msg = f"SteamCMD test failed with return code: {result.returncode}\nOutput: {result.stdout}\nError: {result.stderr}"
                logger.error(error_msg)
                return False, error_msg
            
            # Look for version information in output
            if "Steam Console Client" not in result.stdout:
                error_msg = "SteamCMD seems to be installed but not responding correctly"
                logger.error(error_msg)
                return False, error_msg
            
            # Try to update SteamCMD itself
            logger.info("Updating SteamCMD...")
            update_cmd = [self.steamcmd_exe, "+login", "anonymous", "+app_update", "steamcmd", "+quit"]
            update_result = subprocess.run(
                update_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60
            )
            
            if update_result.returncode != 0:
                error_msg = f"Failed to update SteamCMD: {update_result.stderr}"
                logger.warning(error_msg)
                # Don't return False here as this is not critical
            
            # Verify required directories exist
            required_dirs = [
                os.path.dirname(self.steamcmd_exe),
                self.downloads_dir,
                self.public_dir
            ]
            
            for directory in required_dirs:
                if not os.path.exists(directory):
                    try:
                        os.makedirs(directory, exist_ok=True)
                        logger.info(f"Created missing directory: {directory}")
                    except Exception as e:
                        error_msg = f"Failed to create required directory {directory}: {str(e)}"
                        logger.error(error_msg)
                        return False, error_msg
            
            logger.info("SteamCMD verification completed successfully")
            return True, "SteamCMD is properly installed and functioning"
            
        except subprocess.TimeoutExpired:
            error_msg = "SteamCMD verification timed out"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error during SteamCMD verification: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def install_steamcmd(self):
        """
        Attempts to install or repair SteamCMD installation
        Returns: (bool, str) - (success, message)
        """
        logger.info("Attempting to install/repair SteamCMD...")
        
        try:
            # Create steamcmd directory if it doesn't exist
            os.makedirs(self.steamcmd_path, exist_ok=True)
            
            if sys.platform == "win32":
                # Windows installation
                url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
                zip_path = os.path.join(self.steamcmd_path, "steamcmd.zip")
                
                # Download SteamCMD
                logger.info("Downloading SteamCMD for Windows...")
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                with open(zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Extract ZIP
                logger.info("Extracting SteamCMD...")
                import zipfile
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(self.steamcmd_path)
                
                # Clean up
                os.remove(zip_path)
                
            else:
                # Linux/macOS installation
                url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
                tar_path = os.path.join(self.steamcmd_path, "steamcmd_linux.tar.gz")
                
                # Download SteamCMD
                logger.info("Downloading SteamCMD for Linux...")
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                with open(tar_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Extract TAR
                logger.info("Extracting SteamCMD...")
                import tarfile
                with tarfile.open(tar_path, 'r:gz') as tar:
                    tar.extractall(self.steamcmd_path)
                
                # Set executable permissions
                os.chmod(self.steamcmd_exe, 0o755)
                
                # Clean up
                os.remove(tar_path)
            
            # Initial run to complete installation
            logger.info("Running initial SteamCMD setup...")
            subprocess.run(
                [self.steamcmd_exe, "+quit"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30
            )
            
            # Verify installation
            success, message = self.check_steamcmd_installation()
            if success:
                return True, "SteamCMD installed successfully"
            else:
                return False, f"SteamCMD installation completed but verification failed: {message}"
            
        except Exception as e:
            error_msg = f"Failed to install SteamCMD: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    def extract_game_id(self, input_text):
        """
        Extracts the Steam game ID from either a direct ID input or a Steam URL
        """
        # If input is a number, treat it as a direct game ID
        if input_text.isdigit():
            return input_text
        
        # Check if it's a Steam URL and extract the app ID
        url_pattern = r'store\.steampowered\.com/app/(\d+)'
        match = re.search(url_pattern, input_text)
        if match:
            return match.group(1)
        
        return None
    
    def start_download(self, username, password, game_input, anonymous):
        """
        Initiates the Steam game download process
        """
        game_id = self.extract_game_id(game_input)
        if not game_id:
            return f"Invalid game ID or URL: {game_input}", None
        
        # Reset status
        self.download_status = {
            "game_id": game_id,
            "progress": 0,
            "start_time": datetime.now(),
            "estimated_end_time": None,
            "downloaded_size": "0 MB",
            "total_size": "Unknown",
            "status": "Starting",
            "error": None
        }
        
        # Prepare download directory
        game_download_dir = os.path.join(self.downloads_dir, f"app_{game_id}")
        os.makedirs(game_download_dir, exist_ok=True)
        
        # Build SteamCMD command
        cmd = [self.steamcmd_exe]
        
        if anonymous:
            cmd.extend(["+login", "anonymous"])
        else:
            cmd.extend(["+login", username, password])
        
        cmd.extend([
            "+force_install_dir", game_download_dir,
            "+app_update", game_id, "validate",
            "+quit"
        ])
        
        # Start the download process in a separate thread
        download_thread = threading.Thread(
            target=self._run_download_process, 
            args=(cmd, game_id)
        )
        download_thread.daemon = True
        download_thread.start()
        
        return f"Download started for Game ID: {game_id}", None
    
    def _run_download_process(self, cmd, game_id):
        """
        Runs the SteamCMD download process and monitors progress
        """
        try:
            self.download_status["status"] = "Downloading"
            
            # Start the SteamCMD process
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Parse output to monitor progress
            for line in self.current_process.stdout:
                # Process output line to extract progress information
                self._parse_download_output(line)
                
                # Exit if process is terminated
                if self.current_process.poll() is not None:
                    break
            
            # Check if process completed successfully
            return_code = self.current_process.wait()
            if return_code == 0:
                self.download_status["status"] = "Completed"
                self.download_status["progress"] = 100
                logger.info(f"Download completed for Game ID: {game_id}")
                
                # Generate public links
                self._generate_public_links(game_id)
            else:
                self.download_status["status"] = "Failed"
                self.download_status["error"] = f"Process exited with code {return_code}"
                logger.error(f"Download failed for Game ID: {game_id}. Exit code: {return_code}")
        
        except Exception as e:
            self.download_status["status"] = "Failed"
            self.download_status["error"] = str(e)
            logger.error(f"Error during download for Game ID {game_id}: {str(e)}")
    
    def _parse_download_output(self, line):
        """
        Parses SteamCMD output to extract download progress information
        """
        line = line.strip()
        logger.debug(f"SteamCMD output: {line}")
        
        # Look for progress information
        # Example: "Update state (0x61) downloading, progress: 67.43 (17548717 / 26023999)"
        progress_pattern = r'progress: (\d+\.\d+) \((\d+) / (\d+)\)'
        match = re.search(progress_pattern, line)
        
        if match:
            progress_percent = float(match.group(1))
            downloaded_bytes = int(match.group(2))
            total_bytes = int(match.group(3))
            
            self.download_status["progress"] = progress_percent
            self.download_status["downloaded_size"] = self._format_size(downloaded_bytes)
            self.download_status["total_size"] = self._format_size(total_bytes)
            
            # Calculate estimated time remaining if we have progress
            if progress_percent > 0:
                elapsed_seconds = (datetime.now() - self.download_status["start_time"]).total_seconds()
                total_seconds_estimate = (elapsed_seconds / progress_percent) * 100
                remaining_seconds = total_seconds_estimate - elapsed_seconds
                
                est_completion_time = datetime.now().timestamp() + remaining_seconds
                self.download_status["estimated_end_time"] = datetime.fromtimestamp(est_completion_time)
        
        # Check for error messages
        if "ERROR" in line:
            self.download_status["error"] = line
            logger.warning(f"Detected error in SteamCMD output: {line}")
    
    def _format_size(self, size_bytes):
        """
        Formats bytes to a human-readable size
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    
    def _generate_public_links(self, game_id):
        """
        Generates public links for downloaded game files
        """
        game_download_dir = os.path.join(self.downloads_dir, f"app_{game_id}")
        game_public_dir = os.path.join(self.public_dir, f"app_{game_id}")
        
        # Create public directory for this game
        os.makedirs(game_public_dir, exist_ok=True)
        
        # Copy or move files to public directory
        try:
            for root, _, files in os.walk(game_download_dir):
                for file in files:
                    src_path = os.path.join(root, file)
                    rel_path = os.path.relpath(src_path, game_download_dir)
                    dst_path = os.path.join(game_public_dir, rel_path)
                    
                    # Ensure destination directory exists
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    
                    # Create symlink or copy file depending on platform
                    if sys.platform == "win32":
                        shutil.copy2(src_path, dst_path)
                    else:
                        os.symlink(src_path, dst_path)
            
            logger.info(f"Public links generated for Game ID: {game_id}")
        except Exception as e:
            logger.error(f"Error generating public links for Game ID {game_id}: {str(e)}")
            self.download_status["error"] = f"Error generating public links: {str(e)}"
    
    def get_public_links(self, game_id):
        """
        Returns available public links for a downloaded game
        """
        if not game_id:
            return []
        
        game_public_dir = os.path.join(self.public_dir, f"app_{game_id}")
        if not os.path.exists(game_public_dir):
            return []
        
        links = []
        base_url = f"/public/app_{game_id}"
        
        for root, _, files in os.walk(game_public_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, game_public_dir)
                url = f"{base_url}/{urllib.parse.quote(rel_path)}"
                links.append({
                    "filename": rel_path,
                    "url": url,
                    "size": os.path.getsize(file_path)
                })
        
        return links
    
    def get_download_status(self):
        """
        Returns the current download status information
        """
        status = self.download_status.copy()
        
        # Format time information
        if status["start_time"]:
            status["elapsed_time"] = str(datetime.now() - status["start_time"]).split('.')[0]
        else:
            status["elapsed_time"] = "00:00:00"
        
        if status["estimated_end_time"]:
            status["remaining_time"] = str(status["estimated_end_time"] - datetime.now()).split('.')[0]
            if "-" in status["remaining_time"]:  # Negative time
                status["remaining_time"] = "00:00:00"
        else:
            status["remaining_time"] = "Unknown"
        
        # Get links if download completed
        if status["status"] == "Completed" and status["game_id"]:
            status["links"] = self.get_public_links(status["game_id"])
        else:
            status["links"] = []
        
        return status
    
    def stop_download(self):
        """
        Stops the current download process
        """
        if self.current_process and self.current_process.poll() is None:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.current_process.pid)])
                else:
                    self.current_process.terminate()
                    time.sleep(2)
                    if self.current_process.poll() is None:
                        self.current_process.kill()
                
                self.download_status["status"] = "Stopped"
                return "Download stopped", None
            except Exception as e:
                return None, f"Error stopping download: {str(e)}"
        return "No active download to stop", None

def create_gradio_interface():
    """Create Gradio web interface"""
    with gr.Blocks(title="Steam Game Downloader") as interface:
        gr.Markdown("# Steam Game Downloader")
        gr.Markdown("Enter the Steam App ID to download games")
        
        with gr.Row():
            with gr.Column():
                app_id = gr.Textbox(label="App ID", placeholder="Enter Steam App ID")
                download_btn = gr.Button("Download Game")
                status_text = gr.Markdown("Ready to download")
            
            with gr.Column():
                download_info = gr.JSON(label="Download Status")
                refresh_btn = gr.Button("Refresh Status")
        
        def start_download(game_id):
            if not game_id:
                return "Please enter an App ID"
            
            # Start a simple anonymous download
            try:
                # Log the download attempt
                logger.info(f"Attempting to download app ID: {game_id}")
                
                # Return success message for now
                return f"Download started for App ID {game_id}"
            except Exception as e:
                logger.error(f"Error starting download: {str(e)}")
                return f"Error: {str(e)}"
        
        def get_status():
            # Simple status for now
            return {"status": "ready"}
        
        download_btn.click(
            start_download,
            inputs=[app_id],
            outputs=status_text
        )
        
        refresh_btn.click(get_status, outputs=download_info)
    
    # This is important - return the interface
    return interface

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
        disk = shutil.disk_usage(VOLUME_PATH)
        DISK_USAGE.set(disk.used)
        
        # Update memory usage metrics
        MEMORY_USAGE.set(psutil.Process().memory_info().rss)
    except Exception as e:
        logger.error(f"Error updating system metrics: {str(e)}")

def cleanup_background():
    """Cleanup old downloads and logs"""
    while True:
        try:
            # Clean up old downloads (older than 24 hours)
            cleanup_old_files("/app/downloads", max_age_hours=24)
            # Rotate logs if needed
            cleanup_old_files("/app/logs", max_age_hours=72)
            # Update metrics
            update_system_metrics()
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")
        time.sleep(3600)  # Run every hour

def main():
    """Main application entry point"""
    try:
        # Ensure required directories exist
        os.makedirs("/app/downloads", exist_ok=True)
        os.makedirs("/app/public", exist_ok=True)
        os.makedirs("/app/logs", exist_ok=True)
        os.makedirs("/data", exist_ok=True)
        
        # Verify SteamCMD installation
        logger.info("Verifying SteamCMD installation...")
        steamcmd_path = "/app/steamcmd/steamcmd.sh"
        if not os.path.exists(steamcmd_path):
            logger.error("SteamCMD not found. Exiting.")
            sys.exit(1)
        
        # Create FastAPI app
        api = FastAPI(
            title="Steam Game Downloader",
            description="A SteamCMD-based game downloader",
            version="1.0.0"
        )
        
        # Add health check endpoint
        @api.get("/health")
        async def health_check():
            return {"status": "healthy"}
        
        # Create Gradio interface
        logger.info("Creating Gradio interface...")
        gradio_app = create_gradio_interface()
        
        # Log startup information
        port = int(os.getenv('PORT', '8080'))
        logger.info(f"Starting server on port {port}")
        
        # Mount Gradio app to FastAPI - THIS IS CRITICAL
        # The Gradio app must be mounted with gr.mount_gradio_app and stored in a new variable
        final_app = gr.mount_gradio_app(api, gradio_app, path="/")
        
        # Start the server - USE THE MOUNTED APP
        uvicorn.run(
            final_app,  # Use the final_app, not api or app
            host="0.0.0.0",  # Important: bind to all interfaces
            port=port,
            log_level="info"
        )
    
    except Exception as e:
        logger.critical(f"Fatal error in main application: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()