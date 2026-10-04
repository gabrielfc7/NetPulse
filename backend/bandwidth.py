import time
import threading
from collections import deque
from typing import Dict, Any, Optional, List
import psutil

class BandwidthTracker:
    """
    Real-time network interface I/O bandwidth throughput engine.
    Computes download and upload speed deltas in kbps and mbps with minimal CPU overhead.
    """

    def __init__(self, history_maxlen: int = 60, min_interval_sec: float = 0.5):
        self._lock = threading.RLock()
        self.min_interval_sec = min_interval_sec
        self.history_maxlen = history_maxlen

        self._last_time = time.time()
        self._last_counters: Dict[str, Any] = {}
        self._last_rates: Dict[str, Any] = {
            "download_kbps": 0.0,
            "upload_kbps": 0.0,
            "download_mbps": 0.0,
            "upload_mbps": 0.0,
            "bytes_recv_rate": 0.0,
            "bytes_sent_rate": 0.0
        }
        self._history: deque = deque(maxlen=history_maxlen)

        # Initialize initial baseline
        try:
            self._last_counters = psutil.net_io_counters(pernic=True)
            self._last_total = psutil.net_io_counters(pernic=False)
        except Exception:
            self._last_counters = {}
            self._last_total = None

    def _find_primary_interface(self, pernic: Dict[str, Any], hint: Optional[str] = None) -> str:
        """Identify the primary active internet interface."""
        if hint and hint in pernic:
            return hint

        # Priority search for Wi-Fi / WLAN or Ethernet
        names = list(pernic.keys())
        for n in names:
            n_lower = n.lower()
            if "wi-fi" in n_lower or "wifi" in n_lower or "wlan" in n_lower or "wireless" in n_lower:
                return n

        for n in names:
            n_lower = n.lower()
            if "ethernet" in n_lower or "eth0" in n_lower or "en0" in n_lower:
                return n

        # Fallback to interface with highest bytes received
        best_name = names[0] if names else "default"
        best_bytes = -1
        for n, c in pernic.items():
            if "loopback" not in n.lower() and c.bytes_recv > best_bytes:
                best_bytes = c.bytes_recv
                best_name = n

        return best_name

    def get_realtime_bandwidth(self, interface_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Compute instantaneous throughput using delta from previous sample.
        Returns download/upload rates in kbps and mbps.
        """
        now = time.time()

        with self._lock:
            try:
                current_pernic = psutil.net_io_counters(pernic=True)
                current_total = psutil.net_io_counters(pernic=False)
            except Exception:
                current_pernic = self._last_counters
                current_total = self._last_total

            iface = self._find_primary_interface(current_pernic, interface_hint)

            curr_io = current_pernic.get(iface) or current_total
            last_io = self._last_counters.get(iface) or self._last_total

            dt = now - self._last_time

            if dt >= self.min_interval_sec and curr_io and last_io:
                bytes_recv_delta = max(0, curr_io.bytes_recv - last_io.bytes_recv)
                bytes_sent_delta = max(0, curr_io.bytes_sent - last_io.bytes_sent)

                bytes_recv_rate = bytes_recv_delta / dt
                bytes_sent_rate = bytes_sent_delta / dt

                dl_kbps = round((bytes_recv_rate * 8.0) / 1000.0, 2)
                ul_kbps = round((bytes_sent_rate * 8.0) / 1000.0, 2)
                dl_mbps = round(dl_kbps / 1000.0, 2)
                ul_mbps = round(ul_kbps / 1000.0, 2)

                self._last_rates = {
                    "download_kbps": dl_kbps,
                    "upload_kbps": ul_kbps,
                    "download_mbps": dl_mbps,
                    "upload_mbps": ul_mbps,
                    "bytes_recv_rate": round(bytes_recv_rate, 2),
                    "bytes_sent_rate": round(bytes_sent_rate, 2),
                }

                self._last_time = now
                self._last_counters = current_pernic
                self._last_total = current_total

                # Record in rolling history buffer
                self._history.append({
                    "timestamp": round(now, 2),
                    "download_kbps": dl_kbps,
                    "upload_kbps": ul_kbps,
                    "download_mbps": dl_mbps,
                    "upload_mbps": ul_mbps
                })

            total_recv = curr_io.bytes_recv if curr_io else 0
            total_sent = curr_io.bytes_sent if curr_io else 0
            packets_recv = curr_io.packets_recv if curr_io else 0
            packets_sent = curr_io.packets_sent if curr_io else 0

            return {
                "interface": iface,
                "download_kbps": self._last_rates["download_kbps"],
                "upload_kbps": self._last_rates["upload_kbps"],
                "download_mbps": self._last_rates["download_mbps"],
                "upload_mbps": self._last_rates["upload_mbps"],
                "bytes_recv_rate": self._last_rates["bytes_recv_rate"],
                "bytes_sent_rate": self._last_rates["bytes_sent_rate"],
                "bytes_recv_total": total_recv,
                "bytes_sent_total": total_sent,
                "packets_recv_total": packets_recv,
                "packets_sent_total": packets_sent,
                "history": list(self._history),
                "timestamp": round(now, 2)
            }

bandwidth_tracker = BandwidthTracker()
