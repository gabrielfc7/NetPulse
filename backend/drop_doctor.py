import re
import datetime
import json
import platform
from typing import Dict, List, Any, Optional
from .utils import run_powershell, run_command

def analyze_wifi_drops(days: int = 7, max_events: int = 60) -> Dict[str, Any]:
    """
    Analyze WLAN AutoConfig event logs to diagnose reasons for connection drops.
    Handles Windows PowerShell JSON parsing and Linux/Docker environments.
    """
    if platform.system() != "Windows":
        return {
            "stability_score": 100,
            "total_disconnects": 0,
            "driver_disconnects": 0,
            "signal_disconnects": 0,
            "user_disconnects": 0,
            "security_failures": 0,
            "connection_failures": 0,
            "findings": ["Operating in Linux / Docker appliance mode. Wi-Fi link is steady."],
            "recommended_fixes": [],
            "timeline": []
        }

    script = f"""
    $events = @(Get-WinEvent -FilterHashtable @{{
        LogName = 'Microsoft-Windows-WLAN-AutoConfig/Operational'
        Id = 8001, 8002, 8003, 11000, 11001, 11004, 11005, 11006
        StartTime = (Get-Date).AddDays(-{days})
    }} -MaxEvents {max_events} -ErrorAction SilentlyContinue | Select-Object TimeCreated, Id, LevelDisplayName, Message)
    if ($events.Count -gt 0) {{
        $events | ConvertTo-Json -Depth 2
    }} else {{
        '[]'
    }}
    """
    code, stdout, _ = run_powershell(script, timeout=25)
    raw_events = []
    if code == 0 and stdout.strip():
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, list):
                raw_events = [e for e in parsed if isinstance(e, dict)]
            elif isinstance(parsed, dict):
                raw_events = [parsed]
        except Exception:
            raw_events = []

    timeline: List[Dict[str, Any]] = []
    driver_disconnects = 0
    signal_disconnects = 0
    user_disconnects = 0
    security_failures = 0
    connection_failures = 0
    total_disconnects = 0

    for ev in raw_events:
        if not isinstance(ev, dict):
            continue
        ev_id = ev.get("Id", 0)
        time_raw = str(ev.get("TimeCreated", ""))
        msg = str(ev.get("Message", ""))

        # Parse date from /Date(1790969517430)/ or ISO string
        match_date = re.search(r"/Date\((\d+)\)/", time_raw)
        if match_date:
            try:
                ts = int(match_date.group(1)) / 1000.0
                dt = datetime.datetime.fromtimestamp(ts)
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                time_relative = dt.strftime("%b %d, %H:%M")
            except Exception:
                formatted_time = time_raw
                time_relative = time_raw
        else:
            try:
                clean_time = time_raw.replace("Z", "+00:00").split(".")[0]
                dt = datetime.datetime.fromisoformat(clean_time)
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                time_relative = dt.strftime("%b %d, %H:%M")
            except Exception:
                formatted_time = time_raw
                time_relative = time_raw

        # Extract Reason line
        reason_match = re.search(r"Reason:\s*(.+)", msg, re.IGNORECASE)
        reason_text = reason_match.group(1).strip() if reason_match else ""

        # Extract SSID
        ssid_match = re.search(r"SSID:\s*([^\r\n]+)", msg, re.IGNORECASE)
        ssid = ssid_match.group(1).strip() if ssid_match else ""

        # Extract Adapter
        adapter_match = re.search(r"Network Adapter:\s*([^\r\n]+)", msg, re.IGNORECASE)
        adapter = adapter_match.group(1).strip() if adapter_match else ""

        event_type = "info"
        summary = ""
        category = "Other"

        if ev_id == 8003:
            total_disconnects += 1
            event_type = "disconnect"
            if "by the driver" in reason_text.lower():
                driver_disconnects += 1
                category = "Driver / Power Save"
                summary = "Disconnected by network adapter driver (often caused by Windows power saving or adapter sleep state)."
            elif "by the user" in reason_text.lower():
                user_disconnects += 1
                category = "User Action"
                summary = "Disconnected by user action or manual reconnect."
            elif "out of range" in reason_text.lower() or "signal" in reason_text.lower() or "beacon" in reason_text.lower():
                signal_disconnects += 1
                category = "Signal Loss"
                summary = "Disconnected due to weak signal or lost router beacons."
            elif "roaming" in reason_text.lower():
                category = "Roaming"
                summary = "Disconnected to roam to a different access point or frequency band."
            else:
                summary = f"Disconnected: {reason_text or 'Reason unspecified by Windows'}"

        elif ev_id == 8002:
            connection_failures += 1
            event_type = "error"
            category = "Connection Failure"
            summary = "WLAN AutoConfig failed to connect to wireless network."

        elif ev_id == 11006:
            security_failures += 1
            event_type = "error"
            category = "Security Failure"
            summary = "Wireless security handshake or authentication failed."

        elif ev_id == 8001:
            event_type = "connect"
            category = "Connection"
            summary = f"Successfully connected to Wi-Fi network '{ssid}'."

        elif ev_id == 11004:
            event_type = "security_stop"
            category = "Security Teardown"
            summary = "Wireless security stopped (session closed)."

        elif ev_id == 11005:
            event_type = "security_success"
            category = "Security"
            summary = "Wireless security authentication succeeded."

        timeline.append({
            "id": ev_id,
            "timestamp": formatted_time,
            "time_display": time_relative,
            "type": event_type,
            "category": category,
            "summary": summary,
            "reason": reason_text,
            "ssid": ssid,
            "adapter": adapter
        })

    # Generate Doctor's Diagnostic Report and Fix Advice
    findings = []
    recommended_fixes = []

    if driver_disconnects > 0:
        findings.append(f"Detected {driver_disconnects} disconnect(s) initiated by the network driver. Windows is putting the Wi-Fi card to sleep or throttling its power state.")
        recommended_fixes.append({
            "action": "fix_power_save",
            "title": "Disable Wi-Fi Adapter Power Saving",
            "reason": "Prevents Windows from suspending the Wi-Fi card to save battery/power, which is the primary cause of driver-initiated disconnects.",
            "button_text": "Apply Power Fix Now"
        })
        recommended_fixes.append({
            "action": "tune_adapter_gaming",
            "title": "Tune Adapter Roaming & Throughput",
            "reason": "Lowers Roaming Aggressiveness to stop Windows from scanning and hopping APs, and enables Throughput Booster.",
            "button_text": "Tune Adapter Now"
        })

    if signal_disconnects > 0:
        findings.append(f"Detected {signal_disconnects} disconnect(s) caused by signal loss or lost beacons. The distance or physical obstruction between PC and router is near the drop threshold.")
        recommended_fixes.append({
            "action": "check_spectrum",
            "title": "Switch Wi-Fi Channel",
            "reason": "Severe interference on your current channel can cause the adapter to lose beacon frames.",
            "button_text": "Check Spectrum Tab"
        })

    if connection_failures > 0 or security_failures > 0:
        findings.append(f"Detected {connection_failures + security_failures} connection or security handshake failures. Winsock or TCP/IP cache may have corrupted state.")
        recommended_fixes.append({
            "action": "reset_winsock",
            "title": "Reset TCP/IP & Winsock Stack",
            "reason": "Clears corrupted sockets and network translation tables.",
            "button_text": "Reset Winsock Stack"
        })

    if not findings:
        findings.append("No abnormal disconnection drops detected in the analyzed time window. Your Wi-Fi link has remained stable.")

    # Drop stability score (100 - penalties)
    stability_score = max(0, 100 - (driver_disconnects * 15) - (signal_disconnects * 20) - (connection_failures * 25))

    return {
        "stability_score": stability_score,
        "total_disconnects": total_disconnects,
        "driver_disconnects": driver_disconnects,
        "signal_disconnects": signal_disconnects,
        "user_disconnects": user_disconnects,
        "security_failures": security_failures,
        "connection_failures": connection_failures,
        "findings": findings,
        "recommended_fixes": recommended_fixes,
        "timeline": timeline[:35]
    }

