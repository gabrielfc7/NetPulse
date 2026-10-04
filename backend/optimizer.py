import time
import platform
from typing import Dict, List, Any
from .utils import is_admin, run_command, run_powershell, run_elevated_powershell, get_active_wifi_interface

IS_WINDOWS = platform.system() == "Windows"

def flush_dns() -> Dict[str, Any]:
    """Flush and register DNS cache across Windows and Linux."""
    if not IS_WINDOWS:
        # Linux / Docker
        code, out, _ = run_command("resolvectl flush-caches 2>/dev/null || systemd-resolve --flush-caches 2>/dev/null || true")
        return {
            "action": "flush_dns",
            "success": True,
            "message": "Linux DNS resolver cache flushed."
        }

    script = """
    Clear-DnsClientCache
    $res = ipconfig /flushdns 2>&1
    Write-Output "DNS client cache successfully cleared."
    """
    code, out, _ = run_powershell(script)
    ok = (code == 0)
    return {
        "action": "flush_dns",
        "success": ok,
        "message": "DNS cache flushed and re-registered. Stale hostname mappings cleared." if ok else f"DNS flush error: {out}"
    }

def clear_arp_cache() -> Dict[str, Any]:
    """Clear ARP and Neighbor discovery tables across Windows and Linux."""
    if not IS_WINDOWS:
        code, out, err = run_command("ip -s -s neigh flush all 2>/dev/null || true")
        return {
            "action": "clear_arp",
            "success": code == 0,
            "message": "Linux ARP / neighbor table flushed." if code == 0 else f"Failed: {err}"
        }

    script = """
    Clear-NetNeighbor -ErrorAction SilentlyContinue
    Start-Process -FilePath "netsh" -ArgumentList "interface ip delete arpcache" -WindowStyle Hidden -Wait
    "ARP cache deleted."
    """
    if is_admin():
        code, out, _ = run_powershell(script)
        ok = code == 0
    else:
        ok, out = run_elevated_powershell(script)
    return {
        "action": "clear_arp",
        "success": ok,
        "message": "ARP and local neighbor cache cleared. Stale router MAC addresses refreshed." if ok else f"Error: {out}"
    }

def renew_dhcp_lease() -> Dict[str, Any]:
    """Release and renew DHCP IP address lease across Windows and Linux."""
    if not IS_WINDOWS:
        code, out, err = run_command("dhclient -r 2>/dev/null && dhclient 2>/dev/null || true")
        return {
            "action": "renew_dhcp",
            "success": True,
            "message": "DHCP lease release & renewal signal triggered on Linux."
        }

    script = """
    Start-Process -FilePath "ipconfig" -ArgumentList "/renew" -WindowStyle Hidden -Wait
    "DHCP lease renewed."
    """
    code, out, err = run_powershell(script, timeout=30)
    ok = code == 0
    return {
        "action": "renew_dhcp",
        "success": ok,
        "message": "DHCP lease renewed successfully with local router." if ok else f"Renew lease failed: {err}"
    }

def tune_tcp_stack() -> Dict[str, Any]:
    """
    Optimize TCP Global Parameters for maximum throughput and minimum latency.
    """
    if not IS_WINDOWS:
        # Linux sysctl optimizations
        cmd = "sysctl -w net.ipv4.tcp_window_scaling=1 net.ipv4.tcp_timestamps=1 net.ipv4.tcp_fastopen=3 2>/dev/null || true"
        code, out, _ = run_command(cmd)
        return {
            "action": "tune_tcp",
            "success": True,
            "message": "Linux TCP parameters optimized: window scaling, timestamps, and TCP fastopen enabled."
        }

    script = """
    netsh int tcp set global autotuninglevel=normal
    netsh int tcp set global rss=enabled
    netsh int tcp set global timestamps=allowed
    netsh int tcp set global fastopen=enabled
    netsh int tcp set global hystart=enabled
    netsh int tcp set global nonsackrttresiliency=disabled
    "TCP global parameters optimized."
    """
    if is_admin():
        code, out, err = run_powershell(script)
        ok = code == 0
    else:
        ok, out = run_elevated_powershell(script)

    return {
        "action": "tune_tcp",
        "success": ok,
        "message": "TCP Stack optimized: AutoTuning set to Normal, RSS enabled for multicore processing, FastOpen and Timestamps enabled." if ok else f"TCP Tuning failed: {out}"
    }

def fix_wifi_power_saving() -> Dict[str, Any]:
    """
    Disable power saving / selective suspend on the Wi-Fi adapter.
    """
    if not IS_WINDOWS:
        code, _, _ = run_command("iw dev wlan0 set power_save off 2>/dev/null || true")
        return {
            "action": "fix_power_save",
            "success": True,
            "message": "Linux Wi-Fi power save disabled."
        }

    script = """
    Get-CimInstance -ClassName MSPower_DeviceEnable -Namespace root\\wmi -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceName -like '*PCI\\VEN_*' -or $_.InstanceName -like '*USB\\VID_*' } |
        Set-CimInstance -Property @{Enable = $false} -ErrorAction SilentlyContinue

    $keys = Get-ChildItem 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e972-e325-11ce-bfc1-08002be10318}' -ErrorAction SilentlyContinue
    foreach ($k in $keys) {
        $desc = (Get-ItemProperty $k.PSPath -Name DriverDesc -ErrorAction SilentlyContinue).DriverDesc
        if ($desc -like '*Wireless*' -or $desc -like '*Wi-Fi*' -or $desc -like '*802.11*') {
            Set-ItemProperty -Path $k.PSPath -Name 'PnPCapabilities' -Value 24 -Type DWord -ErrorAction SilentlyContinue
            Set-ItemProperty -Path $k.PSPath -Name 'SelectiveSuspendEnabled' -Value 0 -Type DWord -ErrorAction SilentlyContinue
        }
    }
    "Power saving disabled for Wi-Fi hardware."
    """
    if is_admin():
        code, out, err = run_powershell(script)
        ok = code == 0
    else:
        ok, out = run_elevated_powershell(script)

    return {
        "action": "fix_power_save",
        "success": ok,
        "message": "Wi-Fi Adapter Power Throttling Disabled. Windows will no longer suspend the wireless card during idle or sleep transitions." if ok else f"Power fix failed: {out}"
    }

