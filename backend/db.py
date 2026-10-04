import sqlite3
import os
import time
import json
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, List, Any, Optional

logger = logging.getLogger("NetPulseDB")

DB_PATH = Path(os.environ.get("NETPULSE_DATA_DIR", Path(__file__).resolve().parent.parent)) / "netpulse.db"

def get_connection() -> sqlite3.Connection:
    """
    Create a SQLite connection configured for concurrent access.
    Sets timeout, WAL journal mode, and busy timeout.
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception as e:
        logger.warning(f"Could not configure SQLite PRAGMAs: {e}")
    return conn

@contextmanager
def db_transaction(retries: int = 5, initial_delay: float = 0.05):
    """
    Context manager for write transactions.
    Automatically commits on success, rolls back on error, and closes connection.
    Implements exponential backoff retry on database locked / busy errors.
    """
    delay = initial_delay
    for attempt in range(retries):
        conn = None
        try:
            conn = get_connection()
            yield conn
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            err_msg = str(e).lower()
            if "locked" in err_msg or "busy" in err_msg:
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None
                if attempt == retries - 1:
                    logger.error(f"SQLite transaction failed after {retries} retries: {e}")
                    raise
                time.sleep(delay)
                delay *= 2
            else:
                if conn:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                raise
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

@contextmanager
def db_read(retries: int = 5, initial_delay: float = 0.05):
    """
    Context manager for read queries.
    Safely closes connection and retries on busy.
    """
    delay = initial_delay
    for attempt in range(retries):
        conn = None
        try:
            conn = get_connection()
            yield conn
            return
        except sqlite3.OperationalError as e:
            err_msg = str(e).lower()
            if "locked" in err_msg or "busy" in err_msg:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None
                if attempt == retries - 1:
                    logger.error(f"SQLite read query failed after {retries} retries: {e}")
                    raise
                time.sleep(delay)
                delay *= 2
            else:
                raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

# Pruning configuration: prune at most once an hour instead of every write
_last_prune_time: float = 0.0
_PRUNE_INTERVAL_SEC: float = 3600.0

def init_db():
    """Initialize SQLite tables for metrics, incidents, and settings with WAL mode and indices."""
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")

        # Telemetry metrics history table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            gateway_ms REAL,
            internet_ms REAL,
            loss_percent REAL,
            jitter_ms REAL,
            is_down INTEGER DEFAULT 0
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_is_down ON metrics(is_down, timestamp)")

        # Incidents / Outages history table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time REAL NOT NULL,
            end_time REAL,
            duration_sec REAL,
            incident_type TEXT NOT NULL,
            root_cause TEXT,
            fix_advice TEXT,
            recommended_action TEXT,
            resolved INTEGER DEFAULT 0,
            auto_healed INTEGER DEFAULT 0,
            notified INTEGER DEFAULT 0
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_start ON incidents(start_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_start_desc ON incidents(start_time DESC)")

        # Ensure schema migrations for existing databases
        try:
            cursor.execute("ALTER TABLE incidents ADD COLUMN fix_advice TEXT")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE incidents ADD COLUMN recommended_action TEXT")
        except Exception:
            pass

        # User Notification & Auto-heal Settings
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        # Populate default settings if not exists
        defaults = {
            "ntfy_topic": "netpulse-alerts",
            "ntfy_enabled": "1",
            "windows_toast_enabled": "1",
            "discord_webhook": "",
            "discord_webhooks": "[]",
            "discord_enabled": "0",
            "telegram_bot_token": "",
            "telegram_chat_id": "",
            "telegram_enabled": "0",
            "auto_heal_enabled": "1",
            "alert_on_drop": "1",
            "alert_on_high_latency": "1",
            "high_latency_threshold_ms": "80",
            "loss_threshold_percent": "15"
        }

        for k, v in defaults.items():
            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

# Metrics operations
def record_metric(gateway_ms: float, internet_ms: float, loss_percent: float, jitter_ms: float, is_down: bool):
    global _last_prune_time
    now = time.time()
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO metrics (timestamp, gateway_ms, internet_ms, loss_percent, jitter_ms, is_down)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (now, gateway_ms, internet_ms, loss_percent, jitter_ms, 1 if is_down else 0))

        # Lightweight periodic pruning: only clean once every hour to avoid full scans & write locks on every tick
        if (now - _last_prune_time) >= _PRUNE_INTERVAL_SEC:
            cutoff = now - (7 * 86400)
            cursor.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,))
            _last_prune_time = now

def get_metrics_history(hours: int = 1) -> List[Dict[str, Any]]:
    cutoff = time.time() - (hours * 3600)
    with db_read() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, gateway_ms, internet_ms, loss_percent, jitter_ms, is_down
            FROM metrics
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
        """, (cutoff,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

# Incident operations
def create_incident(incident_type: str, root_cause: str, fix_advice: str = "", recommended_action: str = "") -> int:
    now = time.time()
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO incidents (start_time, incident_type, root_cause, fix_advice, recommended_action, resolved, auto_healed, notified)
            VALUES (?, ?, ?, ?, ?, 0, 0, 0)
        """, (now, incident_type, root_cause, fix_advice, recommended_action))
        return cursor.lastrowid

def resolve_incident(incident_id: int, auto_healed: bool = False):
    now = time.time()
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT start_time FROM incidents WHERE id = ?", (incident_id,))
        row = cursor.fetchone()
        if row:
            duration = round(now - row["start_time"], 1)
            cursor.execute("""
                UPDATE incidents
                SET end_time = ?, duration_sec = ?, resolved = 1, auto_healed = ?
                WHERE id = ?
            """, (now, duration, 1 if auto_healed else 0, incident_id))

def mark_incident_notified(incident_id: int):
    with db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE incidents SET notified = 1 WHERE id = ?", (incident_id,))

def get_recent_incidents(limit: int = 25) -> List[Dict[str, Any]]:
    with db_read() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, start_time, end_time, duration_sec, incident_type, root_cause, fix_advice, recommended_action, resolved, auto_healed, notified
            FROM incidents
            ORDER BY start_time DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

# Settings operations
def get_all_settings() -> Dict[str, str]:
    with db_read() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        rows = cursor.fetchall()
        return {r["key"]: r["value"] for r in rows}

def update_settings(updates: Dict[str, Any]):
    with db_transaction() as conn:
        cursor = conn.cursor()
        for k, v in updates.items():
            if isinstance(v, (list, dict)):
                v = json.dumps(v)
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))

# Initialize on module load
init_db()
