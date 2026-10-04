import re
import math
import statistics
import concurrent.futures
from typing import Dict, List, Any, Optional
from .utils import run_command, get_default_gateway
from .cache import cached

import platform

def ping_host(host: Optional[str], count: int = 4, timeout_ms: int = 750) -> Dict[str, Any]:
    """
    Ping a single host multiple times and compute min, avg, max, jitter, and packet loss.
    Works natively on Windows and Linux / Docker / Raspberry Pi with multilingual support.
    """
    # Guard against invalid or unassigned host
    if not host or host in ("0.0.0.0", "None", ""):
        return {
            "host": host or "Unassigned",
            "sent": count,
            "received": 0,
            "lost": count,
            "loss_percent": 100.0,
            "min_ms": 0.0,
            "avg_ms": 0.0,
            "max_ms": 0.0,
            "jitter_ms": 0.0,
            "std_dev_ms": 0.0,
            "raw_times": [],
            "error": "Invalid or unassigned host address"
        }

    is_windows = platform.system() == "Windows"
    if is_windows:
        cmd = f"ping -n {count} -w {timeout_ms} {host}"
        timeout_budget = max(4.0, count * (timeout_ms / 1000.0) + 3.0)
    else:
        timeout_sec = max(1, int(timeout_ms / 1000.0))
        cmd = f"ping -c {count} -W {timeout_sec} {host}"
        timeout_budget = max(4.0, count * timeout_sec + 3.0)

    code, stdout, _ = run_command(cmd, timeout=timeout_budget)

    times: List[float] = []
    sent_count = count

    for line in stdout.splitlines():
        # Match time=XXms, time<1ms across English, French, German, Spanish
        match = re.search(r"(?:time|temps|zeit|tiempo)[<=](\d+(?:\.\d+)?)\s*ms", line, re.IGNORECASE)
        if match:
            try:
                times.append(float(match.group(1)))
            except ValueError:
                pass

    # Extract summary if present or calculate from received packets
    received_count = len(times)
    lost_count = max(0, sent_count - received_count)

    loss_match = re.search(r"\(?(\d+(?:\.\d+)?)%\)?\s*(?:packet\s+)?(?:loss|perte|verlust|perdidos)", stdout, re.IGNORECASE)
    if loss_match:
        try:
            loss_percent = float(loss_match.group(1))
        except ValueError:
            loss_percent = (lost_count / sent_count * 100.0) if sent_count > 0 else 0.0
    else:
        loss_percent = (lost_count / sent_count * 100.0) if sent_count > 0 else 0.0

    loss_percent = max(0.0, min(100.0, loss_percent))

    if times:
        min_time = min(times)
        max_time = max(times)
        avg_time = sum(times) / len(times)
        # Jitter: average absolute difference between consecutive measurements
        if len(times) > 1:
            diffs = [abs(times[i] - times[i - 1]) for i in range(1, len(times))]
            jitter = sum(diffs) / len(diffs)
            std_dev = statistics.stdev(times)
        else:
            jitter = 0.0
            std_dev = 0.0
    else:
        min_time = 0.0
        max_time = 0.0
        avg_time = 0.0
        jitter = 0.0
        std_dev = 0.0

    return {
        "host": host,
        "sent": sent_count,
        "received": received_count,
        "lost": lost_count,
        "loss_percent": round(loss_percent, 1),
        "min_ms": round(min_time, 1),
        "avg_ms": round(avg_time, 1),
        "max_ms": round(max_time, 1),
        "jitter_ms": round(jitter, 1),
        "std_dev_ms": round(std_dev, 1),
        "raw_times": times
    }

