"""
db.py — thin wrapper around the BUSINESS DATA SQLite database (followup_agent.db).

This is NOT the LangGraph checkpointer. This file only talks to the
`clients` and `messages` tables created by seed_demo_data.py.

Every graph node that needs real data (load_context, check_reply,
send_message, log_and_schedule ...) should import functions from here
instead of writing raw SQL inline.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

DB_PATH = "followup_agent.db"   # same file seed_demo_data.py writes to

CADENCE_DAYS = {
    "proposal_sent":   [3, 7, 14],
    "invoice_pending": [2, 5, 10],
    "meeting_done":    [2, 5, 10],
    "quote_requested": [3, 7, 14],
}


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Reads — used by load_context / check_reply
# ---------------------------------------------------------------------------

def get_client(client_id: int) -> dict:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        if row is None:
            raise ValueError(f"No client with id={client_id}")
        return dict(row)


def get_messages(client_id: int, limit: int = 10) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE client_id = ? ORDER BY sent_at ASC LIMIT ?",
            (client_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_due_clients() -> list[dict]:
    """Clients the daily scheduler should run the graph for."""
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, company, stage, follow_up_count, max_follow_ups, next_follow_up_at
            FROM clients
            WHERE status = 'active'
              AND opt_out = 0
              AND follow_up_count < max_follow_ups
              AND next_follow_up_at IS NOT NULL
              AND next_follow_up_at <= datetime('now', 'localtime')
            ORDER BY next_follow_up_at
            """
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Writes — used by check_reply / send_message / log_and_schedule
# ---------------------------------------------------------------------------

def mark_replied(client_id: int) -> None:
    """check_reply node calls this when a client's reply is detected."""
    with _conn() as conn:
        conn.execute(
            "UPDATE clients SET status = 'replied', next_follow_up_at = NULL WHERE id = ?",
            (client_id,),
        )


def log_message(client_id: int, direction: str, subject: str, body: str) -> None:
    """send_message (direction='sent') or a reply-sync job (direction='received') calls this."""
    with _conn() as conn:
        conn.execute(
            "INSERT INTO messages (client_id, direction, subject, body, sent_at) VALUES (?,?,?,?,?)",
            (client_id, direction, subject, body, datetime.now().isoformat(sep=" ")),
        )


def record_follow_up_sent(client_id: int) -> str:
    """
    log_and_schedule node calls this after a successful send:
    bumps follow_up_count, stamps last_contacted_at, and computes next_follow_up_at
    from that client's stage cadence. Returns the new next_follow_up_at (or None if
    max_follow_ups reached, in which case caller should route to mark_stopped instead).
    """
    with _conn() as conn:
        client = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
        new_count = client["follow_up_count"] + 1
        now = datetime.now()

        next_date = None
        if new_count < client["max_follow_ups"]:
            cadence = CADENCE_DAYS.get(client["stage"], [3, 7, 14])
            gap_days = cadence[min(new_count, len(cadence) - 1)]
            next_date = (now + timedelta(days=gap_days)).isoformat(sep=" ")

        conn.execute(
            """UPDATE clients
               SET follow_up_count = ?, last_contacted_at = ?, next_follow_up_at = ?
               WHERE id = ?""",
            (new_count, now.isoformat(sep=" "), next_date, client_id),
        )
        return next_date


def mark_stopped(client_id: int) -> None:
    """decide_action routes here on max-limit or opt-out."""
    with _conn() as conn:
        conn.execute(
            "UPDATE clients SET status = 'stopped', next_follow_up_at = NULL WHERE id = ?",
            (client_id,),
        )


def set_opt_out(client_id: int) -> None:
    """Call this if a reply contains an opt-out request."""
    with _conn() as conn:
        conn.execute(
            "UPDATE clients SET opt_out = 1, status = 'stopped', next_follow_up_at = NULL WHERE id = ?",
            (client_id,),
        )