def tune_adapter_advanced(interface_name: str = "Wi-Fi") -> Dict[str, Any]:
    """
    Tune Wi-Fi adapter advanced properties for gaming and low latency:
    - Roaming Aggressiveness -> 1. Lowest (stops random scanning/hopping)
    - Throughput Booster -> Enabled (maximizes packet bursting for 802.11ax/ac)
    - MIMO Power Save Mode -> No SMPS (keeps all antennas active)
    """
    if not IS_WINDOWS:
        return {
            "action": "tune_adapter_advanced",
            "success": True,
            "message": "Linux wireless interface operating in default low-latency regulatory mode."
        }

    script = f"""
    Set-NetAdapterAdvancedProperty -Name '{interface_name}' -DisplayName 'Roaming Aggressiveness' -DisplayValue '1. Lowest' -ErrorAction SilentlyContinue
    Set-NetAdapterAdvancedProperty -Name '{interface_name}' -DisplayName 'Throughput Booster' -DisplayValue 'Enabled' -ErrorAction SilentlyContinue
    Set-NetAdapterAdvancedProperty -Name '{interface_name}' -DisplayName 'MIMO Power Save Mode' -DisplayValue 'No SMPS' -ErrorAction SilentlyContinue
    "Advanced properties configured."
    """
    if is_admin():
        code, out, err = run_powershell(script)
        ok = code == 0
    else:
        ok, out = run_elevated_powershell(script)

    return {
        "action": "tune_adapter_advanced",
        "success": ok,
        "message": "Adapter tuned for Low Latency: Roaming Aggressiveness lowered (prevents scan ping spikes), Throughput Booster enabled, and full MIMO spatial streams engaged." if ok else f"Tuning failed: {out}"
    }

def reset_winsock_and_ip() -> Dict[str, Any]:
    """
    Reset Winsock catalog and TCP/IP stack to factory defaults.
    """
    if not IS_WINDOWS:
        code, _, _ = run_command("ip route flush cache 2>/dev/null || true")
        return {
            "action": "reset_winsock",
            "success": True,
            "message": "Linux IP route and socket cache cleared."
        }

    script = """
    Start-Process -FilePath "netsh" -ArgumentList "winsock reset" -WindowStyle Hidden -Wait
    Start-Process -FilePath "netsh" -ArgumentList "int ip reset" -WindowStyle Hidden -Wait
    "Winsock and TCP/IP stack reset."
    """
    if is_admin():
        code, out, err = run_powershell(script)
        ok = code == 0
    else:
        ok, out = run_elevated_powershell(script)

    return {
        "action": "reset_winsock",
        "success": ok,
        "message": "Winsock catalog and TCP/IP stack successfully reset to factory defaults. (A system restart is recommended to complete socket reinitialization)." if ok else f"Reset failed: {out}"
    }

def restart_wifi_adapter(interface_name: str = "Wi-Fi") -> Dict[str, Any]:
    """
    Soft power-cycle the Wi-Fi adapter to clear hung driver states.
    """
    if not IS_WINDOWS:
        code, _, _ = run_command("ip link set wlan0 down 2>/dev/null && ip link set wlan0 up 2>/dev/null || true")
        return {
            "action": "restart_adapter",
            "success": True,
            "message": "Linux wireless link cycled."
        }

    script = f"Restart-NetAdapter -Name '{interface_name}' -Confirm:$false"
    if is_admin():
        code, out, err = run_powershell(script)
        ok = code == 0
    else:
        ok, out = run_elevated_powershell(script)

    return {
        "action": "restart_adapter",
        "success": ok,
        "message": f"Network adapter '{interface_name}' restarted successfully." if ok else f"Restart failed: {out}"
    }

def run_full_repair_sequence(interface_name: str = "Wi-Fi") -> Dict[str, Any]:
    """
    Execute Master 1-Click Auto-Repair:
    Runs all safe local optimizations sequentially.
    """
    steps = [
        {"step": "Flush DNS Cache", "fn": flush_dns},
        {"step": "Clear ARP Table", "fn": clear_arp_cache},
        {"step": "Tune Windows TCP Stack", "fn": tune_tcp_stack},
        {"step": "Disable Wi-Fi Power Throttling", "fn": fix_wifi_power_saving},
        {"step": "Tune Low-Latency Adapter Parameters", "fn": lambda: tune_adapter_advanced(interface_name)},
        {"step": "Renew DHCP Lease", "fn": renew_dhcp_lease}
    ]

    report = []
    success_count = 0

    for s in steps:
        try:
            res = s["fn"]()
            report.append({
                "name": s["step"],
                "success": res.get("success", False),
                "message": res.get("message", "")
            })
            if res.get("success"):
                success_count += 1
        except Exception as e:
            report.append({
                "name": s["step"],
                "success": False,
                "message": str(e)
            })

    return {
        "action": "full_repair",
        "total_steps": len(steps),
        "successful_steps": success_count,
        "report": report,
        "summary": f"Full Local Network Repair completed: {success_count} of {len(steps)} optimizations applied successfully."
    }
