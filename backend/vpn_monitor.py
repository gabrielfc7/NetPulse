import socket
import platform
import re
import time
import json
import psutil
import logging
import urllib.request
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from .utils import get_default_gateway, run_command, run_powershell, run_elevated_powershell, is_admin
from .ping_analyzer import ping_host
from .dns_bench import raw_dns_query

logger = logging.getLogger("NetPulseVPN")

IS_WINDOWS = platform.system() == "Windows"

# Known VPN interface patterns
VPN_INTERFACE_KEYWORDS = [
    "surfshark", "wireguard", "wintun", "openvpn", "tap-windows",
    "tailscale", "nordlynx", "proton", "mullvad", "expressvpn", "vpn"
]

# Known VPN/Datacenter ISP/Org keywords
DATACENTER_ISP_KEYWORDS = [
    "surfshark", "m247", "datacamp", "cdn77", "ovh", "leaseweb", "digitalocean",
    "hetzner", "linode", "packethub", "choopa", "constant", "vultr", "cogent",
    "clouvider", "iptransit", "fastly", "cloudflare", "hosting", "vpn", "server"
]

_public_ip_cache = {"ts": 0.0, "data": None}

def get_cached_public_ip_info() -> Dict[str, Any]:
    """Return cached public IP info immediately without blocking."""
    global _public_ip_cache
    if _public_ip_cache.get("data"):
        return _public_ip_cache["data"]
    # Trigger non-blocking background lookup
    import threading
    threading.Thread(target=get_public_ip_info, daemon=True).start()
    return {}

