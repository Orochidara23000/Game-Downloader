#!/usr/bin/env python3
import os
import sys
import time
import logging
import psutil
import requests
import json
from pathlib import Path
import argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('/app/logs', 'monitor.log'))
    ]
)
logger = logging.getLogger(__name__)

class SystemMonitor:
    def __init__(self, check_interval=60, alert_threshold=90, service_url="http://localhost:8080"):
        self.check_interval = check_interval
        self.alert_threshold = alert_threshold
        self.service_url = service_url
        self.history = {
            'cpu': [],
            'memory': [],
            'disk': [],
            'response_time': []
        }
        self.max_history_points = 1440  # Store 24 hours of data at 1-minute intervals
        
    def check_cpu(self):
        """Check CPU usage"""
        cpu_percent = psutil.cpu_percent(interval=1)
        self.history['cpu'].append((datetime.now(), cpu_percent))
        
        if cpu_percent > self.alert_threshold:
            logger.warning(f"HIGH CPU USAGE: {cpu_percent}%")
            
        return cpu_percent
        
    def check_memory(self):
        """Check memory usage"""
        memory = psutil.virtual_memory()
        self.history['memory'].append((datetime.now(), memory.percent))
        
        if memory.percent > self.alert_threshold:
            logger.warning(f"HIGH MEMORY USAGE: {memory.percent}%")
            
        return memory.percent
        
    def check_disk(self):
        """Check disk usage"""
        disk = psutil.disk_usage('/data')
        self.history['disk'].append((datetime.now(), disk.percent))
        
        if disk.percent > self.alert_threshold:
            logger.warning(f"HIGH DISK USAGE: {disk.percent}%")
            
        return disk.percent
        
    def check_service_health(self):
        """Check service health and response time"""
        try:
            start_time = time.time()
            response = requests.get(f"{self.service_url}/health", timeout=5)
            response_time = (time.time() - start_time) * 1000  # ms
            
            self.history['response_time'].append((datetime.now(), response_time))
            
            if response.status_code != 200:
                logger.error(f"SERVICE HEALTH CHECK FAILED: Status {response.status_code}")
                return False, response_time
                
            if response_time > 1000:  # 1 second
                logger.warning(f"SLOW RESPONSE TIME: {response_time:.2f}ms")
                
            return True, response_time
            
        except Exception as e:
            logger.error(f"SERVICE HEALTH CHECK ERROR: {str(e)}")
            return False, 0
            
    def check_running_processes(self):
        """Check running processes"""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_percent', 'cpu_percent']):
            try:
                proc_info = proc.info
                processes.append(proc_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        # Sort by CPU and memory usage (descending)
        top_cpu = sorted(processes, key=lambda p: p['cpu_percent'], reverse=True)[:5]
        top_memory = sorted(processes, key=lambda p: p['memory_percent'], reverse=True)[:5]
        
        return {
            'top_cpu': top_cpu,
            'top_memory': top_memory
        }
            
    def trim_history(self):
        """Trim history to maximum size"""
        for metric in self.history:
            if len(self.history[metric]) > self.max_history_points:
                self.history[metric] = self.history[metric][-self.max_history_points:]
                
    def export_metrics(self, file_path):
        """Export metrics to JSON file"""
        export_data = {}
        
        # Convert datetime objects to strings
        for metric, values in self.history.items():
            export_data[metric] = [(dt.isoformat(), value) for dt, value in values]
            
        # Add timestamp
        export_data['timestamp'] = datetime.now().isoformat()
        export_data['service_url'] = self.service_url
        
        # Write to file
        with open(file_path, 'w') as f:
            json.dump(export_data, f, indent=2)
            
        logger.info(f"Metrics exported to {file_path}")
        
    def run(self, duration_minutes=0, export_path=None):
        """Run monitoring for specified duration (0 = indefinitely)"""
        logger.info(f"Starting system monitoring (interval: {self.check_interval}s)")
        logger.info(f"Alert threshold: {self.alert_threshold}%")
        logger.info(f"Service URL: {self.service_url}")
        
        end_time = None
        if duration_minutes > 0:
            end_time = datetime.now() + timedelta(minutes=duration_minutes)
            logger.info(f"Monitoring will run until {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            while True:
                with ThreadPoolExecutor(max_workers=4) as executor:
                    cpu_future = executor.submit(self.check_cpu)
                    memory_future = executor.submit(self.check_memory)
                    disk_future = executor.submit(self.check_disk)
                    health_future = executor.submit(self.check_service_health)
                    
                    # Wait for all checks to complete
                    cpu_percent = cpu_future.result()
                    memory_percent = memory_future.result()
                    disk_percent = disk_future.result()
                    health_status, response_time = health_future.result()
                    
                # Log summary
                logger.info(f"System Status - CPU: {cpu_percent:.1f}%, "
                          f"Memory: {memory_percent:.1f}%, "
                          f"Disk: {disk_percent:.1f}%, "
                          f"Service: {'OK' if health_status else 'FAIL'} ({response_time:.1f}ms)")
                
                # Check running processes periodically (every 10 intervals)
                if int(time.time()) % (self.check_interval * 10) < self.check_interval:
                    proc_info = self.check_running_processes()
                    logger.info("Top CPU consuming processes:")
                    for proc in proc_info['top_cpu']:
                        logger.info(f"  PID {proc['pid']}: {proc['name']} ({proc['cpu_percent']:.1f}%)")
                    
                    logger.info("Top memory consuming processes:")
                    for proc in proc_info['top_memory']:
                        logger.info(f"  PID {proc['pid']}: {proc['name']} ({proc['memory_percent']:.1f}%)")
                
                # Trim history to prevent memory growth
                self.trim_history()
                
                # Export metrics if path is provided
                if export_path:
                    self.export_metrics(export_path)
                
                # Check if we've reached the end time
                if end_time and datetime.now() >= end_time:
                    logger.info("Monitoring duration reached, exiting...")
                    break
                    
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Monitoring error: {str(e)}")
            return 1
            
        return 0

def parse_arguments():
    parser = argparse.ArgumentParser(description="Monitor system and service health")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    parser.add_argument("--threshold", type=int, default=90, help="Alert threshold percentage")
    parser.add_argument("--url", default="http://localhost:8080", help="Service URL to monitor")
    parser.add_argument("--duration", type=int, default=0, help="Monitoring duration in minutes (0 = indefinitely)")
    parser.add_argument("--export", help="Path to export metrics JSON file")
    return parser.parse_args()

def main():
    args = parse_arguments()
    
    # Create logs directory if it doesn't exist
    os.makedirs('/app/logs', exist_ok=True)
    
    monitor = SystemMonitor(
        check_interval=args.interval,
        alert_threshold=args.threshold,
        service_url=args.url
    )
    
    return monitor.run(
        duration_minutes=args.duration,
        export_path=args.export
    )

if __name__ == "__main__":
    sys.exit(main())