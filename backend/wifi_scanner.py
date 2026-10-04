import re
import math
from typing import Dict, List, Any
import platform
from .utils import run_command, get_default_gateway, get_active_wifi_interface
from .cache import cached

def _build_ethernet_profile(active_iface: Dict[str, Any], gw: str) -> Dict[str, Any]:
    """Return a pristine wired connection profile for Ethernet / appliance mode."""
    speed_raw = str(active_iface.get("Speed", "1000 Mbps"))
    speed_match = re.search(r"(\d+)", speed_raw)
    speed_mbps = speed_match.group(1) if speed_match else "1000"
    if "gbps" in speed_raw.lower():
        speed_mbps = str(int(speed_mbps) * 1000)

    adapter_name = active_iface.get("Description") or active_iface.get("Name") or "Gigabit Ethernet Adapter"
    iface_name = active_iface.get("Name", "Ethernet")

    return {
        "connected": True,
        "is_ethernet": True,
        "adapter": adapter_name,
        "interface_name": iface_name,
        "guid": "",
        "mac": active_iface.get("Mac", ""),
        "ssid": "Wired Ethernet Connection",
        "bssid": "",
        "state": "connected",
        "band": "Wired Gigabit",
        "channel": 0,
        "radio_type": "802.3 Ethernet",
        "authentication": "Hardware Port",
        "cipher": "Direct Cable",
        "rx_rate_mbps": speed_mbps,
        "tx_rate_mbps": speed_mbps,
        "signal_percent": 100,
        "rssi_dbm": 0,
        "signal_rating": "Pristine (Wired Cable Link)",
        "signal_color": "#10B981",
        "default_gateway": gw
    }

def _build_disconnected_profile(gw: str, reason: str = "Wi-Fi is disconnected.") -> Dict[str, Any]:
    """Return a graceful, safe disconnected profile."""
    return {
        "connected": False,
        "is_ethernet": False,
        "adapter": "Disconnected",
        "interface_name": "None",
        "guid": "",
        "mac": "",
        "ssid": "Disconnected",
        "bssid": "",
        "state": "disconnected",
        "band": "None",
        "channel": 0,
        "radio_type": "None",
        "authentication": "None",
        "cipher": "None",
        "rx_rate_mbps": "0",
        "tx_rate_mbps": "0",
        "signal_percent": 0,
        "rssi_dbm": -100,
        "signal_rating": "Disconnected",
        "signal_color": "#EF4444",
        "default_gateway": gw,
        "error": reason
    }

