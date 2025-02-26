import os
import re
import sys
import subprocess
import time
import threading
import logging
import gradio as gr
import shutil
import urllib.parse
import requests
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("steam_downloader.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SteamDownloader")

class SteamDownloader:
    def __init__(self):
        self.steamcmd_path = os.path.join(os.getcwd(), "steamcmd")
        self.downloads_dir = os.path.join(os.getcwd(), "downloads")
        self.public_dir = os.path.join(os.getcwd(), "public")
        self.steamcmd_exe = os.path.join(self.steamcmd_path, "steamcmd.exe" if sys.platform == "win32" else "steamcmd.sh")
        self.current_process = None
        self.download_status = {
            "game_id": None,
            "progress": 0,
            "start_time": None,
            "estimated_end_time": None,
            "downloaded_size": "0 MB",
            "total_size": "Unknown",
            "status": "Idle",
            "error": None
        }
        
        # Create necessary directories
        for directory in [self.steamcmd_path, self.downloads_dir, self.public_dir]:
            os.makedirs(directory, exist_ok=True)
    
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
            if result.returncode == 0:
                logger.info("SteamCMD is properly installed")
                return True
            else:
                logger.error(f"SteamCMD test failed with return code: {result.returncode}")
                return False
        except (subprocess.SubprocessError, OSError) as e:
            logger.error(f"Error running SteamCMD: {str(e)}")
            return False
    
    def install_steamcmd(self):
        """
        Provides instructions for installing SteamCMD
        """
        if sys.platform == "win32":
            return """
            Please install SteamCMD manually by following these steps:
            1. Download SteamCMD from https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip
            2. Extract the zip file to the 'steamcmd' folder in this application's directory
            3. Run steamcmd.exe once to complete installation
            4. Restart this application after installation
            """
        else:  # Linux/macOS
            return """
            Please install SteamCMD by following these steps:
            
            For Debian/Ubuntu:
            $ sudo apt-get install steamcmd
            
            For Arch Linux:
            $ sudo pacman -S steamcmd
            
            For macOS:
            $ brew install steamcmd
            
            Alternatively, download and install manually:
            $ mkdir -p steamcmd
            $ cd steamcmd
            $ curl -O https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz
            $ tar -xvzf steamcmd_linux.tar.gz
            $ ./steamcmd.sh +quit
            
            Restart this application after installation
            """
    
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

# Main application
def create_gradio_interface():
    downloader = SteamDownloader()
    
    # Check SteamCMD on startup
    steamcmd_installed = downloader.check_steamcmd_installation()
    
    if not steamcmd_installed:
        # If SteamCMD not found, create an installation instructions interface
        install_message = downloader.install_steamcmd()
        
        with gr.Blocks(title="SteamCMD Installation Required") as app:
            gr.Markdown("# ⚠️ SteamCMD Installation Required")
            gr.Markdown(install_message)
            gr.Markdown("Click the button below after installing SteamCMD to refresh")
            refresh_btn = gr.Button("Refresh")
            
            def refresh():
                if downloader.check_steamcmd_installation():
                    return "SteamCMD installed successfully! Please restart the application."
                else:
                    return "SteamCMD still not detected. Please complete the installation."
            
            refresh_btn.click(fn=refresh, outputs=gr.Textbox(label="Status"))
        
        return app
    
    # Main application interface
    with gr.Blocks(title="Steam Game Downloader") as app:
        with gr.Row():
            gr.Markdown("# 🎮 Steam Game Downloader")
        
        with gr.Row():
            with gr.Column(scale=2):
                with gr.Box():
                    gr.Markdown("### Login Details")
                    
                    # Login fields
                    username = gr.Textbox(label="Steam Username", placeholder="Your Steam username")
                    password = gr.Textbox(label="Password", placeholder="Your Steam password", 
                                         type="password", visible=True)
                    anonymous = gr.Checkbox(label="Login Anonymously (for free games only)")
                    
                    # Game input fields
                    game_input = gr.Textbox(
                        label="Game ID or Steam URL", 
                        placeholder="Enter game ID (e.g., 440) or URL (e.g., https://store.steampowered.com/app/440)"
                    )
                    
                    with gr.Row():
                        download_btn = gr.Button("Start Download", variant="primary")
                        stop_btn = gr.Button("Stop Download", variant="stop")
                    
                    status_text = gr.Textbox(label="Status", value="Ready")
                    
                    def toggle_password_visibility(anonymous_checked):
                        return [
                            gr.update(visible=not anonymous_checked),  # password
                            gr.update(visible=not anonymous_checked)   # username
                        ]
                    
                    anonymous.change(
                        fn=toggle_password_visibility, 
                        inputs=anonymous,
                        outputs=[password, username]
                    )
            
            with gr.Column(scale=3):
                with gr.Box():
                    gr.Markdown("### Download Progress")
                    progress_bar = gr.Progress(label="Download Progress")
                    
                    with gr.Row():
                        elapsed_time = gr.Textbox(label="Elapsed Time", value="00:00:00")
                        remaining_time = gr.Textbox(label="Estimated Time Remaining", value="Unknown")
                    
                    with gr.Row():
                        downloaded_size = gr.Textbox(label="Downloaded", value="0 MB")
                        total_size = gr.Textbox(label="Total Size", value="Unknown")
                
                with gr.Box():
                    gr.Markdown("### Public Links (Available after download completes)")
                    links_output = gr.JSON(label="Available Files")
        
        # Event handlers
        def start_download_handler(username, password, game_input, anonymous):
            if not game_input:
                return "Please enter a game ID or Steam URL", None
            
            if not anonymous and (not username or not password):
                return "Please enter your Steam credentials or select anonymous login", None
            
            message, error = downloader.start_download(username, password, game_input, anonymous)
            return message, error
        
        download_btn.click(
            fn=start_download_handler,
            inputs=[username, password, game_input, anonymous],
            outputs=[status_text, gr.Textbox(visible=False)]
        )
        
        stop_btn.click(
            fn=downloader.stop_download,
            outputs=[status_text, gr.Textbox(visible=False)]
        )
        
        # Status updater
        def update_status():
            status = downloader.get_download_status()
            
            # Update progress bar
            progress_value = status["progress"] / 100
            
            return {
                progress_bar: progress_value,
                elapsed_time: status["elapsed_time"],
                remaining_time: status["remaining_time"],
                downloaded_size: status["downloaded_size"],
                total_size: status["total_size"],
                status_text: f"Status: {status['status']}" + (f" - {status['error']}" if status["error"] else ""),
                links_output: status["links"]
            }
        
        # Update status every second
        app.load(lambda: None, inputs=None, outputs=None, every=1, show_progress=False).then(
            update_status,
            inputs=None,
            outputs=[progress_bar, elapsed_time, remaining_time, downloaded_size, total_size, status_text, links_output]
        )
    
    return app

# Launch the application
if __name__ == "__main__":
    app = create_gradio_interface()
    app.launch(server_name="0.0.0.0", share=True)
