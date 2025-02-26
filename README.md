# Steam Game Downloader

A SteamCMD-based game downloader with a Gradio interface, built to run in a Railway environment.

## Features
- **SteamCMD Integration:** Downloads games using SteamCMD.
- **Gradio Interface:** User-friendly UI for login, download initiation, and progress monitoring.
- **Real-Time Progress:** Displays elapsed time, estimated remaining time, and file size details.
- **Public File Links:** Generates public links to downloaded game files.

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
