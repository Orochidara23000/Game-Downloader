import os
import requests
import sys

def check_health():
    """Check if the application is healthy"""
    port = os.getenv('PORT', '8080')
    try:
        response = requests.get(f"http://localhost:{port}/health")
        if response.status_code == 200:
            print("Health check passed")
            return True
        else:
            print(f"Health check failed with status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"Health check failed with error: {str(e)}")
        return False

if __name__ == "__main__":
    sys.exit(0 if check_health() else 1) 