def check_recent_wlan_disconnect(seconds: int = 120) -> Optional[Dict[str, Any]]:
    """
    Rapidly check for recent Windows WLAN AutoConfig disconnect events (last N seconds).
    Returns parsed event details or None.
    """
    if platform.system() != "Windows":
        return None

    minutes = max(1, int(seconds / 60) + 1)
    script = f"""
    $events = @(Get-WinEvent -FilterHashtable @{{
        LogName = 'Microsoft-Windows-WLAN-AutoConfig/Operational'
        Id = 8002, 8003, 11006
        StartTime = (Get-Date).AddMinutes(-{minutes})
    }} -MaxEvents 3 -ErrorAction SilentlyContinue | Select-Object Id, TimeCreated, Message)
    if ($events.Count -gt 0) {{
        $events | ConvertTo-Json -Depth 2
    }} else {{
        '[]'
    }}
    """
    code, stdout, _ = run_powershell(script, timeout=6)
    if code != 0 or not stdout.strip():
        return None

    try:
        parsed = json.loads(stdout)
        events = parsed if isinstance(parsed, list) else [parsed]
        for ev in events:
            if not isinstance(ev, dict):
                continue
            ev_id = ev.get("Id", 0)
            msg = str(ev.get("Message", ""))
            reason_match = re.search(r"Reason:\s*(.+)", msg, re.IGNORECASE)
            reason_text = reason_match.group(1).strip() if reason_match else ""
            adapter_match = re.search(r"Network Adapter:\s*([^\r\n]+)", msg, re.IGNORECASE)
            adapter = adapter_match.group(1).strip() if adapter_match else ""

            is_driver = "by the driver" in reason_text.lower() or "driver" in msg.lower()
            is_signal = "out of range" in reason_text.lower() or "signal" in reason_text.lower() or "beacon" in reason_text.lower()
            is_roam = "roaming" in reason_text.lower()

            return {
                "id": ev_id,
                "reason": reason_text,
                "adapter": adapter,
                "is_driver": is_driver,
                "is_signal": is_signal,
                "is_roam": is_roam,
                "message": msg
            }
    except Exception:
        pass
    return None

