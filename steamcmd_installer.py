import os
import sys
import subprocess
import logging
import requests
import tarfile
import shutil
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SteamCMDInstaller:
    def __init__(self):
        self.steamcmd_path = Path('/app/steamcmd')
        self.steamcmd_exe = self.steamcmd_path / 'steamcmd.sh'
        self.steamcmd_url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
        
    def check_dependencies(self):
        """Check and install required system dependencies"""
        try:
            logger.info("Checking system dependencies...")
            dependencies = [
                'lib32gcc-s1',
                'lib32stdc++6',
                'libc6-i386',
                'libstdc++6:i386'
            ]
            
            # Check if we're running as root
            if os.geteuid() != 0:
                logger.error("This script must be run as root to install dependencies")
                return False
                
            # Update package list
            subprocess.run(['apt-get', 'update'], check=True)
            
            # Add 32-bit architecture
            subprocess.run(['dpkg', '--add-architecture', 'i386'], check=True)
            subprocess.run(['apt-get', 'update'], check=True)
            
            # Install dependencies
            subprocess.run(['apt-get', 'install', '-y'] + dependencies, check=True)
            logger.info("Dependencies installed successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install dependencies: {str(e)}")
            return False

    def download_steamcmd(self):
        """Download SteamCMD from official source"""
        try:
            logger.info("Downloading SteamCMD...")
            response = requests.get(self.steamcmd_url, stream=True)
            response.raise_for_status()
            
            # Create steamcmd directory if it doesn't exist
            self.steamcmd_path.mkdir(parents=True, exist_ok=True)
            
            # Download and extract
            tar_path = self.steamcmd_path / 'steamcmd_linux.tar.gz'
            with open(tar_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            # Extract the archive
            with tarfile.open(tar_path) as tar:
                tar.extractall(path=self.steamcmd_path)
                
            # Cleanup
            tar_path.unlink()
            logger.info("SteamCMD downloaded and extracted successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download SteamCMD: {str(e)}")
            return False

    def verify_installation(self):
        """Verify SteamCMD installation"""
        try:
            logger.info("Verifying SteamCMD installation...")
            
            # Check if steamcmd exists
            if not self.steamcmd_exe.exists():
                logger.error("SteamCMD executable not found")
                return False
                
            # Make executable
            self.steamcmd_exe.chmod(0o755)
            
            # Test SteamCMD
            result = subprocess.run(
                [str(self.steamcmd_exe), '+quit'],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"SteamCMD verification failed: {result.stderr}")
                return False
                
            logger.info("SteamCMD verified successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to verify SteamCMD: {str(e)}")
            return False

    def setup_steamcmd(self):
        """Complete SteamCMD setup process"""
        try:
            # Check if already installed
            if self.steamcmd_exe.exists():
                logger.info("SteamCMD already installed, verifying...")
                if self.verify_installation():
                    return True
                logger.info("Existing installation is invalid, reinstalling...")
                shutil.rmtree(self.steamcmd_path)
            
            # Install dependencies
            if not self.check_dependencies():
                return False
            
            # Download and install SteamCMD
            if not self.download_steamcmd():
                return False
            
            # Verify installation
            if not self.verify_installation():
                return False
            
            # Initial update
            logger.info("Running initial SteamCMD update...")
            subprocess.run([str(self.steamcmd_exe), '+login', 'anonymous', '+quit'])
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup SteamCMD: {str(e)}")
            return False

def main():
    installer = SteamCMDInstaller()
    if installer.setup_steamcmd():
        logger.info("SteamCMD installation completed successfully")
        return 0
    else:
        logger.error("SteamCMD installation failed")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 