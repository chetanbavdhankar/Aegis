"""
AEGIS Database Layer — Thread-safe SQLite with WAL mode.

Schema:
  - users:    one row per Telegram user (with contact info)
  - alerts:   one ACTIVE alert per user (consolidated), severity = max of all messages
  - messages: individual distress messages linked to an alert (chat history)
"""
import sqlite3
import threading
from datetime import datetime, timezone
from backend.config import DB_PATH

_write_lock = threading.RLock()
_SEV_LABELS = {1: "INFO", 2: "LOW", 3: "MODERATE", 4: "HIGH", 5: "CRITICAL"}


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id      INTEGER PRIMARY KEY,
            first_name   TEXT DEFAULT '',
            last_name    TEXT DEFAULT '',
            username     TEXT DEFAULT '',
            phone_number TEXT DEFAULT '',
            language     TEXT DEFAULT 'Unknown',
            created_at   TEXT DEFAULT (datetime('now'))
        );
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id              INTEGER NOT NULL,
            lat                  REAL,
            lng                  REAL,
            incident_type        TEXT DEFAULT 'unknown',
            severity             INTEGER DEFAULT 1,
            severity_label       TEXT DEFAULT 'INFO',
            summary_en           TEXT DEFAULT '',
            summary_local        TEXT DEFAULT '',
            detected_language    TEXT DEFAULT '',
            people_count         TEXT DEFAULT '',
            trapped              INTEGER DEFAULT 0,
            needs                TEXT DEFAULT '',
            verification_status  TEXT DEFAULT 'pending',
            verification_summary TEXT DEFAULT '',
            verification_score   INTEGER DEFAULT 0,
            status               TEXT DEFAULT 'active',
            location_name        TEXT DEFAULT '',
            message_count        INTEGER DEFAULT 0,
            feedback             TEXT DEFAULT '',
            timestamp            TEXT DEFAULT (datetime('now'))
        );
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id          INTEGER NOT NULL,
            chat_id           INTEGER NOT NULL,
            raw_text          TEXT NOT NULL DEFAULT '',
            incident_type     TEXT DEFAULT 'unknown',
            severity          INTEGER DEFAULT 1,
            severity_label    TEXT DEFAULT 'INFO',
            summary_en        TEXT DEFAULT '',
            summary_local     TEXT DEFAULT '',
            detected_language TEXT DEFAULT '',
            people_count      TEXT DEFAULT '',
            trapped           INTEGER DEFAULT 0,
            needs             TEXT DEFAULT '',
            timestamp         TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (alert_id) REFERENCES alerts(id)
        );
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS alert_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id    INTEGER NOT NULL,
            action      TEXT NOT NULL,
            details     TEXT DEFAULT '',
            source      TEXT DEFAULT 'system',
            timestamp   TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (alert_id) REFERENCES alerts(id)
        );
    """)

    conn.commit()

    # Migration for existing DBs
    _migrate(c, conn, "users", [
        ("first_name", "''"), ("last_name", "''"), ("username", "''"),
    ])
    _migrate(c, conn, "alerts", [
        ("status", "'active'"), ("location_name", "''"),
        ("message_count", "0"), ("feedback", "''"),
    ])
    conn.close()


def _migrate(cursor, conn, table: str, columns: list[tuple[str, str]]):
    for col, default in columns:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT DEFAULT {default}")
            conn.commit()
        except sqlite3.OperationalError:
            pass


# ── Audit Log ────────────────────────────────────────────────────────────────

def log_alert_action(alert_id: int, action: str, details: str = "", source: str = "system") -> None:
    """Record an audit event for a specific alert."""
    now = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        conn = get_connection()
        conn.execute(
            "INSERT INTO alert_logs (alert_id, action, details, source, timestamp) VALUES (?, ?, ?, ?, ?)",
            (alert_id, action, details, source, now)
        )
        conn.commit()
        conn.close()


def get_alert_logs(alert_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM alert_logs WHERE alert_id = ? ORDER BY timestamp DESC", (alert_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ── User CRUD ────────────────────────────────────────────────────────────────

def upsert_user(
    chat_id: int,
    language: str = "Unknown",
    first_name: str = "",
    last_name: str = "",
    username: str = "",
    phone_number: str = "",
) -> None:
    with _write_lock:
        conn = get_connection()
        conn.execute(
            """INSERT INTO users (chat_id, language, first_name, last_name, username, phone_number)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET
                   language = excluded.language,
                   first_name = CASE WHEN excluded.first_name != '' THEN excluded.first_name ELSE users.first_name END,
                   last_name = CASE WHEN excluded.last_name != '' THEN excluded.last_name ELSE users.last_name END,
                   username = CASE WHEN excluded.username != '' THEN excluded.username ELSE users.username END,
                   phone_number = CASE WHEN excluded.phone_number != '' THEN excluded.phone_number ELSE users.phone_number END""",
            (chat_id, language, first_name, last_name, username, phone_number),
        )
        conn.commit()
        conn.close()


def update_user_phone(chat_id: int, phone_number: str) -> None:
    with _write_lock:
        conn = get_connection()
        conn.execute("UPDATE users SET phone_number = ? WHERE chat_id = ?", (phone_number, chat_id))
        conn.commit()
        conn.close()


def get_user(chat_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Alert + Message consolidation ────────────────────────────────────────────

def get_active_alert_for_user(chat_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        """SELECT * FROM alerts
           WHERE chat_id = ? AND status != 'resolved'
           ORDER BY id DESC LIMIT 1""",
        (chat_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def is_duplicate_message(alert_id: int, raw_text: str) -> bool:
    """Check if the exact same text was already added to this alert (dedup)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM messages WHERE alert_id = ? AND raw_text = ? LIMIT 1",
        (alert_id, raw_text),
    ).fetchone()
    conn.close()
    return row is not None


