import subprocess
import ctypes
import re
import socket
import logging
import platform
import os
import time
import locale
import json
import psutil
from pathlib import Path
from typing import Dict, Any, Tuple
from .cache import cached, system_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("NetOptimizer")

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

def _decode_bytes(b: bytes) -> str:
    """Safely decode command output bytes trying utf-8, OEM, and fallback encodings."""
    if not b:
        return ""
    preferred = locale.getpreferredencoding(False) or "utf-8"
    candidates = ["utf-8", preferred, "cp1252", "cp437", "iso-8859-1"]
    for enc in candidates:
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("utf-8", errors="replace")

def is_admin() -> bool:
    """Check if the current process has administrative or root privileges."""
    try:
        if IS_WINDOWS:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.geteuid() == 0
    except Exception:
        return False

def run_command(cmd, timeout=15, shell=True) -> Tuple[int, str, str]:
    """Execute a system command safely with robust encoding fallbacks."""
    try:
        proc = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            timeout=timeout
        )
        stdout = _decode_bytes(proc.stdout)
        stderr = _decode_bytes(proc.stderr)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)

def run_powershell(script: str, timeout=20) -> Tuple[int, str, str]:
    """Execute a PowerShell command if on Windows, or return fallback."""
    if not IS_WINDOWS:
        return 1, "", "PowerShell is not available on Linux/Docker"

    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout
        )
        stdout = _decode_bytes(proc.stdout)
        stderr = _decode_bytes(proc.stderr)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"PowerShell script timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)

def run_elevated_powershell(script: str, timeout=30) -> Tuple[bool, str]:
    """
    Run powershell script with elevation on Windows.
    On Linux, checks if running as root.
    """
    if not IS_WINDOWS:
        code, out, err = run_command(script, timeout=timeout)
        return code == 0, out if code == 0 else err

    # Windows direct test first
    code, out, err = run_powershell(script, timeout=timeout)
    if code == 0 and "requires elevation" not in out.lower() and "access is denied" not in err.lower():
        return True, out.strip() or "Execution succeeded."

    if is_admin():
        return False, err.strip() or out.strip()

    escaped_script = script.replace('"', '`"').replace("'", "''")
    elevated_cmd = f"Start-Process powershell -Verb RunAs -Wait -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command \"{escaped_script}\"'"
    code_elev, out_elev, err_elev = run_powershell(elevated_cmd, timeout=timeout)

    if code_elev == 0:
        return True, "Elevated execution completed."

    if "not supported" in err_elev.lower() or "invalidoperation" in err_elev.lower():
        return False, "This setting requires Administrator privileges. Please launch NetPulse via 'start_admin.bat'."

    return False, err_elev.strip() or "Operation requires Administrator privileges."