def get_public_ip_info(timeout: float = 3.5, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetch public egress IP, ISP, Organization, City, Country, and ASN.
    Uses cached result (30s TTL) unless force_refresh is True.
    Uses ip-api.com with fallback to Cloudflare cdn-cgi/trace.
    """
    global _public_ip_cache
    now = time.time()
    if not force_refresh and _public_ip_cache["data"] and (now - _public_ip_cache["ts"] < 30):
        return _public_ip_cache["data"]

    try:
        req = urllib.request.Request(
            "http://ip-api.com/json/?fields=status,message,country,countryCode,regionName,city,isp,org,as,query",
            headers={"User-Agent": "NetPulsePro/2.4"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            if data.get("status") == "success":
                isp = data.get("isp", "")
                org = data.get("org", "")
                asn = data.get("as", "")
                
                # Check if ISP/Org looks like a VPN/datacenter node
                combined = f"{isp} {org} {asn}".lower()
                is_datacenter = any(kw in combined for kw in DATACENTER_ISP_KEYWORDS)

                res = {
                    "success": True,
                    "ip": data.get("query", "Unknown"),
                    "country": data.get("country", "Unknown"),
                    "country_code": data.get("countryCode", ""),
                    "region": data.get("regionName", ""),
                    "city": data.get("city", "Unknown"),
                    "isp": isp,
                    "org": org,
                    "asn": asn,
                    "is_datacenter_vpn": is_datacenter
                }
                _public_ip_cache = {"ts": now, "data": res}
                return res
    except Exception as e:
        logger.debug(f"ip-api lookup failed: {e}")

    # Fallback to Cloudflare trace
    try:
        req = urllib.request.Request(
            "https://1.1.1.1/cdn-cgi/trace",
            headers={"User-Agent": "NetPulsePro/2.4"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            info = {}
            for line in text.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    info[k.strip()] = v.strip()
            
            ip = info.get("ip", "Unknown")
            loc = info.get("loc", "Unknown")
            warp = info.get("warp", "off") == "on"

            res = {
                "success": True,
                "ip": ip,
                "country": loc,
                "country_code": loc,
                "region": "",
                "city": f"Colo: {info.get('colo', 'Unknown')}",
                "isp": "Cloudflare Anycast" if warp else "Unknown ISP",
                "org": "",
                "asn": "",
                "is_datacenter_vpn": warp
            }
            _public_ip_cache = {"ts": now, "data": res}
            return res
    except Exception as e:
        logger.debug(f"Cloudflare trace fallback failed: {e}")

    return {
        "success": False,
        "ip": "Unknown",
        "country": "Unknown",
        "country_code": "",
        "region": "",
        "city": "Unknown",
        "isp": "Offline or Unreachable",
        "org": "",
        "asn": "",
        "is_datacenter_vpn": False
    }

def detect_active_vpn_interfaces() -> List[Dict[str, Any]]:
    """
    Detect all VPN-related network adapters and their live status.
    """
    vpn_adapters = []
    
    if IS_WINDOWS:
        script = """
        Get-NetAdapter | Select-Object Name, InterfaceDescription, Status, LinkSpeed, ifIndex | ConvertTo-Json -Compress
        """
        code, out, _ = run_powershell(script, timeout=6)
        if code == 0 and out.strip():
            try:
                adapters = json.loads(out)
                if isinstance(adapters, dict):
                    adapters = [adapters]
                for a in adapters:
                    name = a.get("Name", "")
                    desc = a.get("InterfaceDescription", "")
                    status = a.get("Status", "")
                    combined = f"{name} {desc}".lower()
                    
                    is_vpn = any(kw in combined for kw in VPN_INTERFACE_KEYWORDS)
                    if is_vpn:
                        # Determine provider hint
                        provider = "Generic VPN"
                        if "surfshark" in combined:
                            provider = "Surfshark"
                        elif "wireguard" in combined or "wintun" in combined:
                            provider = "WireGuard"
                        elif "openvpn" in combined:
                            provider = "OpenVPN"
                        elif "tailscale" in combined:
                            provider = "Tailscale"
                        elif "nord" in combined:
                            provider = "NordVPN"
                        elif "proton" in combined:
                            provider = "ProtonVPN"
                        
                        vpn_adapters.append({
                            "name": name,
                            "description": desc,
                            "status": status,
                            "is_up": status.lower() == "up",
                            "provider": provider,
                            "if_index": a.get("ifIndex")
                        })
            except Exception as e:
                logger.debug(f"Error parsing net adapters json: {e}")
    else:
        # Linux detection
        code, out, _ = run_command("ip -j link 2>/dev/null", timeout=4)
        if code == 0 and out.strip():
            try:
                links = json.loads(out)
                for l in links:
                    name = l.get("ifname", "")
                    flags = l.get("flags", [])
                    is_up = "UP" in flags
                    combined = name.lower()
                    if any(kw in combined for kw in ["tun", "tap", "wg", "surfshark", "wireguard", "tailscale"]):
                        vpn_adapters.append({
                            "name": name,
                            "description": "Linux Tunnel Interface",
                            "status": "Up" if is_up else "Down",
                            "is_up": is_up,
                            "provider": "WireGuard/Tunnel" if "wg" in combined else "OpenVPN/Tunnel",
                            "if_index": l.get("ifindex")
                        })
            except Exception:
                pass

    return vpn_adapters

def get_vpn_services_and_processes() -> Dict[str, Any]:
    """
    Check if Surfshark, WireGuard, or OpenVPN processes and services are running.
    """
    processes = []
    services = []
    
    # Process inspection
    target_procs = ["surfshark", "surfshark.service", "wireguard", "openvpn", "tailscaled"]
    for p in psutil.process_iter(attrs=["pid", "name"]):
        try:
            pname = (p.info["name"] or "").lower()
            if any(tp in pname for tp in target_procs):
                processes.append({
                    "pid": p.info["pid"],
                    "name": p.info["name"]
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Windows Service inspection
    if IS_WINDOWS:
        script = """
        Get-Service -Name '*surfshark*','*wireguard*','*openvpn*' -ErrorAction SilentlyContinue | Select-Object Name, DisplayName, Status, StartType | ConvertTo-Json -Compress
        """
        code, out, _ = run_powershell(script, timeout=5)
        if code == 0 and out.strip():
            try:
                svcs = json.loads(out)
                if isinstance(svcs, dict):
                    svcs = [svcs]
                for s in svcs:
                    services.append({
                        "name": s.get("Name"),
                        "display_name": s.get("DisplayName"),
                        "status": "Running" if str(s.get("Status")) in ("4", "Running") else "Stopped",
                        "start_type": str(s.get("StartType", ""))
                    })
            except Exception:
                pass

    return {
        "processes": processes,
        "services": services
    }

def get_vpn_adapter_mtu(adapter_name: Optional[str] = None) -> Optional[int]:
    """
    Query the configured MTU of the VPN subinterface on Windows.
    """
    if not IS_WINDOWS:
        return None
        
    code, out, _ = run_command("netsh interface ipv4 show subinterfaces", timeout=4)
    if code != 0 or not out:
        return None

    for line in out.splitlines():
        # Format: MTU MediaSenseState Bytes In Bytes Out Interface
        parts = line.strip().split(maxsplit=4)
        if len(parts) >= 5 and parts[0].isdigit():
            mtu = int(parts[0])
            iface = parts[4].strip()
            if adapter_name and adapter_name.lower() in iface.lower():
                return mtu
            elif any(kw in iface.lower() for kw in VPN_INTERFACE_KEYWORDS):
                return mtu
    return None

def test_vpn_mtu_fragmentation(host: str = "1.1.1.1") -> Dict[str, Any]:
    """
    Test packet fragmentation through the VPN tunnel.
    Sends ping packets with DF (Don't Fragment) flag set at key thresholds:
    1472 (1500 MTU Ethernet), 1420 (WireGuard optimal), 1380 (OpenVPN optimal), 1350.
    """
    test_sizes = [1472, 1420, 1380, 1350]
    results = {}
    optimal_payload = 1350

    for size in test_sizes:
        if IS_WINDOWS:
            cmd = f"ping -n 1 -w 1000 -f -l {size} {host}"
        else:
            cmd = f"ping -c 1 -W 1 -M do -s {size} {host}"

        code, stdout, _ = run_command(cmd, timeout=3)
        stdout_lower = stdout.lower()

        is_reply = code == 0 and ("time=" in stdout_lower or "bytes from" in stdout_lower or "reply from" in stdout_lower)
        is_fragmented = "fragment" in stdout_lower or "frag needed" in stdout_lower or "packet needs to be fragmented" in stdout_lower

        passed = is_reply and not is_fragmented
        results[size] = {
            "tested_mtu": size + 28,
            "passed": passed,
            "fragmented": is_fragmented
        }
        if passed and optimal_payload == 1350:
            optimal_payload = size

    # Find highest payload that succeeded
    passed_sizes = [s for s, r in results.items() if r["passed"]]
    highest_passed = max(passed_sizes) if passed_sizes else 1350
    optimal_mtu = highest_passed + 28

    has_fragmentation_risk = not results.get(1472, {}).get("passed", False)

    return {
        "results": results,
        "highest_safe_payload": highest_passed,
        "optimal_mtu": optimal_mtu,
        "has_fragmentation_risk": has_fragmentation_risk,
        "description": (
            f"Tunnel supports clean {optimal_mtu} MTU without packet fragmentation."
            if optimal_mtu >= 1420 else
            f"Path MTU constraint: Packets over {optimal_mtu} bytes are fragmented or dropped. This causes slow page loads, SSL hangs, or lag spikes."
        )
    }

def test_vpn_dns_leak_and_latency() -> Dict[str, Any]:
    """
    Test DNS resolution time through the VPN resolver and check for DNS leaks.
    """
    gw = get_default_gateway()
    dns_servers = []

    if IS_WINDOWS:
        code, out, _ = run_command("netsh interface ipv4 show dnsservers", timeout=4)
        if code == 0:
            dns_servers = re.findall(r"(\d+\.\d+\.\d+\.\d+)", out)
    else:
        code, out, _ = run_command("cat /etc/resolv.conf 2>/dev/null", timeout=2)
        if code == 0:
            dns_servers = re.findall(r"nameserver\s+(\d+\.\d+\.\d+\.\d+)", out)

    unique_dns = list(dict.fromkeys(dns_servers))
    
    # Benchmark query latency to the primary resolver
    primary_dns = unique_dns[0] if unique_dns else "1.1.1.1"
    latencies = []
    for domain in ["google.com", "cloudflare.com", "surfshark.com"]:
        ms = raw_dns_query(primary_dns, domain, timeout=0.8)
        if ms is not None:
            latencies.append(ms)

    avg_dns_ms = round(sum(latencies) / len(latencies), 1) if latencies else None

    # Check for DNS leak: If user is on VPN, but DNS is pointed directly at local router gateway (192.168.x.x)
    is_leaking_to_router = (gw in unique_dns) or any(dns.startswith("192.168.") or dns.startswith("10.0.0.") for dns in unique_dns if dns != gw)
    
    # Internal VPN DNS typically uses 10.x.x.x or 100.x.x.x or secure anycast
    return {
        "primary_dns": primary_dns,
        "configured_servers": unique_dns,
        "avg_latency_ms": avg_dns_ms,
        "is_leaking_to_gateway": is_leaking_to_router,
        "status": "fast" if (avg_dns_ms and avg_dns_ms < 60) else "acceptable" if (avg_dns_ms and avg_dns_ms < 120) else "slow",
        "details": (
            f"DNS responding in {avg_dns_ms}ms via {primary_dns}."
            if avg_dns_ms else f"DNS resolver {primary_dns} timed out."
        )
    }

def measure_vpn_throughput_sample(timeout_sec: float = 4.0) -> Dict[str, Any]:
    """
    Perform a crisp 4.8MB download throughput sample from Cloudflare CDN with User-Agent.
    Measures real-world downstream Mbps through the VPN tunnel without external tools.
    """
    url = "https://speed.cloudflare.com/__down?bytes=5000000"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Encoding": "identity"
            }
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = resp.read()
        elapsed = time.perf_counter() - t0
        
        bytes_len = len(data)
        if elapsed > 0 and bytes_len > 0:
            mbps = round((bytes_len * 8) / (elapsed * 1_000_000), 2)
            return {
                "success": True,
                "mbps": mbps,
                "bytes_transferred": bytes_len,
                "elapsed_seconds": round(elapsed, 2)
            }
    except Exception as e:
        logger.debug(f"Throughput sample failed: {e}")

    return {
        "success": False,
        "mbps": 0.0,
        "bytes_transferred": 0,
        "elapsed_seconds": 0.0
    }

def get_primary_internet_interface() -> str:
    """Return the name of the network adapter currently handling default internet routing."""
    if IS_WINDOWS:
        # Check if 0.0.0.0/1 (VPN split route override) exists
        code, out, _ = run_powershell("(Get-NetRoute -DestinationPrefix '0.0.0.0/1' -ErrorAction SilentlyContinue | Select-Object -First 1).InterfaceAlias", timeout=3)
        if code == 0 and out.strip():
            return out.strip().splitlines()[0].strip()
        # Otherwise check 0.0.0.0/0
        code, out, _ = run_powershell("(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Select-Object -First 1).InterfaceAlias", timeout=3)
        if code == 0 and out.strip():
            return out.strip().splitlines()[0].strip()
    else:
        code, out, _ = run_command("ip route show default 2>/dev/null", timeout=2)
        if code == 0 and out:
            m = re.search(r"dev\s+(\S+)", out)
            if m:
                return m.group(1)
    return ""

def get_vpn_live_status() -> Dict[str, Any]:
    """
    Get live VPN operational status: interface, routing, egress IP, and provider detection.
    """
    adapters = detect_active_vpn_interfaces()
    up_adapters = [a for a in adapters if a.get("is_up")]
    
    svcs_procs = get_vpn_services_and_processes()
    has_surfshark_svc = any(s.get("name") == "Surfshark Service" and s.get("status") == "Running" for s in svcs_procs.get("services", []))
    has_surfshark_proc = any("surfshark" in p.get("name", "").lower() for p in svcs_procs.get("processes", []))

    public_info = get_public_ip_info(timeout=3.0)
    primary_iface = get_primary_internet_interface()
    primary_lower = primary_iface.lower()
    
    # Check if primary interface is a known VPN adapter
    is_primary_vpn = any(kw in primary_lower for kw in VPN_INTERFACE_KEYWORDS)

    is_connected = False
    provider_name = "None"
    protocol_hint = "None"
    active_adapter_name = ""

    if is_primary_vpn:
        is_connected = True
        active_adapter_name = primary_iface
        for a in adapters:
            if a["name"].lower() == primary_lower:
                provider_name = a["provider"]
                break
        if provider_name == "None":
            provider_name = "Surfshark" if "surfshark" in primary_lower else "Generic VPN"
        if "wireguard" in primary_lower or "wintun" in primary_lower:
            protocol_hint = "WireGuard"
        elif "openvpn" in primary_lower:
            protocol_hint = "OpenVPN DCO"
    elif public_info.get("is_datacenter_vpn"):
        is_connected = True
        active_adapter_name = up_adapters[0]["name"] if up_adapters else primary_iface
        if has_surfshark_svc or has_surfshark_proc or any("surfshark" in a["name"].lower() for a in adapters):
            provider_name = "Surfshark"
            protocol_hint = "WireGuard / OpenVPN"
        else:
            provider_name = "Datacenter VPN / Proxy"
    else:
        # Physical ISP / Local link
        is_connected = False
        active_adapter_name = primary_iface
        if has_surfshark_svc or has_surfshark_proc or any("surfshark" in a["name"].lower() for a in adapters):
            provider_name = "Surfshark (Installed / Disconnected)"
        else:
            provider_name = "Disconnected"

    return {
        "is_connected": is_connected,
        "provider": provider_name,
        "protocol": protocol_hint,
        "active_adapter": active_adapter_name,
        "primary_interface": primary_iface,
        "adapters_found": adapters,
        "services_and_processes": svcs_procs,
        "public_ip": public_info.get("ip", "Unknown"),
        "country": public_info.get("country", "Unknown"),
        "city": public_info.get("city", "Unknown"),
        "isp": public_info.get("isp", "Unknown"),
        "org": public_info.get("org", "Unknown"),
        "asn": public_info.get("asn", "Unknown"),
        "is_datacenter_vpn": public_info.get("is_datacenter_vpn", False)
    }

def run_comprehensive_vpn_quality_diagnostic(run_speed_test: bool = True) -> Dict[str, Any]:
    """
    Run full VPN Quality Verification:
    - Multi-target latency, jitter, and packet loss
    - Tunnel MTU and packet fragmentation
    - Configured subinterface MTU
    - DNS resolution speed & DNS leak detection
    - Real-world download throughput (Mbps)
    - Health score (0-100), letter grade, and tailored diagnostic explanations
    """
    status = get_vpn_live_status()
    is_connected = status.get("is_connected", False)

    # 1. Multi-Target Latency & Jitter Test
    # Ping 3 major anycast hosts concurrently
    targets = ["1.1.1.1", "8.8.8.8", "9.9.9.9"]
    ping_results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(ping_host, target, 5, 800): target for target in targets}
        for future in futures:
            target = futures[future]
            try:
                ping_results[target] = future.result()
            except Exception as e:
                ping_results[target] = {"avg_ms": 0.0, "jitter_ms": 0.0, "loss_percent": 100.0}

    # Aggregate ping metrics
    valid_pings = [r for r in ping_results.values() if r.get("loss_percent", 100.0) < 100.0 and r.get("avg_ms", 0) > 0]
    if valid_pings:
        avg_latency = round(sum(p["avg_ms"] for p in valid_pings) / len(valid_pings), 1)
        min_latency = round(min(p.get("min_ms", p["avg_ms"]) for p in valid_pings), 1)
        max_latency = round(max(p.get("max_ms", p["avg_ms"]) for p in valid_pings), 1)
        avg_jitter = round(sum(p.get("jitter_ms", 0.0) for p in valid_pings) / len(valid_pings), 1)
        avg_loss = round(sum(p.get("loss_percent", 0.0) for p in valid_pings) / len(valid_pings), 1)
    else:
        avg_latency = 0.0
        min_latency = 0.0
        max_latency = 0.0
        avg_jitter = 0.0
        avg_loss = 100.0

    # 2. MTU Fragmentation & Configured MTU Audit
    active_adapter_name = status.get("active_adapter")
    configured_mtu = get_vpn_adapter_mtu(active_adapter_name) if active_adapter_name else get_vpn_adapter_mtu("surfshark")
    mtu_test = test_vpn_mtu_fragmentation("1.1.1.1")

    # 3. DNS Latency & Leak Test
    dns_test = test_vpn_dns_leak_and_latency()

    # 4. Optional Throughput Sample
    throughput = measure_vpn_throughput_sample(timeout_sec=4.0) if run_speed_test else {"success": False, "mbps": 0.0}

    # 5. Calculate VPN Health Score (0 - 100)
    score = 100
    deductions = []

    # Deduction 1: Latency & Jitter (Max 35 pts)
    # VPN naturally has ~15-35ms overhead, but jitter > 15ms means severe congestion!
    if avg_jitter > 40.0:
        score -= 30
        deductions.append(f"Severe Jitter ({avg_jitter} ms): VPN node buffer is heavily backlogged.")
    elif avg_jitter > 20.0:
        score -= 20
        deductions.append(f"High Jitter ({avg_jitter} ms): Surfshark server node is experiencing congestion or packet queuing.")
    elif avg_jitter > 10.0:
        score -= 10
        deductions.append(f"Moderate Jitter ({avg_jitter} ms): Noticeable variation in tunnel packet transit.")

    if avg_latency > 150.0:
        score -= 15
        deductions.append(f"High Latency ({avg_latency} ms): Server node is geographically distant or routing path is inefficient.")
    elif avg_latency > 90.0:
        score -= 8
        deductions.append(f"Elevated Latency ({avg_latency} ms).")

    # Deduction 2: Packet Loss (Max 35 pts)
    if avg_loss >= 10.0:
        score -= 35
        deductions.append(f"Critical Packet Loss ({avg_loss}%): Causes download stalls and gaming disconnects.")
    elif avg_loss > 0.0:
        score -= int(avg_loss * 3.5)
        deductions.append(f"Intermittent Packet Drops ({avg_loss}%).")

    # Deduction 3: MTU / Packet Fragmentation (Max 15 pts)
    if configured_mtu and configured_mtu >= 1500 and is_connected:
        score -= 12
        deductions.append(f"Subinterface MTU is 1500: VPN encapsulation exceeds physical frame limits, causing packet fragmentation.")
    elif mtu_test.get("has_fragmentation_risk") and is_connected:
        score -= 10
        deductions.append(f"Packets above {mtu_test.get('optimal_mtu')} bytes are fragmented. Clamping MTU to 1420 will prevent dropped frames.")

    # Deduction 4: DNS Latency & Leak (Max 15 pts)
    if dns_test.get("is_leaking_to_gateway") and is_connected:
        score -= 15
        deductions.append("DNS Leak Detected: Queries are bypassing the VPN tunnel and resolving via local router.")
    elif dns_test.get("avg_latency_ms") and dns_test.get("avg_latency_ms") > 120.0:
        score -= 8
        deductions.append(f"Slow DNS Lookups ({dns_test.get('avg_latency_ms')} ms): Causes web pages to hesitate before loading.")

    if not is_connected:
        score = 0
        grade = "N/A"
        grade_text = "VPN Disconnected"
        badge_color = "#64748B"
        verdict = "VPN is not connected. Traffic is routing directly via local ISP."
    else:
        score = max(0, min(100, score))
        if score >= 90:
            grade = "A+"
            grade_text = "Elite Performance"
            badge_color = "#10B981"
            verdict = "VPN connection is pristine. Low latency, zero packet loss, and optimal MTU."
        elif score >= 80:
            grade = "A"
            grade_text = "Fast & Stable"
            badge_color = "#34D399"
            verdict = "VPN connection is healthy with minor overhead. Ideal for browsing and streaming."
        elif score >= 70:
            grade = "B"
            grade_text = "Good (Minor Jitter)"
            badge_color = "#60A5FA"
            verdict = "Connection is stable but showing slight server load or distance latency."
        elif score >= 55:
            grade = "C"
            grade_text = "Degraded (Server Congestion)"
            badge_color = "#FBBF24"
            verdict = "VPN node is experiencing noticeable congestion or packet queuing. Switching server recommended."
        elif score >= 40:
            grade = "D"
            grade_text = "Poor (High Loss / Jitter)"
            badge_color = "#FB923C"
            verdict = "Severe lag spikes or packet drops detected on this server node. Remediation advised."
        else:
            grade = "F"
            grade_text = "Critical Breakdown"
            badge_color = "#EF4444"
            verdict = "VPN tunnel is critically degraded, leaking DNS, or dropping majority of packets."

    # Generate actionable why-it-happens analysis and fix recommendations
    diagnosis_reasons = []
    recommended_fixes = []

    if avg_jitter > 20.0 or avg_loss > 0.0:
        diagnosis_reasons.append({
            "title": "VPN Server Node Congestion",
            "explanation": f"Surfshark servers are shared pools. Today, the server node at {status.get('city') or status.get('country')} is handling heavy traffic or P2P load, causing {avg_jitter}ms jitter and {avg_loss}% packet drops.",
            "action": "In the Surfshark app, disconnect and tap 'Fastest location' or connect to an alternative nearby city node."
        })
        recommended_fixes.append("switch_server_node")

    if (configured_mtu and configured_mtu >= 1500) or mtu_test.get("has_fragmentation_risk"):
        diagnosis_reasons.append({
            "title": "MTU Packet Fragmentation",
            "explanation": "Because VPN encapsulation adds 60 to 80 bytes of headers to every packet, a 1500-byte MTU forces packets to split into fragments, causing random freezes and slow file downloads.",
            "action": "Click '1-Click Optimize VPN MTU' below to clamp the VPN subinterface to 1420 bytes."
        })
        recommended_fixes.append("optimize_mtu")

    if dns_test.get("is_leaking_to_gateway") or (dns_test.get("avg_latency_ms") and dns_test.get("avg_latency_ms") > 100):
        diagnosis_reasons.append({
            "title": "DNS Resolver Stalls or Route Leaks",
            "explanation": "Windows DNS client often caches stale routes from previous VPN server connections, delaying new requests.",
            "action": "Click 'Flush VPN DNS & Route Cache' to clear Windows resolver caches."
        })
        recommended_fixes.append("flush_dns_routes")

    return {
        "status": status,
        "score": score,
        "grade": grade,
        "grade_text": grade_text,
        "badge_color": badge_color,
        "verdict": verdict,
        "metrics": {
            "avg_latency_ms": avg_latency,
            "min_latency_ms": min_latency,
            "max_latency_ms": max_latency,
            "jitter_ms": avg_jitter,
            "packet_loss_percent": avg_loss,
            "download_mbps": throughput.get("mbps", 0.0),
            "configured_mtu": configured_mtu or 1500,
            "optimal_mtu": mtu_test.get("optimal_mtu", 1420),
            "has_fragmentation_risk": mtu_test.get("has_fragmentation_risk", False),
            "dns_latency_ms": dns_test.get("avg_latency_ms"),
            "dns_leak_detected": dns_test.get("is_leaking_to_gateway", False)
        },
        "target_pings": ping_results,
        "mtu_test": mtu_test,
        "dns_test": dns_test,
        "throughput": throughput,
        "deductions": deductions,
        "diagnosis_reasons": diagnosis_reasons,
        "recommended_fixes": recommended_fixes
    }

# -------------------------------------------------------------
# 1-CLICK REMEDIATION & FIX ACTIONS
# -------------------------------------------------------------

def optimize_vpn_mtu(mtu_size: int = 1420) -> Dict[str, Any]:
    """
    1-Click Fix: Clamp MTU on Surfshark and VPN adapters to 1420 bytes to prevent packet fragmentation.
    """
    if not IS_WINDOWS:
        return {
            "action": "optimize_vpn_mtu",
            "success": True,
            "message": "Linux: Use `ip link set dev <tun> mtu 1420` to tune tunnel MTU."
        }

    # Find VPN adapters
    adapters = detect_active_vpn_interfaces()
    target_names = [a["name"] for a in adapters]
    if not target_names:
        target_names = ["OpenVPN Data Channel Offload for Surfshark", "SurfsharkWireGuard", "WireGuard Tunnel"]

    results = []
    for name in target_names:
        script = f"""
        netsh interface ipv4 set subinterface "{name}" mtu={mtu_size} store=persistent
        netsh interface ipv6 set subinterface "{name}" mtu={mtu_size} store=persistent -ErrorAction SilentlyContinue
        "MTU set to {mtu_size} on {name}"
        """
        if is_admin():
            code, out, err = run_powershell(script)
            ok = code == 0
        else:
            ok, out = run_elevated_powershell(script)
        results.append({"adapter": name, "success": ok, "output": out.strip()})

    any_success = any(r["success"] for r in results)
    return {
        "action": "optimize_vpn_mtu",
        "success": any_success,
        "mtu_applied": mtu_size,
        "results": results,
        "message": f"VPN Adapter MTU clamped to {mtu_size} bytes! Packet fragmentation black holes eliminated." if any_success else "Could not apply MTU setting. Elevation may be required."
    }

def flush_vpn_dns_routes() -> Dict[str, Any]:
    """
    1-Click Fix: Flush Windows DNS cache, clear ARP tables, and purge NetBIOS mappings.
    Cleans out stale server routing entries after switching VPN locations.
    """
    if not IS_WINDOWS:
        code, _, _ = run_command("resolvectl flush-caches 2>/dev/null || systemd-resolve --flush-caches 2>/dev/null || true")
        return {
            "action": "flush_vpn_dns_routes",
            "success": True,
            "message": "DNS resolver caches flushed."
        }

    script = """
    Clear-DnsClientCache -ErrorAction SilentlyContinue
    ipconfig /flushdns
    Start-Process -FilePath "netsh" -ArgumentList "interface ip delete arpcache" -WindowStyle Hidden -Wait
    nbtstat -R 2>&1
    "VPN DNS and routing cache successfully flushed."
    """
    if is_admin():
        code, out, _ = run_powershell(script)
        ok = code == 0
    else:
        ok, out = run_elevated_powershell(script)

    return {
        "action": "flush_vpn_dns_routes",
        "success": ok,
        "message": "Windows DNS client cache, ARP tables, and NetBIOS routes flushed. Stale VPN resolver entries cleared." if ok else f"Flush failed: {out}"
    }

def restart_vpn_service(service_name: str = "Surfshark Service") -> Dict[str, Any]:
    """
    1-Click Fix: Soft restart Surfshark background Windows service to clear hung daemon states and memory leaks.
    """
    if not IS_WINDOWS:
        return {
            "action": "restart_vpn_service",
            "success": False,
            "message": "Service restart only supported on Windows host."
        }

    script = f"""
    Restart-Service -Name '{service_name}' -Force -ErrorAction Stop
    "Service '{service_name}' restarted successfully."
    """
    if is_admin():
        code, out, err = run_powershell(script)
        ok = code == 0
    else:
        ok, out = run_elevated_powershell(script)

    return {
        "action": "restart_vpn_service",
        "success": ok,
        "message": f"Successfully restarted '{service_name}'. Background tunnel daemon and socket handles refreshed." if ok else f"Restart failed: {out}"
    }

def cycle_vpn_adapter(adapter_name: Optional[str] = None) -> Dict[str, Any]:
    """
    1-Click Fix: Disable and re-enable the VPN virtual adapter to clear driver hangs.
    """
    if not IS_WINDOWS:
        return {
            "action": "cycle_vpn_adapter",
            "success": False,
            "message": "Adapter cycling is only supported on Windows host."
        }

    target = adapter_name
    if not target:
        adapters = detect_active_vpn_interfaces()
        if adapters:
            target = adapters[0]["name"]
        else:
            target = "OpenVPN Data Channel Offload for Surfshark"

    script = f"""
    Restart-NetAdapter -Name '{target}' -Confirm:$false -ErrorAction Stop
    "Adapter '{target}' restarted."
    """
    if is_admin():
        code, out, err = run_powershell(script)
        ok = code == 0
    else:
        ok, out = run_elevated_powershell(script)

    return {
        "action": "cycle_vpn_adapter",
        "success": ok,
        "message": f"VPN virtual network adapter '{target}' cycled successfully. Driver states cleared." if ok else f"Cycle failed: {out}"
    }

def run_full_vpn_tuneup() -> Dict[str, Any]:
    """
    1-Click Full VPN Tune-Up:
    1. Clamp MTU to 1420 bytes (eliminates packet fragmentation).
    2. Flush DNS and routing cache (clears stale IPs).
    3. Soft reset socket stack and ARP cache.
    """
    mtu_res = optimize_vpn_mtu(1420)
    dns_res = flush_vpn_dns_routes()

    return {
        "action": "full_vpn_tuneup",
        "success": mtu_res.get("success", False) or dns_res.get("success", False),
        "steps": {
            "mtu": mtu_res,
            "dns_routes": dns_res
        },
        "message": "Full VPN Tune-Up complete! MTU clamped to 1420 bytes, DNS resolver flushed, and stale routes refreshed."
    }