def create_alert_with_message(
    chat_id: int,
    raw_text: str,
    incident_type: str = "unknown",
    severity: int = 1,
    severity_label: str = "INFO",
    summary_en: str = "",
    summary_local: str = "",
    detected_language: str = "",
    people_count: str = "",
    trapped: bool = False,
    needs: str = "",
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        conn = get_connection()
        cursor = conn.execute(
            """INSERT INTO alerts
               (chat_id, incident_type, severity, severity_label,
                summary_en, summary_local, detected_language,
                people_count, trapped, needs, message_count, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (chat_id, incident_type, severity, severity_label,
             summary_en, summary_local, detected_language,
             people_count, int(trapped), needs, now),
        )
        alert_id = cursor.lastrowid
        conn.execute(
            """INSERT INTO messages
               (alert_id, chat_id, raw_text, incident_type, severity,
                severity_label, summary_en, summary_local, detected_language,
                people_count, trapped, needs, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (alert_id, chat_id, raw_text, incident_type, severity,
             severity_label, summary_en, summary_local, detected_language,
             people_count, int(trapped), needs, now),
        )
        conn.execute(
            "INSERT INTO alert_logs (alert_id, action, details, source, timestamp) VALUES (?, ?, ?, ?, ?)",
            (alert_id, "alert_created", f"Severity: {severity}, Type: {incident_type}", "user", now)
        )
        conn.commit()
        conn.close()
        return alert_id


def append_message_to_alert(
    alert_id: int, chat_id: int, raw_text: str,
    incident_type: str = "unknown", severity: int = 1,
    severity_label: str = "INFO", summary_en: str = "",
    summary_local: str = "", detected_language: str = "",
    people_count: str = "", trapped: bool = False, needs: str = "",
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        conn = get_connection()
        cursor = conn.execute(
            """INSERT INTO messages
               (alert_id, chat_id, raw_text, incident_type, severity,
                severity_label, summary_en, summary_local, detected_language,
                people_count, trapped, needs, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (alert_id, chat_id, raw_text, incident_type, severity,
             severity_label, summary_en, summary_local, detected_language,
             people_count, int(trapped), needs, now),
        )
        msg_id = cursor.lastrowid

        # Promote alert headline from highest-severity message
        conn.execute(
            """UPDATE alerts SET
                message_count = (SELECT COUNT(*) FROM messages WHERE alert_id = ?),
                severity = (SELECT MAX(severity) FROM messages WHERE alert_id = ?),
                severity_label = (SELECT severity_label FROM messages WHERE alert_id = ? ORDER BY severity DESC, id DESC LIMIT 1),
                incident_type = (SELECT incident_type FROM messages WHERE alert_id = ? ORDER BY severity DESC, id DESC LIMIT 1),
                summary_en = (SELECT summary_en FROM messages WHERE alert_id = ? ORDER BY severity DESC, id DESC LIMIT 1),
                summary_local = (SELECT summary_local FROM messages WHERE alert_id = ? ORDER BY severity DESC, id DESC LIMIT 1),
                detected_language = (SELECT detected_language FROM messages WHERE alert_id = ? ORDER BY severity DESC, id DESC LIMIT 1),
                people_count = (SELECT people_count FROM messages WHERE alert_id = ? ORDER BY severity DESC, id DESC LIMIT 1),
                trapped = (SELECT MAX(trapped) FROM messages WHERE alert_id = ?),
                needs = (SELECT GROUP_CONCAT(DISTINCT needs) FROM messages WHERE alert_id = ? AND needs != '')
               WHERE id = ?""",
            (alert_id,) * 10 + (alert_id,),
        )
        conn.execute(
            "INSERT INTO alert_logs (alert_id, action, details, source, timestamp) VALUES (?, ?, ?, ?, ?)",
            (alert_id, "message_appended", f"Msg: {raw_text[:100]}", "user", now)
        )
        conn.commit()
        conn.close()
        return msg_id


def get_messages_for_alert(alert_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM messages WHERE alert_id = ? ORDER BY timestamp ASC",
        (alert_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ── Location ─────────────────────────────────────────────────────────────────

def update_alert_location(alert_id: int, lat: float, lng: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        conn = get_connection()
        conn.execute("UPDATE alerts SET lat = ?, lng = ? WHERE id = ?", (lat, lng, alert_id))
        conn.execute(
            "INSERT INTO alert_logs (alert_id, action, details, source, timestamp) VALUES (?, ?, ?, ?, ?)",
            (alert_id, "location_updated", f"Lat: {lat}, Lng: {lng}", "user", now)
        )
        conn.commit()
        conn.close()


def update_alert_location_name(alert_id: int, location_name: str) -> None:
    with _write_lock:
        conn = get_connection()
        conn.execute("UPDATE alerts SET location_name = ? WHERE id = ?", (location_name, alert_id))
        conn.commit()
        conn.close()


def update_latest_alert_location(chat_id: int, lat: float, lng: float) -> int | None:
    now = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        conn = get_connection()
        row = conn.execute(
            """SELECT id FROM alerts
               WHERE chat_id = ? AND status != 'resolved'
               ORDER BY id DESC LIMIT 1""",
            (chat_id,),
        ).fetchone()
        if row:
            conn.execute("UPDATE alerts SET lat = ?, lng = ? WHERE id = ?", (lat, lng, row["id"]))
            conn.execute(
                "INSERT INTO alert_logs (alert_id, action, details, source, timestamp) VALUES (?, ?, ?, ?, ?)",
                (row["id"], "location_updated", f"Lat: {lat}, Lng: {lng}", "user", now)
            )
            conn.commit()
            conn.close()
            return row["id"]
        conn.close()
        return None


# ── Verification ─────────────────────────────────────────────────────────────

def update_alert_verification(alert_id: int, status: str, summary: str, score: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        conn = get_connection()
        conn.execute(
            """UPDATE alerts SET verification_status = ?, verification_summary = ?,
                   verification_score = ? WHERE id = ?""",
            (status, summary, score, alert_id),
        )
        conn.execute(
            "INSERT INTO alert_logs (alert_id, action, details, source, timestamp) VALUES (?, ?, ?, ?, ?)",
            (alert_id, "verification_updated", f"Status: {status}, Score: {score}", "agent", now)
        )
        conn.commit()
        conn.close()


# ── Status & Feedback ────────────────────────────────────────────────────────

def update_alert_status(alert_id: int, new_status: str, new_severity: int = None) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        conn = get_connection()
        if new_severity is not None:
            sev_label = _SEV_LABELS.get(new_severity, "INFO")
            conn.execute(
                "UPDATE alerts SET status = ?, severity = ?, severity_label = ? WHERE id = ?",
                (new_status, new_severity, sev_label, alert_id),
            )
            details = f"Status: {new_status}, Severity: {new_severity}"
        else:
            conn.execute("UPDATE alerts SET status = ? WHERE id = ?", (new_status, alert_id))
            details = f"Status: {new_status}"
            
        conn.execute(
            "INSERT INTO alert_logs (alert_id, action, details, source, timestamp) VALUES (?, ?, ?, ?, ?)",
            (alert_id, "status_changed", details, "dashboard", now)
        )
        conn.commit()
        conn.close()
        return True


def update_alert_feedback(alert_id: int, feedback: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        conn = get_connection()
        conn.execute("UPDATE alerts SET feedback = ? WHERE id = ?", (feedback, alert_id))
        conn.execute(
            "INSERT INTO alert_logs (alert_id, action, details, source, timestamp) VALUES (?, ?, ?, ?, ?)",
            (alert_id, "feedback_received", feedback, "user", now)
        )
        conn.commit()
        conn.close()


# ── Queries ──────────────────────────────────────────────────────────────────

def get_alert_by_id(alert_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_alerts() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM alerts ORDER BY timestamp DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_user_language(chat_id: int) -> str:
    conn = get_connection()
    row = conn.execute("SELECT language FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
    conn.close()
    return row["language"] if row else "Unknown"


def get_all_users() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return [dict(row) for row in rows]
