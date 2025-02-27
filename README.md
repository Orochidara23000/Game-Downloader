# Steam Game Downloader

A web-based interface for downloading Steam games using SteamCMD with a Gradio UI.

## Features

- Download Steam games directly from a web interface
- Track download progress and manage downloads
- Persistent storage of downloaded games
- Health monitoring and system metrics
- Public links for downloaded content

## Getting Started

### Prerequisites

- Python 3.9 or higher
- Docker (for containerized deployment)
- Railway account (for deployment on Railway)

### Local Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/steam-game-downloader.git
   cd steam-game-downloader
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   ./start.sh
   ```

4. Access the interface at http://localhost:8080

### Docker Installation

1. Build the Docker image:
   ```bash
   docker build -t steam-downloader -f Dockerfile.dockerfile .
   ```

2. Run the container:
   ```bash
   docker run -p 8080:8080 -v $(pwd)/data:/data steam-downloader
   ```

3. Access the interface at http://localhost:8080

### Railway Deployment

1. Fork this repository to your GitHub account
2. Connect your Railway account to GitHub
3. Create a new Railway project from your forked repository
4. Add a Railway volume mounted at `/data`
5. Deploy the application

## Usage

1. Enter the Steam App ID of the game you want to download
2. For non-free games, enter your Steam credentials
3. Click "Download Game" to start the download
4. Track download progress in the status panel
5. Access downloaded games through the generated links

## Environment Variables

- `PORT`: The port for the web interface (default: 8080)
- `METRICS_PORT`: The port for Prometheus metrics (default: 9090)
- `RAILWAY_VOLUME_MOUNT_PATH`: Path for persistent data storage (default: /data)

## Directory Structure

- `/app`: Application code
  - `/app/steamcmd`: SteamCMD installation
  - `/app/logs`: Application logs
- `/data`: Persistent storage (mounted volume)
  - `/data/downloads`: Downloaded game files
  - `/data/public`: Public links to downloads

## Monitoring

The application includes several monitoring components:

- `health_check.py`: Health check service accessible at `/health` and `/status`
- `monitor.py`: System monitoring script
- `cleanup.py`: Automated cleanup of old downloads and logs

## Troubleshooting

If you encounter issues:

1. Check the logs at `/app/logs/`
2. Run the health check at `/status`
3. Ensure SteamCMD is installed and working
4. Verify that your Steam credentials are correct for non-free games

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Railway Deployment

### Quick Deploy
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/steam-game-downloader)

### Manual Deployment Steps
1. Fork this repository
2. Create a new Railway project
3. Add the following environment variables in Railway:
   - `PORT`: Will be set automatically by Railway
   - `STEAM_USERNAME`: (Optional) Your Steam username
   - `STEAM_PASSWORD`: (Optional) Your Steam password
   - `MAX_DOWNLOADS`: Maximum concurrent downloads (default: 5)
   - `LOG_LEVEL`: Logging level (default: INFO)

4. Deploy using Railway CLI:
```bash
railway up
```

### Storage Configuration
Railway provides ephemeral storage. For persistent storage:
1. Add a Railway volume
2. Mount it to `/app/downloads` and `/app/public`

## Local Development

### Prerequisites
- Python 3.9+
- Docker (optional)

### Local Setup
1. Clone the repository:
```bash
git clone https://github.com/yourusername/steam-game-downloader.git
cd steam-game-downloader
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create .env file:
```bash
cp .env.example .env
```

5. Run the application:
```bash
python main.py
```

### Docker Setup
```bash
docker-compose up --build
```

## API Documentation
The application exposes the following endpoints:
- `/`: Main web interface
- `/health`: Health check endpoint
- `/metrics`: Prometheus metrics (if enabled)

## Prerequisites
- **Python 3.8+**
- **SteamCMD:**  
  - **Windows:** [Download SteamCMD](https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip)  
  - **Linux/macOS:**  
    - For Debian/Ubuntu: `sudo apt-get install steamcmd`  
    - For Arch Linux: `sudo pacman -S steamcmd`  
    - For macOS: `brew install steamcmd`

## Setup Instructions

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/yourusername/steam-game-downloader.git
   cd steam-game-downloader
