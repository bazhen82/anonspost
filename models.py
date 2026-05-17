from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from config import DATABASE_PATH, FLASK_SECRET_KEY


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_unsubscribe_token(email: str) -> str:
    digest = hashlib.sha256(f"{email.lower()}:{FLASK_SECRET_KEY}".encode()).hexdigest()
    return digest[:32]


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name TEXT DEFAULT '',
                unsubscribed INTEGER NOT NULL DEFAULT 0,
                unsubscribe_token TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL DEFAULT '',
                body_text TEXT NOT NULL DEFAULT '',
                link_url TEXT NOT NULL DEFAULT '',
                image_path TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                sent_at TEXT
            );

            CREATE TABLE IF NOT EXISTS delivery_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                recipient_id INTEGER,
                email TEXT NOT NULL,
                name TEXT DEFAULT '',
                status TEXT NOT NULL,
                error_message TEXT DEFAULT '',
                sent_at TEXT NOT NULL,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id),
                FOREIGN KEY (recipient_id) REFERENCES recipients(id)
            );

            CREATE INDEX IF NOT EXISTS idx_delivery_campaign
                ON delivery_log(campaign_id);
            """
        )


def count_unsubscribed() -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM recipients WHERE unsubscribed = 1"
        ).fetchone()
        return int(row["c"])


def count_active_recipients() -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM recipients WHERE unsubscribed = 0"
        ).fetchone()
        return int(row["c"])


def list_recipients_preview(limit: int = 20) -> list[sqlite3.Row]:
    with get_db() as conn:
        return list(
            conn.execute(
                """
                SELECT email, name, unsubscribed, created_at
                FROM recipients
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        )


def upsert_recipient(email: str, name: str = "") -> tuple[str, bool]:
    """Returns action: 'added' | 'updated' | 'skipped_unsubscribed'."""
    email = email.strip().lower()
    token = make_unsubscribe_token(email)
    now = _utc_now()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id, unsubscribed FROM recipients WHERE email = ?",
            (email,),
        ).fetchone()
        if existing:
            if existing["unsubscribed"]:
                return "skipped_unsubscribed", False
            conn.execute(
                "UPDATE recipients SET name = ? WHERE id = ?",
                (name, existing["id"]),
            )
            return "updated", True
        conn.execute(
            """
            INSERT INTO recipients (email, name, unsubscribed, unsubscribe_token, created_at)
            VALUES (?, ?, 0, ?, ?)
            """,
            (email, name, token, now),
        )
        return "added", True


def get_active_recipients(limit: int) -> list[sqlite3.Row]:
    with get_db() as conn:
        return list(
            conn.execute(
                """
                SELECT id, email, name, unsubscribe_token
                FROM recipients
                WHERE unsubscribed = 0
                ORDER BY id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        )


def unsubscribe_by_token(token: str) -> str | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT email FROM recipients WHERE unsubscribe_token = ?",
            (token,),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE recipients SET unsubscribed = 1 WHERE unsubscribe_token = ?",
            (token,),
        )
        return row["email"]


def get_latest_draft() -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            """
            SELECT * FROM campaigns
            WHERE status = 'draft'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()


def get_campaign(campaign_id: int) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()


def save_draft(
    subject: str,
    body_text: str,
    link_url: str,
    image_path: str | None,
    campaign_id: int | None = None,
) -> int:
    now = _utc_now()
    with get_db() as conn:
        if campaign_id:
            conn.execute(
                """
                UPDATE campaigns
                SET subject = ?, body_text = ?, link_url = ?, image_path = ?
                WHERE id = ? AND status = 'draft'
                """,
                (subject, body_text, link_url, image_path, campaign_id),
            )
            return campaign_id

        draft = conn.execute(
            "SELECT id FROM campaigns WHERE status = 'draft' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if draft:
            conn.execute(
                """
                UPDATE campaigns
                SET subject = ?, body_text = ?, link_url = ?, image_path = ?
                WHERE id = ?
                """,
                (subject, body_text, link_url, image_path, draft["id"]),
            )
            return int(draft["id"])

        cur = conn.execute(
            """
            INSERT INTO campaigns (subject, body_text, link_url, image_path, status, created_at)
            VALUES (?, ?, ?, ?, 'draft', ?)
            """,
            (subject, body_text, link_url, image_path, now),
        )
        return int(cur.lastrowid)


def set_campaign_status(campaign_id: int, status: str, sent_at: str | None = None) -> None:
    with get_db() as conn:
        if sent_at:
            conn.execute(
                "UPDATE campaigns SET status = ?, sent_at = ? WHERE id = ?",
                (status, sent_at, campaign_id),
            )
        else:
            conn.execute(
                "UPDATE campaigns SET status = ? WHERE id = ?",
                (status, campaign_id),
            )


def add_delivery_log(
    campaign_id: int,
    recipient_id: int | None,
    email: str,
    name: str,
    status: str,
    error_message: str = "",
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO delivery_log
            (campaign_id, recipient_id, email, name, status, error_message, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (campaign_id, recipient_id, email, name, status, error_message, _utc_now()),
        )


def get_delivery_report(campaign_id: int) -> list[sqlite3.Row]:
    with get_db() as conn:
        return list(
            conn.execute(
                """
                SELECT email, name, status, error_message, sent_at
                FROM delivery_log
                WHERE campaign_id = ?
                ORDER BY id
                """,
                (campaign_id,),
            ).fetchall()
        )


def delivery_stats(campaign_id: int) -> dict[str, int]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS c
            FROM delivery_log
            WHERE campaign_id = ?
            GROUP BY status
            """,
            (campaign_id,),
        ).fetchall()
    stats = {"sent": 0, "error": 0, "total": 0}
    for row in rows:
        stats["total"] += row["c"]
        if row["status"] == "sent":
            stats["sent"] = row["c"]
        else:
            stats["error"] += row["c"]
    return stats
