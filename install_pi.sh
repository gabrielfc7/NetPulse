#!/usr/bin/env bash
# NetPulse Pro - 1-Click Installer for Raspberry Pi 4 (Docker Sentry)

set -e

echo "===================================================================="
echo "    _   _      _   ____        _              ____             "
echo "   | \ | | ___| |_|  _ \ _   _| |___  ___    |  _ \ _ __ ___   "
echo "   |  \| |/ _ \ __| |_) | | | | / __|/ _ \   | |_) | '__/ _ \  "
echo "   | |\  |  __/ |_|  __/| |_| | \__ \  __/   |  __/| | | (_) | "
echo "   |_| \_|\___|\__|_|    \__,_|_|___/\___|___|_|   |_|  \___/  "
echo "                                        |_____|                 "
echo "   24/7 Autonomous Network Monitor & Sentry Setup for Raspberry Pi"
echo "===================================================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "[!] Docker not detected. Installing Docker automatically..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm -f get-docker.sh
    echo "[+] Docker installed successfully."
fi

# Check for Docker Compose
if ! docker compose version &> /dev/null; then
    echo "[!] Docker Compose plugin not found. Installing..."
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin
fi

# Ensure data directory exists
mkdir -p data

echo "[+] Building and starting NetPulse Pro Docker container..."
docker compose down 2>/dev/null || true
docker compose up -d --build

# Get primary IP address of the Raspberry Pi
PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$PI_IP" ]; then
    PI_IP="<raspberry-pi-ip>"
fi

echo ""
echo "===================================================================="
echo "  [SUCCESS] NetPulse Pro Sentry is running 24/7 on your Raspberry Pi!"
echo "===================================================================="
echo "  * Web Dashboard  : http://${PI_IP}:8765"
echo "  * Router Link    : Monitoring Default Gateway via Gigabit Ethernet"
echo "  * Instant Alerts : Configure ntfy.sh in the 'Alerts' tab"
echo "===================================================================="
echo "  To view live logs: docker compose logs -f"
echo "  To stop sentry   : docker compose down"
echo "===================================================================="
