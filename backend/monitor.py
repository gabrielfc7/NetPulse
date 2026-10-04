import time
import threading
import logging
from typing import Optional, Dict, Any

from .db import record_metric, create_incident, resolve_incident, get_all_settings
from .ping_analyzer import ping_host
from .utils import get_default_gateway
from .notifier import broadcast_alert
from .optimizer import flush_dns, clear_arp_cache, fix_wifi_power_saving, renew_dhcp_lease
from .drop_doctor import diagnose_immediate_drop, check_recent_wlan_disconnect

logger = logging.getLogger("NetPulseMonitor")

class NetworkMonitorDaemon:
    def __init__(self, interval_sec: int = 6):
        self.interval_sec = interval_sec
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # State tracking
        self.current_incident_id: Optional[int] = None
        self.current_diagnosis: Optional[Dict[str, Any]] = None
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_high_latency_alert_time = 0
        self.last_wlan_event_ts = time.time()
        self.latest_status = {
            "status": "Healthy",
            "gateway_ms": 1.0,
            "internet_ms": 25.0,
            "loss_percent": 0.0,
            "jitter_ms": 0.5,
            "root_cause": "",
            "fix_advice": "",
            "recommended_action": "",
            "action_button": "",
            "updated_at": time.time()
        }

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="NetPulseMonitorDaemon")
        self.thread.start()
        logger.info("[NetPulse Monitor] 24/7 Background Network Monitor started.")

    def stop(self):
        self.running = False

    def _run_loop(self):
        time.sleep(2.0)

        while self.running:
            try:
                self._check_network_health()
            except Exception as e:
                logger.error(f"[NetPulse Monitor] Error in loop: {e}")

            time.sleep(self.interval_sec)

    def _check_network_health(self):
        gw = get_default_gateway()
        settings = get_all_settings()

        # Ultra-lightweight ping (2 packets each)
        gw_res = ping_host(gw, count=2, timeout_ms=600)
        cf_res = ping_host("1.1.1.1", count=2, timeout_ms=800)

        gw_ms = gw_res.get("avg_ms", 0.0)
        cf_ms = cf_res.get("avg_ms", 0.0)
        gw_loss = gw_res.get("loss_percent", 0.0)
        cf_loss = cf_res.get("loss_percent", 0.0)
        loss = max(gw_loss, cf_loss)
        jitter = max(gw_res.get("jitter_ms", 0.0), cf_res.get("jitter_ms", 0.0))

        is_failed = (loss >= 90.0) or (cf_res.get("received", 0) == 0)

        # Record in database
        record_metric(gw_ms, cf_ms, loss, jitter, is_failed)

        # Handle Drops & Outages
        if is_failed:
            self.consecutive_failures += 1
            self.consecutive_successes = 0

            # Trigger incident and immediate advisory message:
            # - After 2 consecutive failed probes (~12s)
            # - OR on 1st probe if 100% loss across BOTH gateway and internet (hard drop)
            hard_drop = (gw_loss >= 95.0 and cf_loss >= 95.0)
            should_trigger = (self.consecutive_failures == 2) or (self.consecutive_failures == 1 and hard_drop)

            if should_trigger and not self.current_incident_id:
                # Immediate diagnosis & fix generation
                diag = diagnose_immediate_drop(gw_loss, cf_loss, gw_ms, cf_ms, gw_ip=gw)
                self.current_diagnosis = diag

                self.current_incident_id = create_incident(
                    incident_type="Connection Drop",
                    root_cause=diag["root_cause"],
                    fix_advice=diag["fix_advice"],
                    recommended_action=diag.get("recommended_action", "")
                )

                self.latest_status = {
                    "status": "Critical Drop",
                    "root_cause": diag["root_cause"],
                    "fix_advice": diag["fix_advice"],
                    "recommended_action": diag.get("recommended_action", ""),
                    "action_button": diag.get("action_button", "Fix Now"),
                    "gateway_ms": gw_ms,
                    "internet_ms": cf_ms,
                    "loss_percent": loss,
                    "jitter_ms": jitter,
                    "updated_at": time.time()
                }

                # Send Notification right after detection with exact fix advice
                if settings.get("alert_on_drop") == "1":
                    alert_title = f"NetPulse Alert: {diag['root_cause']}"
                    alert_body = (
                        f"Connection drop detected (Loss: {loss:.0f}%).\n\n"
                        f"🛠️ HOW TO FIX:\n{diag['fix_advice']}"
                    )
                    broadcast_alert(
                        title=alert_title,
                        message=alert_body,
                        is_recovery=False,
                        root_cause=diag["root_cause"],
                        fix_advice=diag["fix_advice"],
                        recommended_action=diag.get("recommended_action", "")
                    )

                # Autonomous Non-Disruptive Self-Healing
                if settings.get("auto_heal_enabled") == "1":
                    self._attempt_autonomous_heal(diag.get("recommended_action"))

            elif self.current_diagnosis:
                # Keep status updated while outage continues
                diag = self.current_diagnosis
                self.latest_status = {
                    "status": "Critical Drop",
                    "root_cause": diag.get("root_cause", ""),
                    "fix_advice": diag.get("fix_advice", ""),
                    "recommended_action": diag.get("recommended_action", ""),
                    "action_button": diag.get("action_button", "Fix Now"),
                    "gateway_ms": gw_ms,
                    "internet_ms": cf_ms,
                    "loss_percent": loss,
                    "jitter_ms": jitter,
                    "updated_at": time.time()
                }

        else:
            self.consecutive_successes += 1
            self.consecutive_failures = 0

            # If recovering from an active incident
            if self.current_incident_id and self.consecutive_successes >= 2:
                resolve_incident(self.current_incident_id, auto_healed=True)

                diag = self.current_diagnosis or {}
                advice_summary = diag.get("short_fix") or "Connection fully restored."

                if settings.get("alert_on_drop") == "1":
                    broadcast_alert(
                        title="NetPulse: Connection Restored",
                        message=(
                            f"Your network connection is back online. Internet latency is {cf_ms:.1f}ms (0% loss).\n\n"
                            f"💡 PREVENTION TIP:\n{advice_summary}"
                        ),
                        is_recovery=True,
                        root_cause=diag.get("root_cause", ""),
                        fix_advice=diag.get("fix_advice", ""),
                        recommended_action=diag.get("recommended_action", "")
                    )

                self.current_incident_id = None
                self.current_diagnosis = None

            # High Latency Alert (with 10-minute cooldown)
            high_lat_threshold = float(settings.get("high_latency_threshold_ms", "80"))
            now = time.time()
            if cf_ms >= high_lat_threshold and (now - self.last_high_latency_alert_time > 600):
                if settings.get("alert_on_high_latency") == "1":
                    broadcast_alert(
                        title="NetPulse Warning: High Latency Spike",
                        message=(
                            f"Internet latency spiked to {cf_ms:.1f}ms (Threshold: {high_lat_threshold}ms). Jitter: {jitter:.1f}ms.\n\n"
                            "🛠️ HOW TO FIX:\nClose bandwidth hogs in Process Monitor or check Bufferbloat tab."
                        ),
                        is_recovery=False,
                        root_cause="High Latency / Bufferbloat",
                        fix_advice="Close high-bandwidth background apps in Process Monitor."
                    )
                    self.last_high_latency_alert_time = now

            self.latest_status = {
                "status": "High Latency" if cf_ms > 100 else "Healthy",
                "gateway_ms": gw_ms,
                "internet_ms": cf_ms,
                "loss_percent": loss,
                "jitter_ms": jitter,
                "root_cause": "",
                "fix_advice": "",
                "recommended_action": "",
                "action_button": "",
                "updated_at": time.time()
            }

    def _attempt_autonomous_heal(self, recommended_action: Optional[str] = None):
        """Perform autonomous, non-disruptive local repairs."""
        try:
            logger.info("[NetPulse Monitor] Running autonomous self-healing (flushing DNS & clearing ARP)...")
            flush_dns()
            clear_arp_cache()

            if recommended_action == "fix_power_save":
                logger.info("[NetPulse Monitor] Auto-healing: Applying Wi-Fi power-save fix...")
                fix_wifi_power_saving()
            elif recommended_action == "renew_dhcp":
                logger.info("[NetPulse Monitor] Auto-healing: Renewing DHCP lease...")
                renew_dhcp_lease()
        except Exception as e:
            logger.error(f"[NetPulse Monitor] Self-heal attempt error: {e}")

# Global daemon instance
monitor_daemon = NetworkMonitorDaemon(interval_sec=6)
