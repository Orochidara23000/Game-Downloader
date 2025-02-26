# Steam Game Downloader

A SteamCMD-based game downloader with a Gradio interface, built to run in a Railway environment.

## Features
- **SteamCMD Integration:** Downloads games using SteamCMD.
- **Gradio Interface:** User-friendly UI for login, download initiation, and progress monitoring.
- **Real-Time Progress:** Displays elapsed time, estimated remaining time, and file size details.
- **Public File Links:** Generates public links to downloaded game files.

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
