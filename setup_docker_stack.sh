#!/usr/bin/env bash
# NetPulse Pro & God's Eye View - Dual Container Deployment for Raspberry Pi 4
set -e

echo "===================================================================="
echo "    Raspberry Pi 4 - Docker Stack Setup: NetPulse & God's Eye View   "
echo "===================================================================="

# 1. Stop native bare-metal NetPulse service if running
if systemctl is-active --quiet netpulse 2>/dev/null; then
    echo "[*] Stopping native netpulse service to free port 8765..."
    sudo systemctl stop netpulse 2>/dev/null || true
    sudo systemctl disable netpulse 2>/dev/null || true
fi

# 2. Ensure Docker is installed
if ! command -v docker &> /dev/null; then
    echo "[!] Docker not detected. Installing Docker automatically..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker "$USER" 2>/dev/null || true
    rm -f get-docker.sh
    echo "[+] Docker installed successfully."
fi

# 3. Ensure Docker Compose plugin is installed
if ! docker compose version &> /dev/null && ! sudo docker compose version &> /dev/null; then
    echo "[!] Docker Compose plugin not found. Installing..."
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin
fi

# Determine if docker needs sudo
DOCKER_CMD="docker"
if ! docker ps &>/dev/null; then
    DOCKER_CMD="sudo docker"
fi
echo "[+] Using Docker binary: ${DOCKER_CMD}"

# 4. Deploy NetPulse Pro & Portal Container
NETPULSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "[*] Deploying NetPulse Pro in ${NETPULSE_DIR}..."
cd "${NETPULSE_DIR}"
mkdir -p data
$DOCKER_CMD compose down 2>/dev/null || true
$DOCKER_CMD compose up -d --build

# 5. Deploy God's Eye View Container
GEV_DIR="${HOME}/gods-eye-view"
echo "[*] Deploying God's Eye View in ${GEV_DIR}..."
if [ ! -d "${GEV_DIR}" ]; then
    echo "[*] Cloning gods-eye-view repository..."
    git clone https://github.com/bilawalsidhu/gods-eye-view.git "${GEV_DIR}"
else
    echo "[*] Existing gods-eye-view folder found. Pulling latest updates..."
    cd "${GEV_DIR}" && git pull || true
fi

cd "${GEV_DIR}"

# Ensure port binding allows LAN access (0.0.0.0:4173:4173)
if grep -q "127.0.0.1:4173" compose.yaml 2>/dev/null; then
    echo "[*] Updating compose.yaml to bind 0.0.0.0:4173 for LAN access..."
    sed -i 's/127\.0\.0\.1:4173/0.0.0.0:4173/g' compose.yaml
fi

# Ensure trusted peers for LAN access
if [ ! -f .env ] || ! grep -q "GEV_KEY_SETUP_TRUSTED_PEERS" .env; then
    echo "[*] Setting GEV_KEY_SETUP_TRUSTED_PEERS=none in .env..."
    echo "GEV_KEY_SETUP_TRUSTED_PEERS=none" >> .env
fi

echo "[*] Building and starting God's Eye View container..."
$DOCKER_CMD compose down 2>/dev/null || true
$DOCKER_CMD compose up -d --build

# 6. Configure Daily 3:00 AM Pi-hole Gravity Auto-Updater
echo "[*] Configuring 3:00 AM daily Pi-hole gravity auto-update cron..."
CRON_JOB="0 3 * * * ${DOCKER_CMD} exec pihole-unbound pihole updateGravity > /home/\${USER}/pihole-gravity.log 2>&1"
(crontab -l 2>/dev/null | grep -v "pihole updateGravity"; echo "${CRON_JOB}") | crontab - 2>/dev/null || true

PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$PI_IP" ]; then
    PI_IP="<raspberry-pi-ip>"
fi

echo ""
echo "===================================================================="
echo "  [SUCCESS] All Services Running on Docker!"
echo "===================================================================="
echo "  * Sentry Hub Portal   : http://pi.local  (or http://${PI_IP})"
echo "  * NetPulse Pro Sentry : http://${PI_IP}:8765"
echo "  * God's Eye View 3D   : http://${PI_IP}:4173"
echo "  * Pi-hole + Unbound   : http://${PI_IP}:8088/admin (DNS: port 53)"
echo "  * Homepage Dashboard  : http://${PI_IP}:3000"
echo "  * Daily 3 AM Ad Update: Configured in crontab (updateGravity)"
echo "===================================================================="
echo "  Check container status : ${DOCKER_CMD} ps"
echo "  NetPulse live logs     : cd ${NETPULSE_DIR} && ${DOCKER_CMD} compose logs -f"
echo "  God's Eye View logs    : cd ${GEV_DIR} && ${DOCKER_CMD} compose logs -f"
echo "  Pi-hole live logs      : cd ${NETPULSE_DIR} && ${DOCKER_CMD} compose logs -f pihole"
echo "===================================================================="
