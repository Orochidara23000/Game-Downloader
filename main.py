#!/usr/bin/env python3
"""
Steam Game Downloader
A web interface for downloading Steam games using SteamCMD
"""
import os
import sys
import subprocess
import threading
import logging
import time
import json
from pathlib import Path
import gradio as gr
import psutil
from prometheus_client import Counter, Gauge, start_http_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/app/logs/steam_downloader.log")
    ]
)
logger = logging.getLogger("SteamDownloader")

# Constants and configuration
PORT = int(os.environ.get("PORT", 8080))
METRICS_PORT = int(os.environ.get("METRICS_PORT", 9090))
DATA_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/data"))
DOWNLOADS_DIR = DATA_DIR / "downloads"
PUBLIC_DIR = DATA_DIR / "public"
STEAMCMD_PATH = Path("/app/steamcmd/steamcmd.sh")

# Create necessary directories
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
Path("/app/logs").mkdir(parents=True, exist_ok=True)

# Metrics
DOWNLOAD_COUNTER = Counter('steam_downloads_total', 'Total number of downloads')
DOWNLOAD_FAILURES = Counter('steam_downloads_failed', 'Failed downloads')
ACTIVE_DOWNLOADS = Gauge('steam_downloads_active', 'Currently active downloads')
DISK_USAGE = Gauge('steam_disk_usage_bytes', 'Disk usage in bytes')

# Track active downloads
active_downloads = {}
download_lock = threading.Lock()

def update_metrics():
    """Update system metrics"""
    try:
        # Update disk usage
        disk_usage = psutil.disk_usage(str(DATA_DIR))
        DISK_USAGE.set(disk_usage.used)
        
        # Update active downloads count
        with download_lock:
            ACTIVE_DOWNLOADS.set(len(active_downloads))
            
    except Exception as e:
        logger.error(f"Error updating metrics: {e}")

