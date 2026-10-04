import os
import psutil
from collections import defaultdict
from typing import Dict, List, Any

def get_network_processes() -> Dict[str, Any]:
    """
    Inspect all active network connections and group them by process.
    Detects bandwidth and connection-saturating applications.
    Safely handles AccessDenied when run as non-admin.
    """
    warnings = []
    conns = []

    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        warnings.append("Elevated privileges required for full network socket inspection. Run NetPulse as Administrator.")
    except Exception as e:
        warnings.append(f"Network socket query limitation: {e}")

    pid_map = defaultdict(list)
    total_established = 0
    total_listening = 0

    for c in conns:
        if c.status == "ESTABLISHED":
            total_established += 1
        elif c.status == "LISTEN":
            total_listening += 1

        if c.pid:
            pid_map[c.pid].append(c)

    results: List[Dict[str, Any]] = []

    for pid, c_list in pid_map.items():
        try:
            p = psutil.Process(pid)
            p_name = p.name()
            try:
                mem_mb = round(p.memory_info().rss / (1024 * 1024), 1)
            except Exception:
                mem_mb = 0.0

            try:
                cpu_pct = p.cpu_percent(interval=None)
            except Exception:
                cpu_pct = 0.0

            # Remote addresses summary
            remote_ips = set()
            established_count = 0
            for conn in c_list:
                if conn.status == "ESTABLISHED":
                    established_count += 1
                if conn.raddr:
                    remote_ips.add(f"{conn.raddr.ip}:{conn.raddr.port}")

            # Identify category
            name_lower = p_name.lower()
            if any(k in name_lower for k in ["steam", "epic", "battle.net", "dota", "valorant", "riot", "game", "league", "csgo"]):
                cat = "Gaming / Game Client"
            elif any(k in name_lower for k in ["chrome", "firefox", "edge", "brave", "opera", "browser"]):
                cat = "Web Browser"
            elif any(k in name_lower for k in ["torrent", "qbittorrent", "transmission", "utorrent"]):
                cat = "P2P / Torrent (High Bandwidth)"
            elif any(k in name_lower for k in ["onedrive", "dropbox", "googledrive", "sync"]):
                cat = "Cloud Sync"
            elif any(k in name_lower for k in ["discord", "zoom", "teams", "slack", "skype"]):
                cat = "VoIP / Conferencing"
            elif any(k in name_lower for k in ["svchost", "system", "searchhost"]):
                cat = "Windows System"
            else:
                cat = "Application"

            results.append({
                "pid": pid,
                "name": p_name,
                "category": cat,
                "connection_count": len(c_list),
                "established_count": established_count,
                "memory_mb": mem_mb,
                "cpu_percent": cpu_pct,
                "remote_endpoints": list(remote_ips)[:5],
                "total_remote_endpoints": len(remote_ips)
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # Sort by total connection count descending
    results.sort(key=lambda x: x["connection_count"], reverse=True)

    # Detect high hogging warning
    p2p_active = [r for r in results if "P2P" in r["category"]]
    high_socket_apps = [r for r in results if r["connection_count"] > 50]

    if p2p_active:
        warnings.append(f"Active P2P Torrent client detected ({p2p_active[0]['name']}). BitTorrent clients open hundreds of simultaneous UDP/TCP connections that heavily degrade Wi-Fi latency.")
    if high_socket_apps:
        top_app = high_socket_apps[0]
        warnings.append(f"'{top_app['name']}' has {top_app['connection_count']} active sockets, which may throttle available Wi-Fi queue slots.")

    return {
        "total_connections": len(conns),
        "established_connections": total_established,
        "listening_ports": total_listening,
        "active_processes": len(results),
        "processes": results[:25],
        "warnings": warnings
    }

def terminate_process(pid: int) -> Dict[str, Any]:
    """
    Safely terminate a process by PID.
    Handles AccessDenied, NoSuchProcess, critical OS protection, and force kill.
    """
    # Protect OS system processes and self
    if pid <= 4:
        return {"success": False, "message": f"PID {pid} is a protected operating system process and cannot be terminated."}

    if pid == os.getpid():
        return {"success": False, "message": "Cannot terminate the active NetPulse diagnostic server process."}

    try:
        p = psutil.Process(pid)
        name = p.name()

        # Send termination signal
        p.terminate()

        # Wait up to 1.5s for process to exit cleanly
        try:
            p.wait(timeout=1.5)
            return {"success": True, "message": f"Successfully terminated process '{name}' (PID {pid})"}
        except psutil.TimeoutExpired:
            # Process did not terminate within timeout; force kill
            p.kill()
            return {"success": True, "message": f"Process '{name}' (PID {pid}) did not exit cleanly and was force-killed."}

    except psutil.NoSuchProcess:
        return {"success": False, "message": f"Process (PID {pid}) is no longer running."}
    except psutil.AccessDenied:
        return {"success": False, "message": f"Access denied terminating process (PID {pid}). Please run NetPulse as Administrator."}
    except Exception as e:
        return {"success": False, "message": f"Could not terminate PID {pid}: {str(e)}"}
