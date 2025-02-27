import os
import sys
import time
import psutil
import requests
import logging
from pathlib import Path
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class HealthChecker:
    def __init__(self):
        self.port = os.getenv('PORT', '8080')
        self.data_dir = Path('/data')
        self.app_dir = Path('/app')
        self.min_disk_space = 1024 * 1024 * 1024  # 1GB
        self.max_memory_percent = 90
        self.max_cpu_percent = 90

    def check_steamcmd(self):
        """Comprehensive SteamCMD check"""
        try:
            # Check executable
            steamcmd_path = self.app_dir / 'steamcmd' / 'steamcmd.sh'
            if not steamcmd_path.exists():
                raise Exception("SteamCMD executable not found")
            
            # Check permissions
            if not os.access(steamcmd_path, os.X_OK):
                raise Exception("SteamCMD not executable")
            
            # Check Steam libraries
            steam_lib_path = self.app_dir / 'steamcmd' / 'linux32'
            if not steam_lib_path.exists():
                raise Exception("Steam libraries not found")
            
            # Test SteamCMD
            result = subprocess.run(
                [str(steamcmd_path), '+quit'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                raise Exception(f"SteamCMD test failed: {result.stderr}")
            
            return True
        
        except Exception as e:
            logger.error(f"SteamCMD check failed: {str(e)}")
            return False

    def check_directories(self):
        """Check if required directories exist and are writable"""
        required_dirs = [
            self.data_dir / 'downloads',
            self.data_dir / 'public',
            self.app_dir / 'logs'
        ]
        
        for directory in required_dirs:
            if not directory.exists():
                raise Exception(f"Directory not found: {directory}")
            if not os.access(directory, os.W_OK):
                raise Exception(f"Directory not writable: {directory}")
        return True

    def check_system_resources(self):
        """Check system resource usage"""
        # Check disk space
        disk_usage = psutil.disk_usage(str(self.data_dir))
        if disk_usage.free < self.min_disk_space:
            raise Exception(f"Low disk space: {disk_usage.free / 1024 / 1024:.2f}MB free")

        # Check memory usage
        memory = psutil.virtual_memory()
        if memory.percent > self.max_memory_percent:
            raise Exception(f"High memory usage: {memory.percent}%")

        # Check CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > self.max_cpu_percent:
            raise Exception(f"High CPU usage: {cpu_percent}%")

        return True

    def check_api_health(self, max_retries=3, retry_delay=2):
        """Check if the API is responding"""
        url = f"http://localhost:{self.port}/health"
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    return True
                else:
                    logger.warning(f"Health check failed with status code: {response.status_code}")
                    logger.warning(f"Response: {response.text}")
            except Exception as e:
                logger.error(f"Health check attempt {attempt + 1} failed: {str(e)}")
            
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
        
        raise Exception("API health check failed after all retries")

    def run_health_check(self):
        """Run all health checks"""
        try:
            checks = {
                "SteamCMD": self.check_steamcmd,
                "Directories": self.check_directories,
                "System Resources": self.check_system_resources,
                "API Health": self.check_api_health
            }

            results = {}
            for name, check in checks.items():
                try:
                    results[name] = check()
                    logger.info(f"{name} check passed")
                except Exception as e:
                    logger.error(f"{name} check failed: {str(e)}")
                    results[name] = False

            return all(results.values())

        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return False

def main():
    checker = HealthChecker()
    success = checker.run_health_check()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())