@cached(ttl=3.5)
def parse_wifi_interface() -> Dict[str, Any]:
    """
    Get active network interface details and link quality.
    Supports Windows (English and localized netsh), Linux / Docker / Raspberry Pi,
    and pure wired Ethernet appliance mode.
    """
    gw = get_default_gateway()
    active_iface = get_active_wifi_interface()

    # 1. Non-Windows (Linux / Raspberry Pi / Docker Appliance Mode)
    if platform.system() != "Windows":
        is_wireless = bool(active_iface.get("IsWireless")) or "wlan" in active_iface.get("Name", "")
        if not is_wireless and active_iface.get("IP"):
            return _build_ethernet_profile(active_iface, gw)
        elif not active_iface.get("IP"):
            return _build_disconnected_profile(gw, "No active network IP found.")

        return {
            "connected": True,
            "is_ethernet": False,
            "adapter": active_iface.get("Description", "Raspberry Pi Wi-Fi"),
            "interface_name": active_iface.get("Name", "wlan0"),
            "guid": "",
            "mac": active_iface.get("Mac", ""),
            "ssid": "Raspberry Pi Wi-Fi",
            "bssid": "",
            "state": "connected",
            "band": "2.4/5 GHz",
            "channel": 1,
            "radio_type": "802.11",
            "authentication": "WPA2",
            "cipher": "CCMP",
            "rx_rate_mbps": "150",
            "tx_rate_mbps": "150",
            "signal_percent": 85,
            "rssi_dbm": -45,
            "signal_rating": "Good",
            "signal_color": "#10B981",
            "default_gateway": gw
        }

    # 2. Windows: Execute netsh wlan show interfaces
    code, stdout, _ = run_command("netsh wlan show interfaces", timeout=6)

    # If netsh failed or returned no wireless interface:
    # Check if we have an active wired Ethernet interface
    no_wifi = (code != 0) or ("no wireless interface" in stdout.lower()) or ("wlansvc" in stdout.lower())
    if no_wifi:
        if active_iface.get("IP") and not active_iface.get("IsWireless", False):
            return _build_ethernet_profile(active_iface, gw)
        return _build_disconnected_profile(gw, "No active wireless interface found or Wi-Fi service disabled.")

    # Parse key-value lines with multilingual resilience
    data: Dict[str, str] = {}
    for line in stdout.splitlines():
        if ":" in line:
            parts = line.split(":", 1)
            data[parts[0].strip().lower()] = parts[1].strip()

    # Find State with multilingual keys: State, Status, Estado, État
    state_val = "disconnected"
    for k, v in data.items():
        if k in ("state", "status", "estado", "état", "etat"):
            state_val = v
            break

    is_connected = bool(re.search(r"(?i)(connected|verbunden|conectado|connect[ée])", state_val))

    # If Wi-Fi is disconnected, check if user is connected via Ethernet cable
    if not is_connected:
        if active_iface.get("IP") and not active_iface.get("IsWireless", False):
            return _build_ethernet_profile(active_iface, gw)
        return _build_disconnected_profile(gw, f"Wi-Fi state: {state_val}")

    # Helper to look up localized keys
    def get_val(*keywords, default=""):
        for k, v in data.items():
            for kw in keywords:
                if kw in k:
                    return v
        return default

    # Signal & RSSI
    signal_raw = get_val("signal", "señal", default="0%")
    signal_str = re.sub(r"[^\d]", "", signal_raw)
    try:
        signal_percent = int(signal_str) if signal_str else 0
    except ValueError:
        signal_percent = 0

    rssi_raw = get_val("rssi", default="")
    rssi_str = re.sub(r"[^\d\-]", "", rssi_raw)
    try:
        rssi_dbm = int(rssi_str) if rssi_str else int((signal_percent / 2) - 100)
    except ValueError:
        rssi_dbm = int((signal_percent / 2) - 100)

    # Link speeds
    rx_speed = get_val("receive rate", "empfangsrate", "réception", "reception", "velocidad de recepción", default="0")
    rx_speed = re.sub(r"[^\d]", "", rx_speed) or "0"

    tx_speed = get_val("transmit rate", "übertragungsrate", "transmission", "velocidad de transmisión", default="0")
    tx_speed = re.sub(r"[^\d]", "", tx_speed) or "0"

    # Band & Channel
    band = get_val("band", "bande", "banda", default="5 GHz")
    channel_raw = get_val("channel", "kanal", "canal", default="0")
    channel_str = re.sub(r"[^\d]", "", channel_raw) or "0"
    channel = int(channel_str) if channel_str.isdigit() else 0

    # SSID & BSSID
    ssid = get_val("ssid", default="Unknown SSID")
    bssid = get_val("bssid", default="")

    # Adapter descriptions
    adapter_desc = get_val("description", "beschreibung", "descripción", default="Wireless Network Adapter")
    iface_name = get_val("name", "schnittstellenname", "nom", "nombre", default="Wi-Fi")

    # Radio type & cipher
    radio_type = get_val("radio type", "funktyp", "type de radio", "tipo de radio", default="802.11")
    auth = get_val("authentication", "authentifizierung", "authentification", "autenticación", default="WPA2")
    cipher = get_val("cipher", "verschlüsselung", "chiffrement", "cifrado", default="CCMP")

    # Signal Quality Rating
    if rssi_dbm >= -55:
        signal_rating = "Excellent"
        signal_color = "#10B981"
    elif rssi_dbm >= -67:
        signal_rating = "Very Good"
        signal_color = "#34D399"
    elif rssi_dbm >= -75:
        signal_rating = "Fair (Vulnerable to jitter)"
        signal_color = "#FBBF24"
    elif rssi_dbm >= -85:
        signal_rating = "Poor (Prone to drops)"
        signal_color = "#F87171"
    else:
        signal_rating = "Critical (Unstable)"
        signal_color = "#EF4444"

    return {
        "connected": True,
        "is_ethernet": False,
        "adapter": adapter_desc,
        "interface_name": iface_name,
        "guid": get_val("guid", default=""),
        "mac": get_val("physical address", "physische adresse", "adresse physique", "dirección física", default=""),
        "ssid": ssid,
        "bssid": bssid,
        "state": state_val,
        "band": band,
        "channel": channel,
        "radio_type": radio_type,
        "authentication": auth,
        "cipher": cipher,
        "rx_rate_mbps": rx_speed,
        "tx_rate_mbps": tx_speed,
        "signal_percent": signal_percent,
        "rssi_dbm": rssi_dbm,
        "signal_rating": signal_rating,
        "signal_color": signal_color,
        "default_gateway": gw
    }

