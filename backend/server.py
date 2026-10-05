import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from .utils import is_admin, get_default_gateway, get_active_wifi_interface, get_system_hardware_info
from .wifi_scanner import parse_wifi_interface, scan_nearby_networks, analyze_channels
from .ping_analyzer import ping_host, run_multi_hop_diagnostic, test_mtu_discovery
from .drop_doctor import analyze_wifi_drops
from .dns_bench import run_dns_benchmark, apply_adapter_dns
from .bufferbloat import run_bufferbloat_test
from .process_monitor import get_network_processes, terminate_process
from .optimizer import (
    flush_dns,
    clear_arp_cache,
    renew_dhcp_lease,
    tune_tcp_stack,
    fix_wifi_power_saving,
    tune_adapter_advanced,
    reset_winsock_and_ip,
    restart_wifi_adapter,
    run_full_repair_sequence
)
from .db import get_metrics_history, get_recent_incidents, get_all_settings, update_settings
from .notifier import broadcast_alert, send_test_notification, test_single_discord_webhook, send_windows_toast
from .monitor import monitor_daemon
from .cache import system_cache, cached
from .bandwidth import bandwidth_tracker
from .security_audit import run_full_security_audit, enable_host_firewall, disable_smb_file_sharing, enable_smb_file_sharing
from .version import get_full_version_manifest, check_remote_updates, CURRENT_VERSION

