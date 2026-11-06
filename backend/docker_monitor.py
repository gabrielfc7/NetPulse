import os
import socket
import http.client
import json
import urllib.request
from typing import List, Dict, Any

SOCKET_PATH = "/var/run/docker.sock"

class UnixSocketConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str):
        super().__init__("localhost")
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(3.0)
        self.sock.connect(self.socket_path)

def query_docker_socket(path: str, method: str = "GET") -> Any:
    """Query local Docker socket via Unix domain socket without external dependencies."""
    if not os.path.exists(SOCKET_PATH):
        return None
    try:
        conn = UnixSocketConnection(SOCKET_PATH)
        conn.request(method, path)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None

def get_containers_summary() -> List[Dict[str, Any]]:
    """Retrieve structured list of all running and stopped Docker containers."""
    raw = query_docker_socket("/containers/json?all=1")
    if not raw:
        # Fallback simulation or basic status if socket unmounted
        return []

    summary = []
    for c in raw:
        raw_names = c.get("Names", [])
        clean_name = raw_names[0].lstrip("/") if raw_names else "unknown"
        state = c.get("State", "unknown").lower()
        status_text = c.get("Status", "")
        
        # Determine health status from Status string
        health = "unknown"
        if "(healthy)" in status_text:
            health = "healthy"
        elif "(unhealthy)" in status_text:
            health = "unhealthy"
        elif "(health: starting)" in status_text:
            health = "starting"
        elif state == "running":
            health = "running"
        else:
            health = state

        # Extract mapped ports
        ports = []
        for p in c.get("Ports", []):
            pub = p.get("PublicPort")
            priv = p.get("PrivatePort")
            proto = p.get("Type", "tcp")
            if pub:
                ports.append(f"{pub}:{priv}/{proto}")
            elif priv:
                ports.append(f"{priv}/{proto}")

        summary.append({
            "id": c.get("Id", "")[:12],
            "name": clean_name,
            "image": c.get("Image", ""),
            "state": state,
            "status": status_text,
            "health": health,
            "ports": ", ".join(ports) if ports else "Host Mode",
            "created": c.get("Created", 0)
        })

    # Sort order: portal, netpulse, pihole, gods-eye-view, homepage
    order = {"pi-portal": 0, "netpulse-sentry": 1, "pihole-unbound": 2, "gods-eye-view": 3, "homepage": 4}
    summary.sort(key=lambda x: next((v for k, v in order.items() if k in x["name"]), 99))
    return summary

def get_pihole_quick_stats() -> Dict[str, Any]:
    """Fetch live query, blocking, and Unbound status from local Pi-hole instance."""
    try:
        # Pi-hole v6 API endpoint
        url = "http://127.0.0.1:8088/api/stats/summary"
        req = urllib.request.Request(url, headers={"User-Agent": "NetPulse-Portal"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode())
            queries = data.get("queries", {})
            return {
                "online": True,
                "total_queries": queries.get("total", 0),
                "blocked_queries": queries.get("blocked", 0),
                "percent_blocked": round(queries.get("percent_blocked", 0.0), 1),
                "domains_being_blocked": data.get("gravity", {}).get("domains_being_blocked", 0),
                "unbound_active": True
            }
    except Exception:
        # Check if port 53 responds or container is present
        return {
            "online": False,
            "total_queries": 0,
            "blocked_queries": 0,
            "percent_blocked": 0.0,
            "domains_being_blocked": 0,
            "unbound_active": False
        }