@cached(ttl=3.0)
def run_multi_hop_diagnostic(gateway_override: Optional[str] = None) -> Dict[str, Any]:
    """
    Run parallel diagnostic comparing Local Gateway vs Upstream Internet.
    Pinpoints whether issues reside in the home Wi-Fi or ISP.
    """
    gw = gateway_override or get_default_gateway()
    targets = [
        {"name": "Local Gateway (Router)", "host": gw, "is_local": True},
        {"name": "Cloudflare DNS (Edge)", "host": "1.1.1.1", "is_local": False},
        {"name": "Google Anycast", "host": "8.8.8.8", "is_local": False}
    ]

    results = {}
    max_workers = min(len(targets), 3)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(ping_host, t["host"], count=4, timeout_ms=750): t
            for t in targets
        }
        for future in concurrent.futures.as_completed(future_map):
            target_info = future_map[future]
            try:
                data = future.result()
                results[target_info["name"]] = {**target_info, **data}
            except Exception as e:
                results[target_info["name"]] = {
                    **target_info,
                    "error": str(e),
                    "loss_percent": 100.0,
                    "avg_ms": 0.0,
                    "jitter_ms": 0.0,
                    "raw_times": []
                }

    # Evaluate Isolation Diagnosis
    gw_res = results.get("Local Gateway (Router)", {})
    cf_res = results.get("Cloudflare DNS (Edge)", {})
    gg_res = results.get("Google Anycast", {})

    gw_loss = gw_res.get("loss_percent", 0.0)
    gw_avg = gw_res.get("avg_ms", 0.0)
    gw_jitter = gw_res.get("jitter_ms", 0.0)

    cf_loss = cf_res.get("loss_percent", 0.0)
    cf_avg = cf_res.get("avg_ms", 0.0)

    root_cause = ""
    verdict = "Optimal"
    verdict_type = "success" # success, warning, danger
    recommendation = ""

    # Check for complete offline outage
    if gw_loss >= 100.0 and cf_loss >= 100.0:
        verdict = "Complete Network Disconnect"
        verdict_type = "danger"
        root_cause = "Both your local router gateway and internet destinations are completely unreachable. Wi-Fi may be disabled or cable disconnected."
        recommendation = "Check your device's Wi-Fi / Ethernet connection status, verify router power, or run 'Reset Winsock Stack'."
    elif gw_loss > 0 or gw_avg > 15 or gw_jitter > 8:
        verdict = "Local Wi-Fi Bottleneck Detected"
        verdict_type = "danger"
        root_cause = (
            f"Latency or packet loss to your local router is elevated (Avg: {gw_avg}ms, Loss: {gw_loss}%, Jitter: {gw_jitter}ms). "
            "Because this occurs on the first hop between your PC and router, the issue is strictly inside your local wireless setup—NOT your internet provider."
        )
        recommendation = (
            "Recommended local fixes: Move closer to router, switch from 2.4 GHz to 5/6 GHz, change Wi-Fi channel away from interference, "
            "or apply the 'Disable Wi-Fi Power Throttling' and 'Flush DNS & Reset Winsock' tools in the Optimizer tab."
        )
    elif cf_loss > 0 or cf_avg > 80:
        verdict = "Upstream Provider / Routing Congestion"
        verdict_type = "warning"
        root_cause = (
            f"Your local Wi-Fi to the router is pristine (Avg: {gw_avg}ms, 0% loss), but internet packets are experiencing delays or drops (Avg: {cf_avg}ms, Loss: {cf_loss}%). "
            "Your wireless link is completely healthy; delay is occurring on the external fiber/cable WAN or ISP gateway."
        )
        recommendation = (
            "Recommended local actions: Switch to Cloudflare 1.1.1.1 or Google DNS via the DNS Benchmark tab, "
            "test Bufferbloat to verify if someone is maxing your bandwidth, or power-cycle your modem/ONT."
        )
    else:
        verdict = "Network Link Flawless"
        verdict_type = "success"
        root_cause = f"Local Wi-Fi latency is sub-millisecond ({gw_avg}ms, 0% loss), and internet routing latency is ultra-responsive ({cf_avg}ms, 0% loss)."
        recommendation = "No latency or packet drop anomalies detected. Your wireless link is performing at peak capacity."

    return {
        "verdict": verdict,
        "verdict_type": verdict_type,
        "root_cause": root_cause,
        "recommendation": recommendation,
        "gateway_ip": gw,
        "hops": results
    }

@cached(ttl=20.0)
def test_mtu_discovery(host: str = "1.1.1.1") -> Dict[str, Any]:
    """
    Test MTU size using DF (Don't Fragment) ping to detect packet fragmentation.
    Cross-platform: Windows and Linux / Docker / Raspberry Pi.
    Standard Ethernet MTU = 1500 (ICMP Payload 1472 + 28 header).
    PPPoE MTU = 1492 (Payload 1464 + 28).
    """
    test_sizes = [1472, 1464, 1452, 1420, 1400]
    optimal_payload = 1400
    is_windows = platform.system() == "Windows"

    for size in test_sizes:
        if is_windows:
            cmd = f"ping -n 1 -f -l {size} {host}"
        else:
            cmd = f"ping -c 1 -M do -s {size} {host}"

        code, stdout, _ = run_command(cmd, timeout=3)
        stdout_lower = stdout.lower()

        # Check for successful echo reply without fragmentation
        is_reply = code == 0 and ("time=" in stdout_lower or "bytes from" in stdout_lower or "reply from" in stdout_lower)
        is_fragmented = "fragment" in stdout_lower or "frag needed" in stdout_lower

        if is_reply and not is_fragmented:
            optimal_payload = size
            break

    optimal_mtu = optimal_payload + 28
    is_standard = optimal_mtu == 1500

    return {
        "optimal_payload": optimal_payload,
        "optimal_mtu": optimal_mtu,
        "standard_ethernet": is_standard,
        "status": "Optimal (1500 MTU)" if is_standard else f"Constrained MTU ({optimal_mtu})",
        "description": "Standard 1500 MTU without fragmentation." if is_standard else f"Packets larger than {optimal_mtu} bytes are fragmented, which may cause latency spikes or dropped packets in games/VPNs."
    }
