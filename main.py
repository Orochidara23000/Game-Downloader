#!/usr/bin/env python3
import os
import sys
import subprocess
import logging
import time
import json
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger()

# Get configuration
PORT = int(os.environ.get('PORT', 8080))

# Install dependencies
def install_dependencies():
    """Install required Python packages"""
    logger.info("Checking and installing dependencies...")
    try:
        # Define required packages
        required_packages = ['flask']
        
        # Install packages using pip
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "--upgrade", "pip"
        ])
        
        for package in required_packages:
            logger.info(f"Installing {package}...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", package
            ])
        
        logger.info("All dependencies installed successfully")
        return True
    except Exception as e:
        logger.error(f"Error installing dependencies: {e}")
        return False

# Simple HTTP request handler
class SimpleHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode())
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())
        elif self.path == '/debug':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            # Collect debug information
            debug_info = {
                "environment": {k: v for k, v in os.environ.items()},
                "working_directory": os.getcwd(),
                "files": [str(f) for f in Path('.').glob('*')]
            }
            
            self.wfile.write(json.dumps(debug_info, indent=2).encode())
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info("%s - %s" % (self.address_string(), format % args))

# Simple HTML content
HTML_CONTENT = """
<!DOCTYPE html>
<html>
<head>
    <title>Steam Game Downloader</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        .container { background: #f5f5f5; padding: 20px; border-radius: 5px; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>Steam Game Downloader</h1>
    <div class="container">
        <p>This is a simple Steam Game Downloader service.</p>
        <p>Check the <a href="/debug">debug information</a> for environment details.</p>
        <p>Use the <a href="/health">health check</a> to verify the service is running.</p>
    </div>
</body>
</html>
"""

def run_simple_server():
    """Run a simple HTTP server without dependencies"""
    logger.info(f"Starting simple HTTP server on port {PORT}")
    server = HTTPServer(('0.0.0.0', PORT), SimpleHTTPHandler)
    
    try:
        logger.info(f"Server started at http://0.0.0.0:{PORT}")
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        server.server_close()

def run_flask_server():
    """Run Flask server if dependencies are installed"""
    try:
        # Try to import Flask
        from flask import Flask, render_template_string, jsonify
        
        app = Flask(__name__)
        
        @app.route('/')
        def index():
            return render_template_string(HTML_CONTENT)
        
        @app.route('/health')
        def health():
            return jsonify({"status": "healthy"})
        
        @app.route('/debug')
        def debug():
            debug_info = {
                "environment": {k: v for k, v in os.environ.items()},
                "working_directory": os.getcwd(),
                "files": [str(f) for f in Path('.').glob('*')]
            }
            return jsonify(debug_info)
        
        logger.info(f"Starting Flask server on port {PORT}")
        app.run(host='0.0.0.0', port=PORT)
        return True
    except ImportError:
        logger.warning("Flask not available, falling back to simple server")
        return False
    except Exception as e:
        logger.error(f"Error running Flask server: {e}")
        return False

def main():
    """Main application entry point"""
    logger.info("Starting Steam Downloader application")
    
    # Log environment info
    logger.info("=== ENVIRONMENT ===")
    for key, value in os.environ.items():
        if key.startswith(('PORT', 'PUBLIC', 'RAILWAY', 'HOST')):
            logger.info(f"{key}: {value}")
    logger.info("==================")
    
    # Show file system info
    logger.info("=== FILES ===")
    for item in Path('.').glob('*'):
        logger.info(f"{item} {'(dir)' if item.is_dir() else '(file)'}")
    logger.info("============")
    
    # Try to install dependencies
    deps_installed = install_dependencies()
    
    # Try to run Flask server
    if deps_installed and run_flask_server():
        logger.info("Successfully started Flask server")
    else:
        # Fall back to simple server
        logger.info("Falling back to simple HTTP server")
        run_simple_server()

if __name__ == "__main__":
    main()
