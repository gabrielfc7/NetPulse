# NetPulse Pro ⚡ - Autonomous Wi-Fi & Network Diagnostic Studio

[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Raspberry%20Pi%20%7C%20Linux%20%7C%20Docker-cyan.svg)](#-deployment-options)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com)
[![Support](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-yellow.svg)](https://buymeacoffee.com/gabrielcacao)

> **Autonomous Local Wi-Fi Diagnostics, 24/7 Raspberry Pi Sentry & Network Security Defense.**  
> Continuously monitors network health, catches and diagnoses micro-disconnects in real time, audits network vulnerabilities, triggers non-disruptive self-healing, and pushes instant alerts with step-by-step fix recommendations directly to your phone and desktop.

---

## ☕ Support the Project

NetPulse Pro is 100% free, open-source, and privacy-respecting. All network telemetry and security audits run **locally on your machine** without sending data to third parties.

If you enjoy NetPulse Pro or if it helped you solve lag spikes, disconnects, or router vulnerabilities, consider supporting ongoing development:

👉 **[Buy Me a Coffee](https://buymeacoffee.com/gabrielcacao)** ☕

---

## ✨ Highlights & Key Features

- **Categorized Left Sidebar Navigation**: Clean, user-friendly layout grouped into *Monitoring & Health*, *Diagnostics & Analysis*, *Security & Defense*, and *Optimization & Repair* with responsive mobile drawer support.
- **🛡️ 6-Vector Security & Vulnerability Auditor**:
  - **Wi-Fi Protocol & Cipher Strength**: Audits WPA3/WPA2-AES security and flags outdated WEP/TKIP or open unencrypted SSIDs.
  - **Router Gateway Port Exposure**: Non-intrusively tests for exposed Telnet (23), UPnP (1900/5000), unencrypted HTTP management (80), and SMB (445).
  - **Host Firewall Status**: Verifies active Domain, Private, and Public profiles on Windows Defender Firewall or Linux UFW.
  - **ARP Spoofing & MitM Sentry**: Audits ARP tables for duplicate MACs, poisoned gateways, or rogue subnet responders.
  - **DNS Security & Privacy**: Validates encrypted DNS (Quad9, Cloudflare) and warns against unencrypted, easily-spoofed ISP resolvers.
  - **LAN Service Exposure**: Scans wildcard listening ports (`0.0.0.0`) for exposed databases or unauthenticated remote services.
  - **1-Click Vulnerability Remediations**: One-click actions to enable host firewalls, flush ARP tables, and apply Quad9 malware-blocking DNS.
- **🩺 Disconnect & Drop Doctor with Instant Solutions**:
  - Automatically isolates whether disconnects originate from your **Local Router Gateway** (Wi-Fi signal degradation, channel congestion, driver sleep throttling) or your **External ISP**.
  - Pushes **immediate actionable remediation advice** right after drops occur.
- **🎮 Gaming & Video Stream Anti-Lag Optimizer**:
  - 1-Click tuning to disable Windows Wi-Fi power throttling, optimize TCP stack autotuning, and reduce adapter roaming aggressiveness to prevent in-game ping spikes (Dota 2, CS2, Valorant, etc.).
- **📈 24/7 Outage Timeline & History**:
  - Embedded high-performance SQLite database (`netpulse.db`) logging ping, jitter, packet loss, and incident reports across 1h, 6h, 24h, and 7-day windows.
- **📡 Wi-Fi Spectrum Radar & Channel Advisor**:
  - Scans neighboring BSSIDs, measures channel contention across 2.4 GHz and 5 GHz bands, and identifies the cleanest broadcast channel.
- **🔔 Instant Push Alerts to Phone & Desktop**:
  - **ntfy.sh** (100% free, zero account needed, instant phone push for iOS & Android).
  - **Discord Webhooks** (multi-channel broadcast with rich embeds and test triggers).
  - **Telegram Bot** (direct instant messaging).
  - **Native OS Desktop Notifications**.

---

## 🚀 Deployment Options

Choose the deployment method that fits your setup:

```
┌────────────────────────────────────────────────────────────────────────┐
│                          DEPLOYMENT MODES                              │
├──────────────────────┬──────────────────────────┬──────────────────────┤
│      Windows PC      │   Raspberry Pi (24/7)    │   Docker Container   │
│  (Desktop Studio)    │   (Hardware Sentry)      │ (NAS / Linux Server) │
└──────────────────────┴──────────────────────────┴──────────────────────┘
```

---

### Option 1: Running on Windows (Recommended for Gaming & Wi-Fi Tuning)

Running NetPulse Pro natively on Windows gives the app direct access to the Windows WLAN AutoConfig API, adapter power management, and TCP stack configurations.

#### Quick Start:
1. Clone or download the repository:
   ```powershell
   git clone https://github.com/gabrielcacao/NetPulse.git
   cd NetPulse
   ```
2. Install Python 3.10+ (ensure *"Add Python to PATH"* is checked during installation).
3. **Run as Administrator** (Recommended):
   - Right-click `start_admin.bat` and select **"Run as administrator"**.
   - *Why Administrator?* Elevated rights allow NetPulse to inspect firewall profiles, tune Wi-Fi adapter roaming aggressiveness, clear ARP caches, and configure DNS.
4. **Standard Launch**: Double-click `start.bat` or run:
   ```powershell
   pip install -r requirements.txt
   python run.py
   ```
5. Open your browser at **`http://127.0.0.1:8765`**.

---

### Option 2: Running 24/7 on Raspberry Pi (Hardware Sentry Appliance)

Transform any Raspberry Pi (Pi 3, Pi 4, Pi 5, or Pi Zero 2W) into a **dedicated 24/7 network watchdog**. Connect the Pi via Ethernet to your router to monitor connection health around the clock, even when your PC is turned off.

#### 1-Click Automated Setup:
1. Copy the project folder to your Raspberry Pi:
   ```bash
   scp -r NetOptimizer pi@raspberrypi.local:~/netpulse
   ```
2. SSH into your Raspberry Pi and execute the installer:
   ```bash
   cd ~/netpulse
   chmod +x install_pi.sh
   ./install_pi.sh
   ```
3. The script will:
   - Install Docker and Docker Compose (if not already present).
   - Configure host networking for raw Gigabit ICMP ping accuracy.
   - Start NetPulse in the background as an auto-restarting service.
4. Access the dashboard from any smartphone, laptop, or tablet on your Wi-Fi network:
   ```
   http://<raspberry-pi-ip>:8765
   ```

#### Native Systemd Service (Without Docker):
If you prefer running NetPulse natively on Raspberry Pi OS:
```bash
sudo apt update && sudo apt install -y python3-pip python3-venv git
cd ~/netpulse
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create systemd service
sudo tee /etc/systemd/system/netpulse.service > /dev/null <<EOF
[Unit]
Description=NetPulse Pro 24/7 Network Sentry
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now netpulse
```

---

### Option 3: Running via Docker (Linux, Synology NAS, Unraid, TrueNAS)

NetPulse Pro includes a multi-arch container image (`linux/amd64` and `linux/arm64`).

```bash
# Clone the repository
git clone https://github.com/gabrielcacao/NetPulse.git
cd NetPulse

# Start the container
docker compose up -d --build
```

#### Docker Compose Configuration (`docker-compose.yml`):
```yaml
version: '3.8'

services:
  netpulse:
    build: .
    image: netpulse-pro:latest
    container_name: netpulse-sentry
    restart: unless-stopped
    # Host networking allows direct ICMP pings without Docker NAT virtualization overhead
    network_mode: host
    environment:
      - NETPULSE_DOCKER=1
      - NETPULSE_DATA_DIR=/app/data
    volumes:
      - ./data:/app/data
      - /sys:/sys:ro
      - /proc:/proc:ro
```

- **View Live Logs**: `docker compose logs -f`
- **Stop Container**: `docker compose down`
- **Update & Rebuild**: `docker compose up -d --build`

---

## 🔔 Setting Up Instant Phone Alerts (ntfy.sh)

NetPulse Pro allows you to receive instant drop and vulnerability alerts on your mobile device without registering an account:

1. Open the **Alerts & Phone Push** section in the sidebar.
2. In the **ntfy.sh Topic Name** field, type a unique secret topic name (e.g. `myhome-netpulse-9472`).
3. On your phone, install the free **ntfy** app from Google Play or the iOS App Store (or visit `https://ntfy.sh/myhome-netpulse-9472` in any browser).
4. Tap **Subscribe to topic** and enter your topic name.
5. In NetPulse Pro, click **"Test Alert"** — you will immediately hear a chime and receive a notification!

---

## 📂 Project Architecture

```
NetPulse/
├── backend/
│   ├── server.py              # FastAPI application & REST API routes
│   ├── security_audit.py      # 6-Vector defensive vulnerability engine
│   ├── drop_doctor.py         # WLAN AutoConfig analyzer & remediation builder
│   ├── monitor.py             # 24/7 monitoring daemon & autonomous healer
│   ├── db.py                  # SQLite WAL metrics and incident database
│   ├── notifier.py            # Phone push (ntfy.sh), Discord, Telegram, Windows Toast
│   ├── wifi_scanner.py        # Wi-Fi spectrum radar & BSSID channel advisor
│   ├── ping_analyzer.py       # Cross-platform ping, jitter, MTU discovery
│   ├── dns_bench.py           # DNS Turbo benchmark & 1-click switcher
│   ├── bufferbloat.py         # Loaded latency & router QoS analyzer
│   ├── process_monitor.py     # Network bandwidth hog & socket monitor
│   ├── optimizer.py           # 1-Click adapter repairs & TCP stack tuning
│   └── utils.py               # Cross-platform OS helpers (Windows & Linux)
├── frontend/
│   ├── index.html             # Glassmorphism dark dashboard UI with sidebar
│   ├── css/style.css          # Dials, charts, responsive animations
│   └── js/app.js              # Real-time state management, charts, and API bridges
├── Dockerfile                 # Multi-architecture container build
├── docker-compose.yml         # Host-networking Docker Compose configuration
├── install_pi.sh              # 1-Click installer for Raspberry Pi OS
├── run.py                     # Universal Python launcher
├── start.bat                  # Standard Windows batch launcher
├── start_admin.bat            # Elevated Windows Administrator launcher
├── requirements.txt           # Python dependencies
├── LICENSE                    # MIT Open Source License
└── README.md                  # Comprehensive Documentation
```

---

## 📜 Open Source License & Attribution

This project is licensed under the **MIT License** — you are free to use, modify, distribute, and build upon it.

See the full [LICENSE](LICENSE) for details.

### 👤 Author & Maintainer
- **Gabriel Cacao**
- Support: [buymeacoffee.com/gabrielcacao](https://buymeacoffee.com/gabrielcacao)

### 💖 Third-Party Acknowledgements
NetPulse Pro is built upon open-source tools and libraries:
- [FastAPI](https://fastapi.tiangolo.com/) & [Uvicorn](https://www.uvicorn.org/) — High-performance asynchronous API framework
- [Chart.js](https://www.chartjs.org/) — Responsive charting engine
- [Lucide Icons](https://lucide.dev/) — Modern UI icon library
- [Tailwind CSS](https://tailwindcss.com/) — Utility-first styling framework
- [psutil](https://github.com/giampaolo/psutil) — Cross-platform process and system monitoring
- [ntfy.sh](https://ntfy.sh/) — Free, open-source HTTP push notifications