def verify_steamcmd():
    """Verify SteamCMD installation"""
    logger.info("Verifying SteamCMD installation...")
    
    if not STEAMCMD_PATH.exists():
        logger.error("SteamCMD not found!")
        return False
        
    try:
        # Test SteamCMD
        result = subprocess.run(
            [str(STEAMCMD_PATH), "+quit"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            logger.error(f"SteamCMD verification failed: {result.stderr}")
            return False
            
        logger.info("SteamCMD verification successful")
        return True
        
    except Exception as e:
        logger.error(f"SteamCMD verification error: {e}")
        return False

def download_game(app_id, username=None, password=None, steam_guard=None):
    """Download a Steam game using SteamCMD"""
    if not app_id or not app_id.strip():
        return "Error: Please enter a valid App ID"
    
    app_id = app_id.strip()
    download_id = f"{app_id}_{int(time.time())}"
    download_path = DOWNLOADS_DIR / app_id
    
    # Create download directory
    download_path.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Starting download for App ID: {app_id}")
    
    # Build SteamCMD command
    cmd = [
        str(STEAMCMD_PATH),
        "+@NoPromptForPassword 1"
    ]
    
    # Add login details if provided
    if username and password:
        cmd.extend([
            f"+login {username} {password}"
        ])
        if steam_guard:
            cmd[-1] += f" {steam_guard}"
    else:
        cmd.append("+login anonymous")
    
    # Add download commands
    cmd.extend([
        f"+force_install_dir {download_path}",
        f"+app_update {app_id} validate",
        "+quit"
    ])
    
    # Start download in a separate thread
    def download_thread():
        try:
            with download_lock:
                active_downloads[download_id] = {
                    "app_id": app_id,
                    "status": "starting",
                    "start_time": time.time(),
                    "download_path": str(download_path)
                }
                
            # Run SteamCMD command
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            with download_lock:
                active_downloads[download_id]["status"] = "downloading"
                active_downloads[download_id]["process"] = process
            
            # Wait for completion
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                # Success
                with download_lock:
                    active_downloads[download_id]["status"] = "completed"
                    active_downloads[download_id]["end_time"] = time.time()
                
                # Create a public link
                try:
                    # Create symlink in public directory
                    public_link = PUBLIC_DIR / app_id
                    if public_link.exists():
                        if public_link.is_symlink():
                            public_link.unlink()
                    
                    # Create relative symlink
                    public_link.symlink_to(download_path)
                    
                    with download_lock:
                        active_downloads[download_id]["public_link"] = str(public_link)
                        
                except Exception as e:
                    logger.error(f"Error creating public link: {e}")
                
                DOWNLOAD_COUNTER.inc()
                logger.info(f"Download completed for App ID: {app_id}")
            else:
                # Failure
                with download_lock:
                    active_downloads[download_id]["status"] = "failed"
                    active_downloads[download_id]["error"] = stderr
                
                DOWNLOAD_FAILURES.inc()
                logger.error(f"Download failed for App ID: {app_id}: {stderr}")
            
            # Update metrics
            update_metrics()
            
        except Exception as e:
            with download_lock:
                active_downloads[download_id]["status"] = "error"
                active_downloads[download_id]["error"] = str(e)
            
            DOWNLOAD_FAILURES.inc()
            logger.error(f"Error during download for App ID {app_id}: {e}")
            update_metrics()
    
    # Start the download thread
    download_thread = threading.Thread(target=download_thread)
    download_thread.daemon = True
    download_thread.start()
    
    return f"Download started for App ID: {app_id} (ID: {download_id})"

def get_downloads_status():
    """Get the status of all downloads"""
    with download_lock:
        # Create a copy without process objects (not serializable)
        downloads_copy = {}
        for download_id, download in active_downloads.items():
            download_copy = download.copy()
            if "process" in download_copy:
                download_copy["process"] = "Running" if download_copy["process"].poll() is None else "Completed"
            downloads_copy[download_id] = download_copy
        
        return downloads_copy

def create_gradio_interface():
    """Create Gradio web interface"""
    with gr.Blocks(title="Steam Game Downloader") as interface:
        gr.Markdown("# Steam Game Downloader")
        gr.Markdown("Download games from Steam using SteamCMD")
        
        with gr.Row():
            with gr.Column():
                app_id = gr.Textbox(label="Steam App ID", placeholder="Enter Steam App ID (e.g., 730 for CS:GO)")
                
                with gr.Accordion("Login Details (Optional)", open=False):
                    username = gr.Textbox(label="Steam Username", placeholder="Optional: For non-free games")
                    password = gr.Textbox(label="Steam Password", placeholder="Optional: For non-free games", type="password")
                    steam_guard = gr.Textbox(label="Steam Guard Code", placeholder="Optional: If 2FA is enabled")
                
                download_btn = gr.Button("Download Game")
                status_text = gr.Markdown("Ready to download")
            
            with gr.Column():
                download_info = gr.JSON(label="Download Status")
                refresh_btn = gr.Button("Refresh Status")
        
        # Download function
        download_btn.click(
            fn=download_game,
            inputs=[app_id, username, password, steam_guard],
            outputs=status_text
        )
        
        # Get status function
        refresh_btn.click(
            fn=get_downloads_status,
            inputs=[],
            outputs=download_info
        )
        
        # Auto-refresh every 5 seconds
        gr.on(
            triggers=[interface.load, gr.every(5)],
            fn=get_downloads_status,
            inputs=[],
            outputs=download_info
        )
    
    return interface

def start_metrics_server():
    """Start Prometheus metrics server"""
    try:
        start_http_server(METRICS_PORT)
        logger.info(f"Metrics server started on port {METRICS_PORT}")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")

def main():
    """Main application entry point"""
    try:
        # Print application info
        logger.info(f"Starting Steam Game Downloader on port {PORT}")
        logger.info(f"Data directory: {DATA_DIR}")
        logger.info(f"Downloads directory: {DOWNLOADS_DIR}")
        logger.info(f"Public directory: {PUBLIC_DIR}")
        
        # Verify SteamCMD installation
        logger.info("Verifying SteamCMD installation...")
        if not verify_steamcmd():
            logger.error("SteamCMD verification failed. Service may not work correctly.")
        
        # Start metrics server
        start_metrics_server()
        
        # Start initial metrics update
        update_metrics()
        
        # Create and start Gradio interface
        logger.info("Creating Gradio interface...")
        demo = create_gradio_interface()
        
        # Log server details
        logger.info(f"Starting server on port {PORT}")
        logger.info(f"Public URL: {os.environ.get('PUBLIC_URL', '')}")
        logger.info(f"Railway URL: {os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')}")
        
        # Launch the interface
        demo.launch(
            server_name="0.0.0.0",
            server_port=PORT,
            share=False,
            debug=False
        )
        
    except Exception as e:
        logger.critical(f"Fatal error in main application: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()