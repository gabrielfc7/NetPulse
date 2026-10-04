import urllib.request
import urllib.parse
import json
import logging
import platform
import threading
from typing import Dict, Any, Optional
from .db import get_all_settings
from .utils import run_powershell

logger = logging.getLogger("NetPulseNotifier")

def send_windows_toast(title: str, message: str, fix_advice: str = "") -> bool:
    """Send native Windows Desktop Toast Notification asynchronously."""
    if platform.system() != "Windows":
        return False

    def _worker():
        try:
            combined_text = message
            if fix_advice:
                combined_text = f"{message}\n\nFix: {fix_advice}"

            safe_title = title.replace("'", "''").replace('"', '`"')[:64]
            safe_text = combined_text.replace("'", "''").replace('"', '`"')[:300]

            script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $textNodes = $template.GetElementsByTagName('text')
            $textNodes.Item(0).AppendChild($template.CreateTextNode('{safe_title}')) > $null
            $textNodes.Item(1).AppendChild($template.CreateTextNode('{safe_text}')) > $null
            $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($toast)
            """
            run_powershell(script, timeout=6)
        except Exception as e:
            logger.debug(f"Windows toast error: {e}")

    threading.Thread(target=_worker, daemon=True, name="WindowsToastWorker").start()
    return True

def send_ntfy_notification(
    topic: str,
    title: str,
    message: str,
    priority: str = "high",
    tags: str = "warning,wifi",
    fix_advice: str = ""
) -> bool:
    """Send free, instant push notification to phone/desktop via ntfy.sh with fix advice."""
    if not topic:
        return False
    url = f"https://ntfy.sh/{urllib.parse.quote(topic.strip())}"
    
    full_message = message
    if fix_advice:
        full_message = f"{message}\n\n🛠️ HOW TO FIX:\n{fix_advice}"

    try:
        req = urllib.request.Request(
            url,
            data=full_message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": tags,
                "User-Agent": "NetPulse-Pro",
                "Click": "http://127.0.0.1:8765",
                "Actions": "view, Open NetPulse Dashboard, http://127.0.0.1:8765"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"ntfy notification failed: {e}")
        return False

def send_discord_notification(
    webhook_url: str,
    title: str,
    message: str,
    color: int = 16711680,
    footer_text: str = "NetPulse Pro • 24/7 Network Monitor",
    root_cause: str = "",
    fix_advice: str = "",
    recommended_action: str = ""
) -> bool:
    """Send alert to a Discord channel via Webhook with rich diagnostic and fix fields."""
    if not webhook_url or not webhook_url.strip():
        return False

    fields = []
    if root_cause:
        fields.append({"name": "🔍 Root Cause Diagnosis", "value": f"**{root_cause}**", "inline": False})
    if fix_advice:
        fields.append({"name": "🛠️ How to Fix (Immediate Steps)", "value": fix_advice, "inline": False})
    if recommended_action:
        fields.append({
            "name": "⚡ Quick Fix Action",
            "value": f"Open NetPulse Dashboard at `http://127.0.0.1:8765` to run `{recommended_action}`",
            "inline": False
        })

    embed = {
        "title": title,
        "description": message,
        "color": color,
        "footer": {"text": footer_text}
    }
    if fields:
        embed["fields"] = fields

    payload = {"embeds": [embed]}
    try:
        req = urllib.request.Request(
            webhook_url.strip(),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "NetPulse-Pro/1.0"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status in (200, 204)
    except Exception as e:
        logger.error(f"Discord notification failed: {e}")
        return False

def get_discord_webhooks(settings: Dict[str, Any]) -> list:
    """
    Extract multiple Discord webhooks from settings dictionary.
    Returns list of dicts: [{'name': '...', 'url': '...'}]
    """
    results = []
    seen_urls = set()

    raw_webhooks = settings.get("discord_webhooks")
    if raw_webhooks:
        if isinstance(raw_webhooks, str):
            try:
                parsed = json.loads(raw_webhooks)
                if isinstance(parsed, list):
                    for idx, item in enumerate(parsed, 1):
                        if isinstance(item, dict):
                            url = str(item.get("url", "")).strip()
                            name = str(item.get("name", "")).strip()
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                results.append({"name": name or f"Webhook #{idx}", "url": url})
                        elif isinstance(item, str) and item.strip():
                            url = item.strip()
                            if url not in seen_urls:
                                seen_urls.add(url)
                                results.append({"name": f"Webhook #{idx}", "url": url})
            except Exception:
                for line in raw_webhooks.replace(",", "\n").splitlines():
                    url = line.strip()
                    if url and url.startswith("http") and url not in seen_urls:
                        seen_urls.add(url)
                        results.append({"name": f"Webhook #{len(results)+1}", "url": url})
        elif isinstance(raw_webhooks, list):
            for idx, item in enumerate(raw_webhooks, 1):
                if isinstance(item, dict):
                    url = str(item.get("url", "")).strip()
                    name = str(item.get("name", "")).strip()
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append({"name": name or f"Webhook #{idx}", "url": url})
                elif isinstance(item, str) and item.strip():
                    url = item.strip()
                    if url not in seen_urls:
                        seen_urls.add(url)
                        results.append({"name": f"Webhook #{idx}", "url": url})

    legacy_url = str(settings.get("discord_webhook", "")).strip()
    if legacy_url and legacy_url not in seen_urls:
        seen_urls.add(legacy_url)
        results.append({"name": "Primary Webhook", "url": legacy_url})

    return results

def test_single_discord_webhook(webhook_url: str) -> Dict[str, Any]:
    """Test a specific Discord webhook URL directly with instant feedback."""
    if not webhook_url or not webhook_url.strip():
        return {"success": False, "message": "Webhook URL cannot be empty."}
    
    url = webhook_url.strip()
    if not (url.startswith("https://discord.com/api/webhooks/") or url.startswith("https://discordapp.com/api/webhooks/")):
        return {"success": False, "message": "Invalid Discord Webhook URL. It must start with https://discord.com/api/webhooks/..."}

    title = "NetPulse Pro: Test Webhook Alert"
    message = "Discord Webhook connection verified successfully! NetPulse sentry alerts and drop-fix instructions will be posted here."
    ok = send_discord_notification(
        url,
        title,
        message,
        color=3447003,
        footer_text="NetPulse Pro • Webhook Verification",
        root_cause="Simulation Test Passed",
        fix_advice="Everything is operational. NetPulse is actively monitoring your latency and connection drops."
    )
    if ok:
        return {"success": True, "message": "Discord test notification successfully delivered to your channel!"}
    else:
        return {"success": False, "message": "Failed to send notification to Discord. Please check if the Webhook URL was deleted or revoked."}

def send_telegram_notification(bot_token: str, chat_id: str, message: str, root_cause: str = "", fix_advice: str = "") -> bool:
    """Send alert via Telegram Bot."""
    if not bot_token or not chat_id:
        return False
    
    text = message
    if root_cause:
        text += f"\n\n*Root Cause:* {root_cause}"
    if fix_advice:
        text += f"\n\n*🛠️ How to Fix:*\n{fix_advice}"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error(f"Telegram notification failed: {e}")
        return False

def broadcast_alert(
    title: str,
    message: str,
    is_recovery: bool = False,
    root_cause: str = "",
    fix_advice: str = "",
    recommended_action: str = ""
) -> Dict[str, Any]:
    """Broadcast alert with root cause and fix instructions through all enabled channels."""
    settings = get_all_settings()
    results: Dict[str, Any] = {}

    priority = "default" if is_recovery else "high"
    tags = "white_check_mark,network" if is_recovery else "rotating_light,wrench,warning"
    discord_color = 65280 if is_recovery else 16711680

    # 1. Native Windows Desktop Toast Notification
    if settings.get("windows_toast_enabled", "1") == "1" and platform.system() == "Windows":
        results["windows_toast"] = send_windows_toast(title, message, fix_advice)

    # 2. ntfy.sh (Phone & Desktop push)
    if settings.get("ntfy_enabled") == "1" and settings.get("ntfy_topic"):
        topic = settings.get("ntfy_topic")
        results["ntfy"] = send_ntfy_notification(
            topic, title, message, priority=priority, tags=tags, fix_advice=fix_advice
        )

    # 3. Discord (Multiple Webhooks Supported)
    if settings.get("discord_enabled") == "1":
        webhooks = get_discord_webhooks(settings)
        delivered_count = 0
        for wh in webhooks:
            wh_url = wh.get("url", "")
            wh_name = wh.get("name", "Discord")
            if wh_url:
                ok = send_discord_notification(
                    wh_url,
                    title,
                    message,
                    color=discord_color,
                    footer_text=f"NetPulse Pro • {wh_name}",
                    root_cause=root_cause,
                    fix_advice=fix_advice,
                    recommended_action=recommended_action
                )
                if ok:
                    delivered_count += 1
        if webhooks:
            results["discord"] = delivered_count > 0
            results["discord_delivered"] = delivered_count
            results["discord_total"] = len(webhooks)

    # 4. Telegram
    if settings.get("telegram_enabled") == "1" and settings.get("telegram_bot_token") and settings.get("telegram_chat_id"):
        results["telegram"] = send_telegram_notification(
            settings.get("telegram_bot_token"),
            settings.get("telegram_chat_id"),
            f"*{title}*\n\n{message}",
            root_cause=root_cause,
            fix_advice=fix_advice
        )

    return results

def send_test_notification() -> Dict[str, Any]:
    """Send a test notification to verify user configuration and show fix instruction format."""
    title = "NetPulse Pro: Test Drop Alert & Fix Advice"
    message = "Test alert delivered! When a connection drop occurs, NetPulse automatically diagnoses the cause and sends immediate fix instructions like below."
    root_cause = "Sample Test: Wi-Fi Driver Power Suspend"
    fix_advice = "1. Click 'Disable Wi-Fi Power Saving' in NetPulse. 2. Set Roaming Aggressiveness to Lowest. 3. Avoid power-saving sleep timeouts while gaming."
    
    results = broadcast_alert(
        title,
        message,
        is_recovery=False,
        root_cause=root_cause,
        fix_advice=fix_advice,
        recommended_action="fix_power_save"
    )
    
    delivered_channels = []
    if results.get("windows_toast"):
        delivered_channels.append("Windows Desktop Toast")
    if results.get("ntfy"):
        delivered_channels.append("ntfy.sh (Phone/PC)")
    if results.get("discord"):
        count = results.get("discord_delivered", 1)
        delivered_channels.append(f"{count} Discord Webhook{'s' if count != 1 else ''}")
    if results.get("telegram"):
        delivered_channels.append("Telegram")

    if delivered_channels:
        return {
            "success": True,
            "channels": results,
            "message": f"Test alert with fix advice delivered to: {', '.join(delivered_channels)}!"
        }
    else:
        return {
            "success": False,
            "channels": results,
            "message": "No notification channels succeeded. Please check your notification settings."
        }