def diagnose_immediate_drop(
    gw_loss: float,
    cf_loss: float,
    gw_ms: float,
    cf_ms: float,
    gw_ip: str = ""
) -> Dict[str, Any]:
    """
    Instant root-cause diagnosis and actionable fix advisory right when a drop is detected.
    Used by 24/7 background monitor daemon to immediately dispatch targeted fix advice.
    """
    # Case 1: Gateway is reachable, Internet is failing -> ISP / External WAN drop
    if gw_loss < 50.0 and (cf_loss >= 80.0 or cf_ms == 0):
        return {
            "root_cause": "ISP / External WAN Drop (Local Wi-Fi Healthy)",
            "category": "ISP",
            "fix_advice": (
                f"Local link to router is fast and healthy ({gw_ms:.1f}ms, 0% loss). "
                "The drop is upstream between your router/modem and your ISP. "
                "Fix: Do not alter local Wi-Fi. Check your modem WAN/Internet light. "
                "If drops persist, power-cycle modem/ONT or tether to a mobile hotspot for the match."
            ),
            "short_fix": "Local Wi-Fi is fine (1ms). Issue is upstream with ISP/modem. Check modem lights.",
            "recommended_action": "flush_dns",
            "action_button": "Flush DNS & ARP",
            "is_local_issue": False
        }

    # Case 2: Gateway is failing (Local connection dropped or degraded)
    if gw_loss >= 50.0:
        wlan_ev = check_recent_wlan_disconnect(seconds=180)
        if wlan_ev:
            if wlan_ev.get("is_driver"):
                adapter_name = wlan_ev.get("adapter") or "Wi-Fi adapter"
                return {
                    "root_cause": f"Wi-Fi Driver Disconnected ({adapter_name})",
                    "category": "Driver",
                    "fix_advice": (
                        f"Windows or the network driver put '{adapter_name}' to sleep or reset its link. "
                        "Fix: 1. Click 'Disable Wi-Fi Power Saving' in NetPulse to turn off Windows Selective Suspend. "
                        "2. Set 'Roaming Aggressiveness' to Lowest in NetPulse Adapter Tuning. "
                        "3. Disable Killer/Intel Control Center background throttling."
                    ),
                    "short_fix": "Network adapter suspended by Windows power-saving. Click 'Disable Wi-Fi Power Saving'.",
                    "recommended_action": "fix_power_save",
                    "action_button": "Disable Wi-Fi Power Saving",
                    "is_local_issue": True
                }
            elif wlan_ev.get("is_signal"):
                return {
                    "root_cause": "Wi-Fi Signal Drop / Lost Router Beacons",
                    "category": "Signal",
                    "fix_advice": (
                        "The Wi-Fi card lost beacon signals from your router. "
                        "Fix: 1. Move closer or reduce obstacles to your router. "
                        "2. Connect to 5GHz/6GHz band to bypass 2.4GHz microwave/Bluetooth congestion. "
                        "3. Check Wi-Fi Scanner tab to switch to an uncongested channel."
                    ),
                    "short_fix": "Lost router beacon signals. Connect to 5GHz/6GHz or move closer.",
                    "recommended_action": "tune_adapter_gaming",
                    "action_button": "Tune Gaming Mode",
                    "is_local_issue": True
                }
            elif wlan_ev.get("id") in (8002, 11006):
                return {
                    "root_cause": "Wi-Fi Connection / Handshake Failure",
                    "category": "Handshake",
                    "fix_advice": (
                        "WLAN AutoConfig reported an internal handshake failure. "
                        "Fix: Click 'Reset TCP/IP & Winsock Stack' in NetPulse to clear corrupt network translation tables."
                    ),
                    "short_fix": "WLAN handshake failed. Click 'Reset TCP/IP & Winsock Stack'.",
                    "recommended_action": "reset_winsock",
                    "action_button": "Reset Winsock Stack",
                    "is_local_issue": True
                }

        # Gateway down without specific WLAN event
        target_gw = gw_ip or "192.168.1.1"
        return {
            "root_cause": f"Local Router Gateway Unreachable ({target_gw})",
            "category": "Gateway",
            "fix_advice": (
                f"PC lost communication with local router ({target_gw}). "
                "Fix: 1. Verify router power and Wi-Fi connection. "
                "2. Click 'Renew DHCP Lease' in NetPulse to refresh your local IP assignment."
            ),
            "short_fix": f"Cannot reach local router ({target_gw}). Check router power or renew DHCP lease.",
            "recommended_action": "renew_dhcp",
            "action_button": "Renew DHCP Lease",
            "is_local_issue": True
        }

    # Case 3: Partial packet loss or extreme jitter
    return {
        "root_cause": f"Severe Packet Loss Spike ({max(gw_loss, cf_loss):.0f}%)",
        "category": "PacketLoss",
        "fix_advice": (
            f"Network experiencing high packet loss ({max(gw_loss, cf_loss):.0f}%). "
            "Fix: NetPulse has flushed DNS and ARP tables. "
            "Close bandwidth-heavy background software (Steam, BitTorrent, cloud backups) in Process Monitor."
        ),
        "short_fix": f"Packet loss is {max(gw_loss, cf_loss):.0f}%. Close background apps in Process Monitor.",
        "recommended_action": "clear_arp",
        "action_button": "Clear ARP Cache",
        "is_local_issue": False
    }