@cached(ttl=5.0)
def scan_nearby_networks() -> List[Dict[str, Any]]:
    """Scan all nearby networks and BSSIDs with frequency, channel, and utilization."""
    if platform.system() != "Windows":
        return []

    code, stdout, _ = run_command("netsh wlan show networks mode=bssid", timeout=12)
    if code != 0 or not stdout:
        return []

    networks: List[Dict[str, Any]] = []
    current_ssid = None
    current_bssid = None

    for line in stdout.splitlines():
        line_clean = line.strip()

        # Match SSID line (e.g. "SSID 1 : MyNetwork" or "SSID 12 : Guest Network")
        if re.match(r"^SSID\s+\d+\s*:", line_clean, re.IGNORECASE) or line_clean.startswith("SSID "):
            parts = line_clean.split(":", 1)
            ssid_name = parts[1].strip() if len(parts) > 1 else "Hidden Network"
            if not ssid_name:
                ssid_name = "Hidden Network"
            current_ssid = {
                "ssid": ssid_name,
                "bssids": []
            }
            networks.append(current_ssid)
            current_bssid = None

        # Match BSSID line (e.g. "BSSID 1 : 12:34:56:78:90:ab")
        elif (re.search(r"BSSID\s+\d*\s*:", line_clean, re.IGNORECASE) or "BSSID" in line_clean) and current_ssid is not None:
            # Extract MAC address from line
            mac_match = re.search(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})", line_clean)
            bssid_mac = mac_match.group(1) if mac_match else ""
            if not bssid_mac and ":" in line_clean:
                parts = line_clean.split(":", 1)
                bssid_mac = parts[1].strip() if len(parts) > 1 else ""

            current_bssid = {
                "bssid": bssid_mac,
                "signal_percent": 0,
                "rssi_dbm": -90,
                "radio_type": "802.11",
                "band": "2.4 GHz",
                "channel": 1,
                "auth": "WPA2",
                "encryption": "CCMP",
                "stations": 0,
                "utilization_percent": 0
            }
            current_ssid["bssids"].append(current_bssid)

        elif current_bssid is not None and ":" in line_clean:
            parts = line_clean.split(":", 1)
            key = parts[0].strip().lower()
            val = parts[1].strip()

            if any(k in key for k in ["signal", "señal"]):
                sig = int(re.sub(r"[^\d]", "", val) or 0)
                current_bssid["signal_percent"] = sig
                current_bssid["rssi_dbm"] = int((sig / 2) - 100)
            elif any(k in key for k in ["radio", "funktyp"]):
                current_bssid["radio_type"] = val
            elif "band" in key:
                current_bssid["band"] = val
            elif any(k in key for k in ["channel", "kanal", "canal"]):
                current_bssid["channel"] = int(re.sub(r"[^\d]", "", val) or 1)
            elif any(k in key for k in ["auth", "autentic"]):
                current_bssid["auth"] = val
            elif any(k in key for k in ["encrypt", "cifrado", "verschlüsselung", "chiffrement"]):
                current_bssid["encryption"] = val
            elif any(k in key for k in ["station", "client"]):
                current_bssid["stations"] = int(re.sub(r"[^\d]", "", val) or 0)
            elif any(k in key for k in ["utiliz", "auslastung", "charge"]):
                match = re.search(r"\((\d+)\s*%\)", val)
                if match:
                    current_bssid["utilization_percent"] = int(match.group(1))

    return networks

