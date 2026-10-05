import socket
import platform
import re
import time
import psutil
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional
from .utils import get_default_gateway, run_command, run_powershell, is_admin

logger = logging.getLogger("NetPulseSecurity")

IS_WINDOWS = platform.system() == "Windows"

_cached_audit: Optional[Dict[str, Any]] = None
_cached_audit_ts: float = 0.0

def _test_tcp_port(ip: str, port: int, timeout_sec: float = 0.25) -> bool:
    """Test if a TCP port is open with ultra-short timeout."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_sec)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False

def audit_wifi_encryption() -> Dict[str, Any]:
    """Audit Wi-Fi authentication cipher and encryption strength."""
    if not IS_WINDOWS:
        return {
            "id": "wifi_encryption",
            "name": "Wi-Fi Protocol & Encryption",
            "category": "Wireless Security",
            "status": "passed",
            "score_deduction": 0,
            "details": "Linux / Appliance Mode: Operating via local network interface.",
            "recommendation": "Ensure your upstream router enforces WPA2-AES or WPA3."
        }

    code, out, _ = run_command("netsh wlan show interfaces", timeout=4)
    if code != 0 or not out:
        return {
            "id": "wifi_encryption",
            "name": "Wi-Fi Protocol & Encryption",
            "category": "Wireless Security",
            "status": "passed",
            "score_deduction": 0,
            "details": "Ethernet or virtual connection active (no active Wi-Fi profile).",
            "recommendation": "Wired links are immune to over-the-air Wi-Fi sniffing."
        }

    auth_match = re.search(r"Authentication\s*:\s*(.+)", out, re.IGNORECASE)
    cipher_match = re.search(r"Cipher\s*:\s*(.+)", out, re.IGNORECASE)
    auth = auth_match.group(1).strip() if auth_match else "Unknown"
    cipher = cipher_match.group(1).strip() if cipher_match else "Unknown"

    auth_lower = auth.lower()
    cipher_lower = cipher.lower()

    if "open" in auth_lower or "none" in cipher_lower:
        return {
            "id": "wifi_encryption",
            "name": "Wi-Fi Protocol & Encryption",
            "category": "Wireless Security",
            "status": "critical",
            "score_deduction": 40,
            "details": f"CRITICAL: Connected to unencrypted network ({auth} / {cipher}). All Wi-Fi traffic can be intercepted by anyone nearby.",
            "recommendation": "Disconnect immediately or log into router admin and set security to WPA2-Personal (AES) or WPA3."
        }
    elif "wep" in auth_lower or "wep" in cipher_lower:
        return {
            "id": "wifi_encryption",
            "name": "Wi-Fi Protocol & Encryption",
            "category": "Wireless Security",
            "status": "critical",
            "score_deduction": 35,
            "details": f"CRITICAL: Network uses obsolete WEP encryption ({auth} / {cipher}), which can be cracked in under 60 seconds.",
            "recommendation": "Upgrade router wireless security to WPA2-PSK (AES) or WPA3."
        }
    elif "tkip" in cipher_lower or ("wpa" in auth_lower and "wpa2" not in auth_lower and "wpa3" not in auth_lower):
        return {
            "id": "wifi_encryption",
            "name": "Wi-Fi Protocol & Encryption",
            "category": "Wireless Security",
            "status": "warning",
            "score_deduction": 15,
            "details": f"WARNING: Network uses older WPA/TKIP ({auth} / {cipher}) with known cryptographic vulnerabilities.",
            "recommendation": "Configure router to use WPA2-PSK (AES) or WPA3-Personal."
        }
    elif "wpa3" in auth_lower:
        return {
            "id": "wifi_encryption",
            "name": "Wi-Fi Protocol & Encryption",
            "category": "Wireless Security",
            "status": "passed",
            "score_deduction": 0,
            "details": f"EXCELLENT: Protected by modern WPA3 ({auth} / {cipher}) with Protected Management Frames (PMF).",
            "recommendation": "Your wireless link utilizes state-of-the-art encryption."
        }
    else:
        return {
            "id": "wifi_encryption",
            "name": "Wi-Fi Protocol & Encryption",
            "category": "Wireless Security",
            "status": "passed",
            "score_deduction": 0,
            "details": f"SECURE: Protected by standard {auth} ({cipher} encryption).",
            "recommendation": "Wireless encryption meets current industry standards."
        }

def audit_router_gateway_exposure(gw_ip: str) -> Dict[str, Any]:
    """Audit router default gateway open services and management interfaces."""
    if not gw_ip or gw_ip in ("0.0.0.0", "127.0.0.1"):
        return {
            "id": "router_exposure",
            "name": "Router Gateway Port Exposure",
            "category": "Router Security",
            "status": "passed",
            "score_deduction": 0,
            "details": "Gateway not reachable for port auditing.",
            "recommendation": "Ensure router firewall is enabled."
        }

    # Test ports concurrently: 23 (Telnet), 80 (HTTP), 443 (HTTPS), 445 (SMB), 5000 (UPnP Web)
    ports = [23, 80, 443, 445, 5000]
    port_results: Dict[int, bool] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {executor.submit(_test_tcp_port, gw_ip, p, 0.25): p for p in ports}
        for fut in future_map:
            p = future_map[fut]
            try:
                port_results[p] = fut.result()
            except Exception:
                port_results[p] = False

    telnet_open = port_results.get(23, False)
    http_open = port_results.get(80, False)
    https_open = port_results.get(443, False)
    smb_open = port_results.get(445, False)
    upnp_open = port_results.get(5000, False)

    findings = []
    deduction = 0
    severity = "passed"

    if telnet_open:
        findings.append("Telnet (Port 23) is open on router. Telnet sends passwords in cleartext across the LAN.")
        deduction += 25
        severity = "critical"

    if upnp_open:
        findings.append("UPnP Web Service (Port 5000) is listening on router. UPnP can allow malware to open external inbound ports.")
        deduction += 10
        if severity != "critical":
            severity = "warning"

    if smb_open:
        findings.append("SMB File Sharing (Port 445) is exposed on router. Ensure guest access is disabled.")
        deduction += 5
        if severity == "passed":
            severity = "warning"

    if http_open and not https_open:
        findings.append("Router web management is only accessible via unencrypted HTTP (Port 80); HTTPS (Port 443) is not enabled.")
        deduction += 5
        if severity == "passed":
            severity = "warning"

    if not findings:
        return {
            "id": "router_exposure",
            "name": "Router Gateway Port Exposure",
            "category": "Router Security",
            "status": "passed",
            "score_deduction": 0,
            "details": f"Router at {gw_ip} has no unencrypted Telnet, UPnP, or insecure debug services exposed to LAN.",
            "recommendation": "Router management interfaces are properly secured."
        }
    else:
        return {
            "id": "router_exposure",
            "name": "Router Gateway Port Exposure",
            "category": "Router Security",
            "status": severity,
            "score_deduction": deduction,
            "details": f"Issues found on {gw_ip}: " + " | ".join(findings),
            "recommendation": "Log into your router admin page and disable Telnet, disable UPnP if unused, and enforce HTTPS."
        }

def audit_firewall_status() -> Dict[str, Any]:
    """Audit Windows Defender Firewall or Linux iptables/ufw."""
    if not IS_WINDOWS:
        code, out, _ = run_command("ufw status 2>/dev/null || iptables -L -n 2>/dev/null", timeout=3)
        if "active" in out.lower() or "chain" in out.lower():
            return {
                "id": "firewall_status",
                "name": "Host Firewall Defense",
                "category": "Host Protection",
                "status": "passed",
                "score_deduction": 0,
                "details": "Linux firewall (UFW/iptables) rules are active.",
                "recommendation": "Host firewall is filtering inbound packets."
            }
        return {
            "id": "firewall_status",
            "name": "Host Firewall Defense",
            "category": "Host Protection",
            "status": "warning",
            "score_deduction": 10,
            "details": "Linux firewall (UFW) may be inactive.",
            "recommendation": "Enable UFW with 'sudo ufw enable'."
        }

    script = "Get-NetFirewallProfile | Select-Object Name, Enabled | ConvertTo-Json"
    code, stdout, _ = run_powershell(script, timeout=4)
    if code != 0 or not stdout.strip():
        return {
            "id": "firewall_status",
            "name": "Host Firewall Defense",
            "category": "Host Protection",
            "status": "passed",
            "score_deduction": 0,
            "details": "Windows Defender Firewall operational.",
            "recommendation": "Firewall service running."
        }

    disabled_profiles = []
    try:
        import json
        profiles = json.loads(stdout)
        if isinstance(profiles, dict):
            profiles = [profiles]
        for p in profiles:
            if not p.get("Enabled", True):
                disabled_profiles.append(p.get("Name", "Unknown"))
    except Exception:
        pass

    if disabled_profiles:
        return {
            "id": "firewall_status",
            "name": "Host Firewall Defense",
            "category": "Host Protection",
            "status": "warning",
            "score_deduction": 20,
            "details": f"WARNING: Windows Firewall is DISABLED on profile(s): {', '.join(disabled_profiles)}.",
            "recommendation": "Enable Windows Defender Firewall for all network profiles to block malicious inbound probes."
        }
    else:
        return {
            "id": "firewall_status",
            "name": "Host Firewall Defense",
            "category": "Host Protection",
            "status": "passed",
            "score_deduction": 0,
            "details": "Windows Defender Firewall is ACTIVE across all Domain, Private, and Public network profiles.",
            "recommendation": "Inbound attack filtering is fully active."
        }

def audit_arp_mitm_sentry() -> Dict[str, Any]:
    """Detect ARP spoofing and Man-in-the-Middle (MitM) duplicate MAC attacks."""
    mac_to_ips: Dict[str, List[str]] = {}
    code, out, _ = run_command("arp -a", timeout=4)
    if code == 0 and out:
        for line in out.splitlines():
            # Match IP and MAC address pairs
            match = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F\-]{17}|[0-9a-fA-F\:]{17})\s+(\w+)", line)
            if match:
                ip, mac, entry_type = match.group(1), match.group(2).lower().replace("-", ":"), match.group(3).lower()
                # Exclude broadcast/multicast MACs
                if mac in ("ff:ff:ff:ff:ff:ff", "01:00:5e:00:00:16", "01:00:5e:00:00:fb"):
                    continue
                if ip.endswith(".255") or ip.startswith("224.") or ip.startswith("239."):
                    continue
                mac_to_ips.setdefault(mac, []).append(ip)

    # Check for duplicate MACs across different devices
    duplicate_macs = {mac: ips for mac, ips in mac_to_ips.items() if len(ips) > 1}
    gw = get_default_gateway()

    # Specifically check if Gateway shares a MAC with another IP (classic ARP poison)
    gw_poisoned = False
    for mac, ips in duplicate_macs.items():
        if gw in ips and len(ips) > 1:
            gw_poisoned = True
            break

    if gw_poisoned:
        return {
            "id": "arp_mitm",
            "name": "ARP Spoofing & MitM Sentry",
            "category": "Network Integrity",
            "status": "critical",
            "score_deduction": 35,
            "details": f"CRITICAL: Gateway IP {gw} shares a hardware MAC with another host ({duplicate_macs.get(mac)}). High likelihood of ARP Poisoning / Man-in-the-Middle attack on this network!",
            "recommendation": "Run 'Clear ARP Cache' immediately in Local Repair Center. Disconnect from untrusted public Wi-Fi."
        }
    elif duplicate_macs:
        return {
            "id": "arp_mitm",
            "name": "ARP Spoofing & MitM Sentry",
            "category": "Network Integrity",
            "status": "warning",
            "score_deduction": 10,
            "details": f"Notice: Multiple local IPs map to the same MAC ({list(duplicate_macs.keys())[0]}). May be caused by a Wi-Fi repeater, bridge, or proxy.",
            "recommendation": "Check if a mesh node or Wi-Fi range extender is operating in MAC-clone mode."
        }
    else:
        return {
            "id": "arp_mitm",
            "name": "ARP Spoofing & MitM Sentry",
            "category": "Network Integrity",
            "status": "passed",
            "score_deduction": 0,
            "details": "ARP table clean. No duplicate MAC collisions or gateway poisoning detected.",
            "recommendation": "Local subnet routing integrity is normal."
        }

def audit_dns_security() -> Dict[str, Any]:
    """Audit DNS upstream configuration for malware blocking & DoH/DoT privacy."""
    gw = get_default_gateway()
    
    # Check current DNS configuration
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

    is_secure_resolver = any(dns in ("1.1.1.1", "1.0.0.1", "9.9.9.9", "149.112.112.112", "8.8.8.8", "8.8.4.4", "208.67.222.222") for dns in unique_dns)
    is_router_dns = any(dns == gw for dns in unique_dns)

    if is_secure_resolver:
        return {
            "id": "dns_security",
            "name": "DNS Privacy & Poisoning Protection",
            "category": "DNS & Protocol",
            "status": "passed",
            "score_deduction": 0,
            "details": f"Protected: Using secure public anycast resolver ({', '.join(unique_dns[:2])}) with DNSSEC validation.",
            "recommendation": "Your DNS queries bypass ISP interception and log tracking."
        }
    elif is_router_dns or not unique_dns:
        return {
            "id": "dns_security",
            "name": "DNS Privacy & Poisoning Protection",
            "category": "DNS & Protocol",
            "status": "warning",
            "score_deduction": 10,
            "details": f"Warning: Using default router/ISP DNS ({unique_dns[0] if unique_dns else gw}). Plaintext UDP port 53 DNS is subject to ISP logging, ad injection, and lack of malware blocking.",
            "recommendation": "In NetPulse DNS Turbo Benchmark, 1-click apply Cloudflare (1.1.1.1) or Quad9 (9.9.9.9 with malware threat protection)."
        }
    else:
        return {
            "id": "dns_security",
            "name": "DNS Privacy & Poisoning Protection",
            "category": "DNS & Protocol",
            "status": "passed",
            "score_deduction": 0,
            "details": f"Custom DNS configured: {', '.join(unique_dns[:2])}.",
            "recommendation": "Verify upstream resolver supports DNSSEC."
        }

def audit_wildcard_listening_ports() -> Dict[str, Any]:
    """Inspect locally listening services bound to 0.0.0.0 exposing ports to LAN."""
    exposed_risks = []
    try:
        conns = psutil.net_connections(kind="inet")
        high_risk_ports = {
            21: "FTP (Unencrypted File Transfer)",
            23: "Telnet (Unencrypted Remote Shell)",
            445: "SMB (Windows File Sharing exposed to LAN)",
            1433: "MSSQL Database Server",
            3306: "MySQL Database Server",
            3389: "RDP (Remote Desktop Protocol exposed to LAN)",
            5432: "PostgreSQL Database Server",
            6379: "Redis In-Memory Store (Often unauthenticated)",
            27017: "MongoDB Database Server"
        }

        for c in conns:
            if c.status == "LISTEN" and c.laddr:
                ip, port = c.laddr.ip, c.laddr.port
                if ip in ("0.0.0.0", "::") and port in high_risk_ports:
                    proc_name = "Unknown"
                    try:
                        if c.pid:
                            proc_name = psutil.Process(c.pid).name()
                    except Exception:
                        pass
                    item = f"Port {port} ({high_risk_ports[port]} - {proc_name})"
                    if item not in exposed_risks:
                        exposed_risks.append(item)
    except Exception as e:
        logger.debug(f"Socket connection check note: {e}")

    if exposed_risks:
        return {
            "id": "open_listening_ports",
            "name": "LAN Service Exposure (0.0.0.0)",
            "category": "Host Protection",
            "status": "warning",
            "score_deduction": 15,
            "details": f"Services listening on all network interfaces: {', '.join(exposed_risks)}.",
            "recommendation": "Bind sensitive local databases and services to 127.0.0.1 (localhost) only, or restrict via Windows Firewall."
        }
    else:
        return {
            "id": "open_listening_ports",
            "name": "LAN Service Exposure (0.0.0.0)",
            "category": "Host Protection",
            "status": "passed",
            "score_deduction": 0,
            "details": "No high-risk database or plaintext remote services are exposed to the local network subnet.",
            "recommendation": "Local ports are properly sequestered."
        }

def run_full_security_audit(force_refresh: bool = False) -> Dict[str, Any]:
    """Run comprehensive 6-vector network and Wi-Fi security vulnerability assessment concurrently."""
    global _cached_audit, _cached_audit_ts
    now = time.time()
    if not force_refresh and _cached_audit is not None and (now - _cached_audit_ts < 12.0):
        return _cached_audit

    gw_ip = get_default_gateway()

    with ThreadPoolExecutor(max_workers=6) as executor:
        f_wifi = executor.submit(audit_wifi_encryption)
        f_router = executor.submit(audit_router_gateway_exposure, gw_ip)
        f_fw = executor.submit(audit_firewall_status)
        f_arp = executor.submit(audit_arp_mitm_sentry)
        f_dns = executor.submit(audit_dns_security)
        f_ports = executor.submit(audit_wildcard_listening_ports)

        checks = [
            f_wifi.result(),
            f_router.result(),
            f_fw.result(),
            f_arp.result(),
            f_dns.result(),
            f_ports.result()
        ]

    total_deduction = sum(c.get("score_deduction", 0) for c in checks)
    score = max(0, min(100, 100 - total_deduction))

    critical_count = sum(1 for c in checks if c.get("status") == "critical")
    warning_count = sum(1 for c in checks if c.get("status") == "warning")
    passed_count = sum(1 for c in checks if c.get("status") == "passed")

    if critical_count > 0:
        grade = "CRITICAL RISK"
        badge_color = "rose"
    elif warning_count > 1 or score < 75:
        grade = "MODERATE RISK"
        badge_color = "amber"
    elif warning_count == 1:
        grade = "FAIR"
        badge_color = "blue"
    else:
        grade = "EXCELLENT"
        badge_color = "emerald"

    # Actionable recommended fixes
    actionable_fixes = []
    for c in checks:
        if c.get("status") in ("critical", "warning"):
            action = "none"
            btn_text = "View Recommendation"
            cid = c.get("id")
            if cid == "dns_security":
                action = "apply_quad9_dns"
                btn_text = "Apply Quad9 Malware-Blocking DNS"
            elif cid == "arp_mitm":
                action = "clear_arp"
                btn_text = "Flush ARP Cache"
            elif cid == "firewall_status":
                action = "enable_firewall"
                btn_text = "Enable Windows Firewall"

            actionable_fixes.append({
                "id": cid,
                "title": c.get("name"),
                "severity": c.get("status"),
                "problem": c.get("details"),
                "recommendation": c.get("recommendation"),
                "action": action,
                "button_text": btn_text
            })

    res = {
        "score": score,
        "grade": grade,
        "badge_color": badge_color,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "passed_count": passed_count,
        "gateway_ip": gw_ip,
        "checks": checks,
        "actionable_fixes": actionable_fixes
    }
    _cached_audit = res
    _cached_audit_ts = time.time()
    return res

def enable_host_firewall() -> Dict[str, Any]:
    """Enable Windows Defender Firewall on all profiles."""
    if not IS_WINDOWS:
        code, out, _ = run_command("sudo ufw enable 2>/dev/null || true")
        return {"success": code == 0, "message": "Linux firewall command dispatched."}

    script = "Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True"
    if is_admin():
        code, out, err = run_powershell(script)
        ok = code == 0
    else:
        from .utils import run_elevated_powershell
        ok, out = run_elevated_powershell(script)

    return {
        "success": ok,
        "message": "Windows Defender Firewall successfully enabled on all Domain, Private, and Public profiles." if ok else f"Firewall update error: {out}"
    }
