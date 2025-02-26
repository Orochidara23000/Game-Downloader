import os
import requests
import sys
import time

def check_health(max_retries=3, retry_delay=2):
    """Check if the application is healthy with retries"""
    port = os.getenv('PORT', '8080')
    url = f"http://localhost:{port}/health"
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                print("Health check passed")
                return True
            else:
                print(f"Health check failed with status code: {response.status_code}")
                print(f"Response: {response.text}")
        except Exception as e:
            print(f"Health check attempt {attempt + 1} failed with error: {str(e)}")
        
        if attempt < max_retries - 1:
            print(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    
    return False

if __name__ == "__main__":
    sys.exit(0 if check_health() else 1) 