def analyze_channels(current_interface: Dict[str, Any], networks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate congestion score for 2.4 GHz and 5 GHz channels.
    Determine best recommended channels and evaluate current connection.
    Gracefully handles pure Ethernet appliance mode and empty wireless scan results.
    """
    # Check if connected via wired Ethernet
    is_ethernet = current_interface.get("is_ethernet") or ("ethernet" in current_interface.get("band", "").lower()) or ("802.3" in current_interface.get("radio_type", ""))

    # Flatten all BSSIDs
    all_bssids = []
    for net in networks:
        for b in net.get("bssids", []):
            all_bssids.append({
                "ssid": net.get("ssid", "Unknown"),
                **b
            })

    # 2.4 GHz Channel Analysis (Channels 1 to 14)
    channels_24: Dict[int, Dict[str, Any]] = {
        ch: {"channel": ch, "count": 0, "networks": [], "score": 100, "recommended": ch in (1, 6, 11)}
        for ch in range(1, 14)
    }

    # 5 GHz standard channels
    common_5ghz = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]
    channels_5g: Dict[int, Dict[str, Any]] = {
        ch: {"channel": ch, "count": 0, "networks": [], "score": 100, "is_dfs": (52 <= ch <= 144)}
        for ch in common_5ghz
    }

    # Populate network counts
    for b in all_bssids:
        band = b.get("band", "")
        ch = b.get("channel", 0)
        signal = b.get("signal_percent", 50)
        ssid_display = b.get("ssid", "Unknown")
        utilization = b.get("utilization_percent", 0)

        # Weight based on signal strength
        weight = (signal / 100.0) * 20

        if "2.4" in band and ch in channels_24:
            channels_24[ch]["count"] += 1
            channels_24[ch]["networks"].append(ssid_display)
            channels_24[ch]["score"] = max(0, channels_24[ch]["score"] - weight - (utilization * 0.3))
            for adj in range(max(1, ch - 2), min(14, ch + 3)):
                if adj != ch and adj in channels_24:
                    channels_24[adj]["score"] = max(0, channels_24[adj]["score"] - (weight * 0.6))

        elif "5" in band:
            if ch not in channels_5g:
                channels_5g[ch] = {"channel": ch, "count": 0, "networks": [], "score": 100, "is_dfs": (52 <= ch <= 144)}
            channels_5g[ch]["count"] += 1
            channels_5g[ch]["networks"].append(ssid_display)
            channels_5g[ch]["score"] = max(0, channels_5g[ch]["score"] - weight - (utilization * 0.3))

    recom_24 = sorted([c for c in channels_24.values() if c["channel"] in (1, 6, 11)], key=lambda x: x["score"], reverse=True)
    best_24 = recom_24[0]["channel"] if recom_24 else 1

    recom_5g = sorted(channels_5g.values(), key=lambda x: (x["score"] - (5 if x["is_dfs"] else 0)), reverse=True)
    best_5g = recom_5g[0]["channel"] if recom_5g else 36

    curr_band = current_interface.get("band", "")
    curr_ch = current_interface.get("channel", 0)
    current_status = "Optimal"
    recommendation_text = ""

    if is_ethernet:
        current_status = "Optimal (Wired)"
        recommendation_text = "You are connected via high-speed wired Gigabit Ethernet. Your connection bypasses all wireless spectrum and channel interference."
    elif not current_interface.get("connected"):
        current_status = "Disconnected"
        recommendation_text = "Wi-Fi is currently disconnected. Reconnect to assess wireless channel conditions."
    elif "2.4" in curr_band:
        current_score = channels_24.get(curr_ch, {}).get("score", 50)
        if curr_ch not in (1, 6, 11):
            current_status = "High Interference"
            recommendation_text = f"You are on 2.4 GHz Channel {curr_ch}, which overlaps with adjacent channels and causes packet collisions. Switch your router's 2.4 GHz channel to Channel {best_24}, or preferably switch to the 5 GHz band for up to 10x higher speeds and zero interference."
        elif current_score < 60:
            current_status = "Crowded"
            recommendation_text = f"Your current 2.4 GHz channel ({curr_ch}) is crowded ({channels_24[curr_ch]['count']} APs). Cleanest available 2.4 GHz channel is Channel {best_24}."
        else:
            recommendation_text = f"Your 2.4 GHz channel ({curr_ch}) has acceptable traffic, but 5 GHz offers significantly lower latency and higher bandwidth."
    elif "5" in curr_band:
        current_score = channels_5g.get(curr_ch, {}).get("score", 90)
        curr_neighbors = channels_5g.get(curr_ch, {}).get("count", 1) - 1
        if curr_neighbors > 2:
            current_status = "Moderate Congestion"
            recommendation_text = f"Channel {curr_ch} has {curr_neighbors} other networks broadcasting on it. Recommended cleaner channel: Channel {best_5g}."
        else:
            current_status = "Optimal"
            recommendation_text = f"Channel {curr_ch} is clean with minimal interference ({curr_neighbors} overlapping neighbors). Your 5 GHz spectrum configuration is excellent."
    else:
        recommendation_text = f"Spectrum audit complete. Recommended channels: 2.4 GHz Ch {best_24}, 5 GHz Ch {best_5g}."

    return {
        "current_channel": curr_ch,
        "current_band": curr_band,
        "current_status": current_status,
        "recommendation": recommendation_text,
        "best_channel_24": best_24,
        "best_channel_5g": best_5g,
        "channels_24": list(channels_24.values()),
        "channels_5g": list(channels_5g.values()),
        "total_visible_bssids": len(all_bssids)
    }