app = FastAPI(title="NetPulse Pro - WiFi & Network Diagnostic Studio", version=CURRENT_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

@app.on_event("startup")
def on_startup():
    """Start 24/7 background monitor daemon."""
    monitor_daemon.start()

class SetDnsRequest(BaseModel):
    primary: str
    secondary: Optional[str] = ""
    interface_name: Optional[str] = "Wi-Fi"

class ProcessKillRequest(BaseModel):
    pid: int

class SettingsUpdateRequest(BaseModel):
    settings: dict

class SingleWebhookTestRequest(BaseModel):
    webhook_url: str

@app.get("/api/history")
def get_history(hours: int = 1):
    """Get continuous latency, packet loss, and jitter historical samples."""
    return get_metrics_history(hours=hours)

@app.get("/api/incidents")
def get_incidents(limit: int = 25):
    """Get list of past network outages, drop durations, and auto-heal actions."""
    return get_recent_incidents(limit=limit)

@app.get("/api/system-health")
def get_system_hardware():
    """Get host / Raspberry Pi CPU temperature, RAM, uptime, and platform details."""
    return get_system_hardware_info()

@app.get("/api/settings")
def get_app_settings():
    """Get notification channels and auto-repair settings."""
    return get_all_settings()

@app.post("/api/settings")
def update_app_settings(req: SettingsUpdateRequest):
    """Save notification channels and auto-repair settings."""
    update_settings(req.settings)
    return {"success": True, "message": "Settings updated successfully."}

@app.post("/api/test-notification")
def trigger_test_alert():
    """Send test notification to user's phone / PC."""
    return send_test_notification()

@app.post("/api/test-toast")
def trigger_test_toast():
    """Send native Windows desktop toast alert."""
    ok = send_windows_toast(
        title="NetPulse: Test Drop Alert",
        message="Simulated connection drop. Real-time diagnosis & immediate fix advice active.",
        fix_advice="Disable Wi-Fi Adapter Power Saving to avoid sleep timeouts while gaming."
    )
    return {"success": ok, "message": "Windows desktop toast sent!" if ok else "Toast not available on this platform."}

@app.post("/api/test-discord-single")
def test_discord_single(req: SingleWebhookTestRequest):
    """Test sending an immediate alert to an individual Discord webhook URL."""
    return test_single_discord_webhook(req.webhook_url)

@app.get("/api/daemon-status")
def get_daemon_status():
    """Get live 24/7 monitor daemon state."""
    return monitor_daemon.latest_status

@app.get("/api/status")
def get_system_status():
    """Get active Wi-Fi interface telemetry and adapter status."""
    wifi_info = parse_wifi_interface()
    adapter_meta = get_active_wifi_interface()
    admin = is_admin()

    return {
        "admin_privileges": admin,
        "wifi": wifi_info,
        "adapter_hardware": adapter_meta,
        "default_gateway": get_default_gateway()
    }

@app.get("/api/wifi-scan")
def get_wifi_scan():
    """Scan nearby networks, analyze channel congestion, and get optimal channels."""
    wifi_info = parse_wifi_interface()
    networks = scan_nearby_networks()
    analysis = analyze_channels(wifi_info, networks)
    return {
        "current_interface": wifi_info,
        "networks": networks,
        "analysis": analysis
    }

@app.get("/api/ping-test")
def get_ping_diagnostic(gateway: Optional[str] = None):
    """Run dual-hop latency, jitter, and packet loss diagnosis."""
    return run_multi_hop_diagnostic(gateway_override=gateway)

@app.get("/api/mtu-test")
def get_mtu_test():
    """Test optimal MTU size and detect packet fragmentation."""
    return test_mtu_discovery()

@app.get("/api/drops")
def get_drops_report(days: int = 7):
    """Analyze WLAN AutoConfig event log for connection drops and disconnect reasons."""
    return analyze_wifi_drops(days=days)

@app.get("/api/dns-benchmark")
def get_dns_benchmark():
    """Benchmark current DNS against Cloudflare, Google, Quad9, and OpenDNS."""
    return run_dns_benchmark()

@app.post("/api/set-dns")
def set_dns(req: SetDnsRequest):
    """Apply DNS servers to Wi-Fi adapter or reset to DHCP."""
    return apply_adapter_dns(req.primary, req.secondary or "", req.interface_name or "Wi-Fi")

@app.get("/api/bufferbloat")
def get_bufferbloat():
    """Measure loaded vs unloaded latency and throughput speed."""
    return run_bufferbloat_test()

@app.get("/api/processes")
def get_processes():
    """Inspect active network-using processes and sockets."""
    return get_network_processes()

@app.post("/api/terminate-process")
def kill_process(req: ProcessKillRequest):
    """Terminate bandwidth hog process."""
    return terminate_process(req.pid)

@app.get("/api/bandwidth-realtime")
def get_bandwidth_realtime(interface: Optional[str] = None):
    """Real-time interface I/O bandwidth throughput engine."""
    return bandwidth_tracker.get_realtime_bandwidth(interface_hint=interface)

@app.get("/api/security-audit")
def get_security_audit():
    """Run comprehensive 6-vector network security & vulnerability audit."""
    return run_full_security_audit()

@app.post("/api/security-fix/{action}")
def execute_security_fix(action: str):
    """Execute 1-click remediation for detected security vulnerabilities."""
    action = action.lower()
    if action == "enable_firewall":
        return enable_host_firewall()
    elif action == "apply_quad9_dns":
        return apply_adapter_dns("9.9.9.9", "149.112.112.112", "Wi-Fi")
    elif action == "clear_arp":
        return clear_arp_cache()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown security fix action: {action}")

@app.post("/api/optimize/{action}")
def execute_optimization(action: str):
    """Execute local network fix and invalidate stale system caches."""
    action = action.lower()
    system_cache.clear()

    if action == "flush_dns":
        return flush_dns()
    elif action == "clear_arp":
        return clear_arp_cache()
    elif action == "renew_dhcp":
        return renew_dhcp_lease()
    elif action == "tune_tcp":
        return tune_tcp_stack()
    elif action == "fix_power_save":
        return fix_wifi_power_saving()
    elif action == "tune_adapter_gaming":
        return tune_adapter_advanced()
    elif action == "reset_winsock":
        return reset_winsock_and_ip()
    elif action == "restart_adapter":
        return restart_wifi_adapter()
    elif action == "full_repair":
        return run_full_repair_sequence()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown optimization action '{action}'")

@cached(ttl=3.0)
def _compute_full_health():
    wifi_info = parse_wifi_interface()

    # Quick ping check (3 pings to gateway)
    gw = get_default_gateway()
    gw_ping = ping_host(gw, count=3, timeout_ms=800)
    gw_loss = gw_ping.get("loss_percent", 0.0)
    gw_avg = gw_ping.get("avg_ms", 2.0)
    gw_jitter = gw_ping.get("jitter_ms", 0.0)

    # Disconnected state guard
    if not wifi_info.get("connected") or gw_loss >= 100.0:
        return {
            "score": 0,
            "grade": "F",
            "grade_text": "Disconnected",
            "badge_color": "#EF4444",
            "wifi": wifi_info,
            "gateway_ping": gw_ping
        }

    sig = wifi_info.get("signal_percent", 100 if wifi_info.get("is_ethernet") else 50)

    # Score components
    # 1. Signal score (max 30)
    signal_score = (sig / 100.0) * 30

    # 2. Packet Loss score (max 30)
    if gw_loss == 0:
        loss_score = 30
    elif gw_loss < 5:
        loss_score = 15
    else:
        loss_score = 0

    # 3. Latency & Jitter score (max 25)
    if gw_avg <= 3 and gw_jitter <= 2:
        lat_score = 25
    elif gw_avg <= 10 and gw_jitter <= 5:
        lat_score = 18
    elif gw_avg <= 25:
        lat_score = 10
    else:
        lat_score = 2

    # 4. Band score (max 15): Wired Ethernet & 5GHz/6GHz is superior
    band = wifi_info.get("band", "").lower()
    if wifi_info.get("is_ethernet") or "wired" in band or "gigabit" in band or "ethernet" in band:
        band_score = 15
    elif "6" in band:
        band_score = 15
    elif "5" in band:
        band_score = 15
    elif "2.4" in band:
        band_score = 8
    else:
        band_score = 5

    total_score = min(100, max(0, round(signal_score + loss_score + lat_score + band_score)))

    if total_score >= 90:
        grade = "A+"
        grade_text = "Elite Performance"
        badge_color = "#10B981"
    elif total_score >= 80:
        grade = "A"
        grade_text = "Excellent"
        badge_color = "#34D399"
    elif total_score >= 70:
        grade = "B"
        grade_text = "Good"
        badge_color = "#60A5FA"
    elif total_score >= 55:
        grade = "C"
        grade_text = "Fair (Occasional Stutter)"
        badge_color = "#FBBF24"
    elif total_score >= 40:
        grade = "D"
        grade_text = "Sub-Optimal (Packet Loss / Jitter)"
        badge_color = "#FB923C"
    else:
        grade = "F"
        grade_text = "Degraded (Critical Drops)"
        badge_color = "#EF4444"

    return {
        "score": total_score,
        "grade": grade,
        "grade_text": grade_text,
        "badge_color": badge_color,
        "wifi": wifi_info,
        "gateway_ping": gw_ping
    }

@app.get("/api/full-health")
def get_full_health():
    """
    Compute comprehensive connection health score (0-100) and letter grade with caching.
    Handles disconnected states and wired Ethernet appliance mode correctly.
    """
    return _compute_full_health()

@app.get("/api/security-audit")
def get_security_audit(force: bool = False):
    """
    Perform 6-vector defensive security and vulnerability audit:
    Wi-Fi encryption, Router gateway ports, Host firewall, ARP MitM, DNS integrity, Wildcard ports.
    """
    return run_full_security_audit(force_refresh=force)

@app.post("/api/security-fix/{action}")
def run_security_fix_action(action: str):
    """
    Apply 1-click remediation for detected security vulnerabilities.
    """
    if action == "enable_firewall":
        return enable_host_firewall()
    elif action == "clear_arp":
        return clear_arp_cache()
    elif action == "apply_quad9_dns":
        return apply_adapter_dns("Wi-Fi", "9.9.9.9", "149.112.112.112")
    elif action == "disable_smb":
        return disable_smb_file_sharing()
    elif action == "enable_smb":
        return enable_smb_file_sharing()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown security fix action: {action}")

@app.get("/api/version")
def get_version_info(force: bool = False):
    """
    Get application version, commit SHA, changelog, and remote GitHub update status.
    """
    return get_full_version_manifest(force_check=force)

@app.post("/api/check-updates")
def check_updates_now():
    """
    Check GitHub repository for newer releases and updates.
    """
    return check_remote_updates(force=True)

# Serve Frontend static assets
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({"status": "Frontend files not found."})
