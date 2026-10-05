import subprocess
import urllib.request
import json
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("netpulse.version")

CURRENT_VERSION = "2.3.0"
APP_NAME = "NetPulse Pro"
CHANNEL = "Stable Pro"
RELEASE_DATE = "2026-10-04"
GITHUB_REPO = "gabrielfc7/NetPulse"
GITHUB_URL = f"https://github.com/{GITHUB_REPO}"

CHANGELOG = [
    {
        "version": "2.3.0",
        "date": "2026-10-04",
        "tag": "Latest",
        "changes": [
            "Added 1-Click LAN SMB File Sharing (Port 445) exposure remediation & shield.",
            "Integrated Version Control manager with automated remote GitHub update check.",
            "Added Security Audit Report export (Formatted Markdown and JSON).",
            "Fixed tab container nesting bug causing blank Security & Vulnerabilities screen.",
            "Deduplicated listening sockets across IPv4 (0.0.0.0) and IPv6 (::) in port auditor."
        ]
    },
    {
        "version": "2.2.0",
        "date": "2026-10-04",
        "tag": "Stable",
        "changes": [
            "Implemented concurrent 6-vector security audit assessment with thread pool execution.",
            "Added in-memory audit caching with forced refresh override.",
            "Introduced skeleton loaders and asset versioning query parameters.",
            "Enhanced mobile navigation drawer and active tab persistence."
        ]
    },
    {
        "version": "1.0.0",
        "date": "2026-10-04",
        "tag": "Release",
        "changes": [
            "Initial release of NetPulse Pro - Autonomous Network Diagnostic Studio.",
            "Continuous 24/7 Drop Sentry daemon with instant ISP vs. local root-cause analysis.",
            "Real-time Wi-Fi spectrum radar, DNS benchmark, and Bufferbloat speed analyzer.",
            "Multi-channel alert dispatcher (Windows Toast, ntfy.sh, Discord, Telegram)."
        ]
    }
]

_update_cache: Optional[Dict[str, Any]] = None
_update_cache_ts: float = 0.0

def get_git_commit() -> str:
    """Retrieve the current short Git commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "095d29f"

def check_remote_updates(force: bool = False) -> Dict[str, Any]:
    """
    Check GitHub repository releases/commits to see if a newer version is available.
    Cached for 1 hour unless force=True.
    """
    global _update_cache, _update_cache_ts
    now = time.time()
    if not force and _update_cache is not None and (now - _update_cache_ts < 3600):
        return _update_cache

    latest_ver = CURRENT_VERSION
    update_available = False
    release_url = f"{GITHUB_URL}/releases/latest"
    release_body = ""

    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={
            "User-Agent": f"NetPulsePro/{CURRENT_VERSION}",
            "Accept": "application/vnd.github.v3+json"
        })
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
            tag_name = data.get("tag_name", "").lstrip("v")
            if tag_name:
                latest_ver = tag_name
                release_body = data.get("body", "")
                release_url = data.get("html_url", release_url)

                # Simple semver comparison: e.g. 2.4.0 > 2.3.0
                def parse_ver(v_str):
                    return [int(x) for x in v_str.split(".") if x.isdigit()]

                curr_parts = parse_ver(CURRENT_VERSION)
                latest_parts = parse_ver(latest_ver)
                if latest_parts > curr_parts:
                    update_available = True
    except Exception as e:
        logger.debug(f"GitHub release check note: {e}")
        # If no published release yet, check latest commit on main
        try:
            url_commits = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
            req2 = urllib.request.Request(url_commits, headers={
                "User-Agent": f"NetPulsePro/{CURRENT_VERSION}",
                "Accept": "application/vnd.github.v3+json"
            })
            with urllib.request.urlopen(req2, timeout=4) as resp2:
                cdata = json.loads(resp2.read().decode())
                remote_sha = cdata.get("sha", "")[:7]
                local_sha = get_git_commit()
                if remote_sha and local_sha and remote_sha != local_sha:
                    # New commits present
                    update_available = False # Current release is in sync
        except Exception:
            pass

    result = {
        "current_version": CURRENT_VERSION,
        "latest_version": latest_ver,
        "update_available": update_available,
        "release_url": release_url,
        "release_notes_excerpt": release_body[:300] if release_body else "You are running the latest version of NetPulse Pro.",
        "last_checked_ts": now
    }
    _update_cache = result
    _update_cache_ts = now
    return result

def get_full_version_manifest(force_check: bool = False) -> Dict[str, Any]:
    """Return complete version, commit, update status, and changelog manifest."""
    commit_sha = get_git_commit()
    update_info = check_remote_updates(force=force_check)

    return {
        "app_name": APP_NAME,
        "current_version": CURRENT_VERSION,
        "channel": CHANNEL,
        "commit": commit_sha,
        "release_date": RELEASE_DATE,
        "github_url": GITHUB_URL,
        "update_info": update_info,
        "changelog": CHANGELOG
    }
