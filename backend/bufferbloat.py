import time
import urllib.request
import threading
from typing import Dict, List, Any
from .ping_analyzer import ping_host
from .utils import get_default_gateway

def run_bufferbloat_test() -> Dict[str, Any]:
    """
    Test unloaded latency vs loaded latency (bufferbloat) and estimate download speed.
    Includes timeouts and handles offline or server unreachable edge cases safely.
    """
    target_host = "1.1.1.1"

    # 1. Unloaded baseline ping
    unloaded_res = ping_host(target_host, count=4, timeout_ms=800)
    unloaded_received = unloaded_res.get("received", 0)
    unloaded_avg = unloaded_res.get("avg_ms", 0.0)

    # Edge case: If offline or 1.1.1.1 is unreachable
    if unloaded_received == 0:
        return {
            "grade": "N/A",
            "grade_desc": "Offline - Baseline ping failed. Ensure your internet connection is active.",
            "badge_color": "#94A3B8",
            "unloaded_latency_ms": 0.0,
            "loaded_latency_ms": 0.0,
            "bufferbloat_delta_ms": 0.0,
            "download_speed_mbps": 0.0,
            "downloaded_mb": 0.0,
            "unloaded_times": [],
            "loaded_times": [],
            "recommendation": "Bufferbloat test requires an active internet connection. Check Wi-Fi or router connection."
        }

    # 2. Loaded test: trigger download while collecting pings
    download_bytes = 0
    download_duration = 0.0
    download_error = None
    stop_event = threading.Event()

    def download_worker():
        nonlocal download_bytes, download_duration, download_error
        t_start = time.perf_counter()
        try:
            req = urllib.request.Request(
                "https://speed.cloudflare.com/__down?bytes=25000000",
                headers={"User-Agent": "NetPulse-Diagnostics/1.0"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                chunk_size = 64 * 1024
                while not stop_event.is_set():
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    download_bytes += len(chunk)
            download_duration = max(0.1, time.perf_counter() - t_start)
        except Exception as e:
            download_error = str(e)
            download_duration = max(0.1, time.perf_counter() - t_start)

    dl_thread = threading.Thread(target=download_worker, daemon=True)
    dl_thread.start()

    # Small delay for pipe to fill
    time.sleep(0.3)

    # Measure latency while load is active
    loaded_res = ping_host(target_host, count=5, timeout_ms=1000)
    stop_event.set()
    dl_thread.join(timeout=2.0)

    # Edge case: If download completely failed
    if download_error and download_bytes == 0:
        return {
            "grade": "N/A",
            "grade_desc": f"Download test server unreachable ({download_error}).",
            "badge_color": "#94A3B8",
            "unloaded_latency_ms": unloaded_avg,
            "loaded_latency_ms": unloaded_avg,
            "bufferbloat_delta_ms": 0.0,
            "download_speed_mbps": 0.0,
            "downloaded_mb": 0.0,
            "unloaded_times": unloaded_res.get("raw_times", []),
            "loaded_times": [],
            "recommendation": "Unable to contact Cloudflare speed test server. Verify firewall or DNS configuration."
        }

    loaded_avg = loaded_res.get("avg_ms", unloaded_avg)
    delta_ms = max(0.0, round(loaded_avg - unloaded_avg, 1))

    # Calculate download throughput
    if download_duration > 0 and download_bytes > 0:
        download_speed_mbps = round((download_bytes * 8) / (download_duration * 1_000_000), 2)
    else:
        download_speed_mbps = 0.0

    # Bufferbloat Grade
    if delta_ms <= 6.0:
        grade = "A+"
        grade_desc = "Exceptional - Zero bufferbloat. Latency is unaffected by downloads."
        badge_color = "#10B981"
    elif delta_ms <= 25.0:
        grade = "A"
        grade_desc = "Good - Minimal latency increase under load."
        badge_color = "#34D399"
    elif delta_ms <= 60.0:
        grade = "B"
        grade_desc = "Moderate - Slight lag spikes may occur during heavy streaming or downloads."
        badge_color = "#FBBF24"
    elif delta_ms <= 150.0:
        grade = "C"
        grade_desc = "Noticeable Bufferbloat - High latency during downloads will cause game stutter or video call freezes."
        badge_color = "#FB923C"
    elif delta_ms <= 300.0:
        grade = "D"
        grade_desc = "Poor - Heavy bufferbloat. Your router buffer is queuing packets uncontrollably."
        badge_color = "#F87171"
    else:
        grade = "F"
        grade_desc = "Critical Bufferbloat - Latency increases by >300ms under load. Causes dropped calls and game disconnects."
        badge_color = "#EF4444"

    return {
        "grade": grade,
        "grade_desc": grade_desc,
        "badge_color": badge_color,
        "unloaded_latency_ms": unloaded_avg,
        "loaded_latency_ms": loaded_avg,
        "bufferbloat_delta_ms": delta_ms,
        "download_speed_mbps": download_speed_mbps,
        "downloaded_mb": round(download_bytes / 1_000_000, 2),
        "unloaded_times": unloaded_res.get("raw_times", []),
        "loaded_times": loaded_res.get("raw_times", []),
        "recommendation": (
            "Bufferbloat is negligible. Your local queueing is healthy."
            if grade in ("A+", "A") else
            "To fix bufferbloat without calling your ISP, enable Smart Queue Management (SQM, fq_codel, or CAKE) in your router settings, or throttle background update downloads in Windows Settings > Delivery Optimization."
        )
    }