@cached(ttl=5.0)
def get_default_gateway() -> str:
    """Find default IPv4 gateway address across Windows and Linux / Docker with TTL caching."""
    if IS_WINDOWS:
        # 0. Ultra-fast route print (~20ms instead of 800ms PowerShell)
        code, route_out, _ = run_command("route print 0.0.0.0", timeout=3)
        if code == 0 and route_out:
            match_route = re.search(r"0\.0\.0\.0\s+0\.0\.0\.0\s+([\d\.]+)", route_out)
            if match_route and match_route.group(1) != "0.0.0.0":
                return match_route.group(1)

        # 1. Try language-independent PowerShell route lookup
        script = "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Select-Object -First 1).NextHop"
        code, out, _ = run_powershell(script, timeout=5)
        if code == 0 and out.strip():
            gw = out.strip()
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", gw) and gw != "0.0.0.0":
                return gw

        # 2. Try ipconfig with multilingual regex
        _, ipout, _ = run_command("ipconfig", timeout=5)
        match = re.search(r"(?:Default Gateway|Standardgateway|Passerelle par d[ée]faut|Puerta de enlace predeterminada|Gateway predefinito)[ .:]+([\d\.]+)", ipout, re.IGNORECASE)
        if match and match.group(1) != "0.0.0.0":
            return match.group(1)

        # 3. Try netsh
        _, netsh_out, _ = run_command("netsh interface ipv4 show addresses", timeout=5)
        match_netsh = re.search(r"(?:Default Gateway|Passerelle|Puerta)[ .:]+([\d\.]+)", netsh_out, re.IGNORECASE)
        if match_netsh and match_netsh.group(1) != "0.0.0.0":
            return match_netsh.group(1)

        return "192.168.1.1"

    # Linux / Docker / Raspberry Pi
    try:
        # Check /proc/net/route
        if os.path.exists("/proc/net/route"):
            with open("/proc/net/route") as f:
                for line in f.readlines()[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 3 and parts[1] == "00000000":
                        gw_hex = parts[2]
                        # Convert hex to decimal IP (little-endian bytes)
                        gw_ip = socket.inet_ntoa(bytes.fromhex(gw_hex)[::-1])
                        if gw_ip != "0.0.0.0":
                            return gw_ip
    except Exception:
        pass

    # Fallback to `ip route`
    code, out, _ = run_command("ip route show default", timeout=5)
    if code == 0 and out:
        match = re.search(r"default via ([\d\.]+)", out)
        if match:
            return match.group(1)

    return "192.168.1.1"

@cached(ttl=4.0)
def get_active_wifi_interface() -> dict:
    """Get active network adapter details (Wi-Fi or Ethernet on Windows/Pi/Linux) with fast psutil path & TTL caching."""
    if IS_WINDOWS:
        # Fast path via psutil + netsh (~40ms instead of 2400ms PowerShell)
        try:
            stats = psutil.net_if_stats()
            addrs = psutil.net_if_addrs()

            chosen_name = None
            is_wireless = True

            # 1. Look for Wi-Fi / Wireless adapter UP
            for name, s in stats.items():
                if s.isup and any(w in name.lower() for w in ['wi-fi', 'wireless', 'wlan']):
                    chosen_name = name
                    is_wireless = True
                    break

            # 2. Look for active wired/other adapter UP
            if not chosen_name:
                for name, s in stats.items():
                    if s.isup and 'loopback' not in name.lower() and 'tailscale' not in name.lower() and s.speed > 0:
                        chosen_name = name
                        is_wireless = any(w in name.lower() for w in ['wi-fi', 'wireless', 'wlan'])
                        break

            if chosen_name:
                ip = ""
                mac = ""
                if chosen_name in addrs:
                    for a in addrs[chosen_name]:
                        if a.family == socket.AF_INET and not a.address.startswith("127."):
                            ip = a.address
                        elif getattr(a, "family", None) == getattr(psutil, "AF_LINK", None):
                            mac = a.address

                # Fast DNS lookup via netsh
                dns_servers = ""
                try:
                    p = subprocess.run(['netsh', 'interface', 'ipv4', 'show', 'dnsservers', chosen_name], capture_output=True, text=True, timeout=2)
                    ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', p.stdout)
                    dns_servers = ", ".join(ips)
                except Exception:
                    pass

                speed_val = stats[chosen_name].speed if chosen_name in stats else 0
                speed_str = f"{speed_val} Mbps" if speed_val > 0 else ("Wi-Fi Link" if is_wireless else "Ethernet Link")

                return {
                    "Name": chosen_name,
                    "Description": chosen_name if not is_wireless else "Wireless Adapter",
                    "Mac": mac,
                    "Speed": speed_str,
                    "Index": 1,
                    "IP": ip,
                    "DNS": dns_servers,
                    "IsWireless": is_wireless
                }
        except Exception as e:
            logger.debug(f"Fast adapter check failed, falling back to PowerShell: {e}")

        # PowerShell fallback
        script = """
        $wifi = Get-NetAdapter -InterfaceDescription '*Wireless*', '*Wi-Fi*', '*802.11*' -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' } | Select-Object -First 1
        $isWireless = $true
        if (-not $wifi) {
            $wifi = Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'Up' } | Select-Object -First 1
            $isWireless = $false
        }
        if ($wifi) {
            $ipObj = Get-NetIPAddress -InterfaceIndex $wifi.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1
            $ip = if ($ipObj) { $ipObj.IPAddress } else { '' }
            $dnsObj = Get-DnsClientServerAddress -InterfaceIndex $wifi.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
            $dns = if ($dnsObj) { ($dnsObj.ServerAddresses -join ', ') } else { '' }
            [PSCustomObject]@{
                Name = $wifi.Name
                Description = $wifi.InterfaceDescription
                Mac = $wifi.MacAddress
                Speed = $wifi.LinkSpeed
                Index = $wifi.ifIndex
                IP = $ip
                DNS = $dns
                IsWireless = $isWireless
            } | ConvertTo-Json
        }
        """
        code, out, _ = run_powershell(script, timeout=8)
        if code == 0 and out.strip():
            try:
                res = json.loads(out)
                if isinstance(res, dict):
                    return res
            except Exception:
                pass
        return {"Name": "Wi-Fi", "Description": "Wireless Adapter", "IP": "", "DNS": "", "Index": 0, "IsWireless": True}

    # Linux / Raspberry Pi details
    iface_name = "eth0"
    ip_addr = ""
    dns_servers = ""
    mac_addr = ""

    try:
        addrs = psutil.net_if_addrs()
        # Find primary interface with IPv4
        for name, addr_list in addrs.items():
            if name != "lo":
                for addr in addr_list:
                    if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                        iface_name = name
                        ip_addr = addr.address
                    elif getattr(addr, "family", None) == getattr(psutil, "AF_LINK", None):
                        mac_addr = addr.address
    except Exception:
        pass

    # Read DNS from /etc/resolv.conf
    try:
        if os.path.exists("/etc/resolv.conf"):
            with open("/etc/resolv.conf") as f:
                dns_list = []
                for line in f:
                    if line.startswith("nameserver"):
                        dns_list.append(line.split()[1])
                dns_servers = ", ".join(dns_list)
    except Exception:
        pass

    is_wireless = "wlan" in iface_name or "wifi" in iface_name
    desc = f"Raspberry Pi Wireless ({iface_name})" if is_wireless else f"Raspberry Pi Gigabit Ethernet ({iface_name})"

    return {
        "Name": iface_name,
        "Description": desc,
        "Mac": mac_addr,
        "Speed": "1000 Mbps" if not is_wireless else "Wi-Fi Link",
        "Index": 1,
        "IP": ip_addr,
        "DNS": dns_servers,
        "IsWireless": is_wireless
    }

@cached(ttl=2.0)
def get_system_hardware_info() -> Dict[str, Any]:
    """Retrieve system hardware metrics (Pi CPU temp, RAM, CPU load, uptime) with TTL caching."""
    try:
        cpu_pct = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        uptime_sec = int(time.time() - psutil.boot_time())
    except Exception:
        cpu_pct = 0.0
        mem = type('obj', (object,), {'used': 0, 'total': 1, 'percent': 0})()
        uptime_sec = 0

    # Raspberry Pi temperature detection
    cpu_temp = None
    if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                cpu_temp = round(int(f.read().strip()) / 1000.0, 1)
        except Exception:
            pass

    # Model name detection (e.g. Raspberry Pi 4 Model B)
    device_model = platform.node()
    if os.path.exists("/proc/device-tree/model"):
        try:
            with open("/proc/device-tree/model") as f:
                device_model = f.read().strip().replace("\x00", "")
        except Exception:
            pass

    return {
        "platform": platform.system(),
        "arch": platform.machine(),
        "device_model": device_model,
        "cpu_percent": cpu_pct,
        "cpu_temp_c": cpu_temp,
        "memory_used_mb": round(mem.used / (1024 * 1024), 1),
        "memory_total_mb": round(mem.total / (1024 * 1024), 1),
        "memory_percent": mem.percent,
        "uptime_seconds": uptime_sec,
        "is_docker": os.path.exists("/.dockerenv") or os.environ.get("NETPULSE_DOCKER") == "1",
        "is_raspberry_pi": "Raspberry Pi" in device_model or (cpu_temp is not None and IS_LINUX)
    }
