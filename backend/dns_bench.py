import socket
import time
import platform
import concurrent.futures
from typing import Dict, List, Any, Optional
from .utils import run_command, run_powershell, run_elevated_powershell, get_active_wifi_interface
from .cache import cached, system_cache

DNS_PROVIDERS = [
    {
        "id": "cloudflare",
        "name": "Cloudflare DNS",
        "description": "Fastest consumer DNS with zero-logging privacy policy.",
        "primary": "1.1.1.1",
        "secondary": "1.0.0.1"
    },
    {
        "id": "google",
        "name": "Google Public DNS",
        "description": "High-reliability global anycast network with intelligent routing.",
        "primary": "8.8.8.8",
        "secondary": "8.8.4.4"
    },
    {
        "id": "quad9",
        "name": "Quad9 Security DNS",
        "description": "Blocks known malicious domains, phishing, and ransomware automatically.",
        "primary": "9.9.9.9",
        "secondary": "149.112.112.112"
    },
    {
        "id": "opendns",
        "name": "Cisco OpenDNS",
        "description": "Robust enterprise-grade DNS with optional content filtering.",
        "primary": "208.67.222.222",
        "secondary": "208.67.220.220"
    }
]

TEST_DOMAINS = ["google.com", "cloudflare.com", "microsoft.com", "github.com"]

def raw_dns_query(server_ip: str, domain: str, timeout: float = 0.6) -> Optional[float]:
    """
    Send standard UDP DNS query to server_ip for domain and measure round-trip time in ms.
    Includes crisp socket timeout (600ms) and IPv4 format validation.
    """
    if not server_ip:
        return None

    # Validate IPv4 format
    try:
        socket.inet_aton(server_ip)
    except socket.error:
        # Not a valid IPv4 address (e.g. IPv6 or hostname)
        return None

    header = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
    qname = b""
    for part in domain.split("."):
        if part:
            qname += bytes([len(part)]) + part.encode("ascii", errors="replace")
    qname += b"\x00"
    qtype_qclass = b"\x00\x01\x00\x01" # Type A, Class IN
    packet = header + qname + qtype_qclass

    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        t0 = time.perf_counter()
        sock.sendto(packet, (server_ip, 53))
        sock.recvfrom(512)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return round(elapsed_ms, 1)
    except Exception:
        return None
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass

def benchmark_single_dns(provider: Dict[str, Any]) -> Dict[str, Any]:
    """Test a single DNS provider across multiple test domains with early exit on unresponsive resolvers."""
    ip = provider.get("primary", "")
    times: List[float] = []
    consecutive_fails = 0

    for domain in TEST_DOMAINS:
        ms = raw_dns_query(ip, domain, timeout=0.6)
        if ms is not None:
            times.append(ms)
            consecutive_fails = 0
        else:
            consecutive_fails += 1
            # If 2 consecutive queries fail, provider is unreachable; exit early to save time
            if consecutive_fails >= 2:
                break

    if times:
        avg_ms = round(sum(times) / len(times), 1)
        min_ms = round(min(times), 1)
        success_rate = round((len(times) / len(TEST_DOMAINS)) * 100, 0)
    else:
        avg_ms = 999.0
        min_ms = 999.0
        success_rate = 0.0

    return {
        **provider,
        "avg_ms": avg_ms,
        "min_ms": min_ms,
        "success_rate": success_rate,
        "responsive": success_rate > 0
    }

@cached(ttl=10.0)
def run_dns_benchmark() -> Dict[str, Any]:
    """Benchmark all DNS providers in parallel with bounded worker pool and rank them."""
    # Also include the current system DNS
    iface = get_active_wifi_interface()
    current_dns_raw = iface.get("DNS", "")
    current_dns_ip = current_dns_raw.split(",")[0].strip() if current_dns_raw else ""

    providers_to_test = list(DNS_PROVIDERS)
    known_ips = ["1.1.1.1", "8.8.8.8", "9.9.9.9", "208.67.222.222"]

    if current_dns_ip and current_dns_ip not in known_ips:
        try:
            socket.inet_aton(current_dns_ip)
            providers_to_test.append({
                "id": "current",
                "name": f"Current System DNS ({current_dns_ip})",
                "description": "Your current configured DNS server (assigned by your router/ISP).",
                "primary": current_dns_ip,
                "secondary": ""
            })
        except socket.error:
            pass

    results = []
    pool_size = min(len(providers_to_test), 5)
    with concurrent.futures.ThreadPoolExecutor(max_workers=pool_size) as executor:
        futures = [executor.submit(benchmark_single_dns, p) for p in providers_to_test]
        for f in concurrent.futures.as_completed(futures):
            try:
                results.append(f.result())
            except Exception:
                pass

    # Sort by responsiveness and avg_ms
    results.sort(key=lambda x: (0 if x["responsive"] else 1, x["avg_ms"]))

    fastest = results[0] if results and results[0]["responsive"] else None

    return {
        "ranked_providers": results,
        "fastest": fastest,
        "current_configured_dns": current_dns_raw,
        "recommendation": f"Switching to {fastest['name']} ({fastest['avg_ms']}ms) will optimize web browsing speed and latency." if fastest else "DNS benchmark complete."
    }

def apply_adapter_dns(primary: str, secondary: str = "", interface_name: str = "Wi-Fi") -> Dict[str, Any]:
    """Apply DNS servers to the specified network adapter across Windows and Linux."""
    # Invalidate cached DNS benchmark and adapter data
    run_dns_benchmark.invalidate()
    system_cache.invalidate_prefix("get_active_wifi_interface")

    is_windows = platform.system() == "Windows"

    if not is_windows:
        # Linux / Docker
        if not primary:
            return {"success": True, "message": "DNS reset to automatic (DHCP) on Linux."}
        # In Linux/Docker, update /etc/resolv.conf if possible
        try:
            with open("/etc/resolv.conf", "w") as f:
                f.write(f"nameserver {primary}\n")
                if secondary:
                    f.write(f"nameserver {secondary}\n")
            return {"success": True, "message": f"Successfully updated /etc/resolv.conf with {primary}" + (f", {secondary}" if secondary else "")}
        except Exception as e:
            return {"success": False, "message": f"Could not write to /etc/resolv.conf: {e}"}

    # Windows implementation
    if not primary:
        # Reset to DHCP
        script = f"Set-DnsClientServerAddress -InterfaceAlias '{interface_name}' -ResetServerAddresses -ErrorAction SilentlyContinue"
        ok, msg = run_elevated_powershell(script)
        run_powershell("Clear-DnsClientCache; ipconfig /flushdns")
        return {"success": ok, "message": "DNS reset to automatic (DHCP)" if ok else f"Failed: {msg}"}

    servers = f"'{primary}'"
    if secondary:
        servers += f", '{secondary}'"

    script = f"Set-DnsClientServerAddress -InterfaceAlias '{interface_name}' -ServerAddresses @({servers}) -ErrorAction SilentlyContinue"
    ok, msg = run_elevated_powershell(script)
    run_powershell("Clear-DnsClientCache; ipconfig /flushdns")
    return {
        "success": ok,
        "message": f"Successfully configured DNS to {primary}" + (f", {secondary}" if secondary else "") if ok else f"Failed to set DNS: {msg}"
    }
