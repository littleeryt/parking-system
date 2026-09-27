"""
database.py
-----------
The "dynamic database" for the Modern Parking System (Task One, part c).

It is called dynamic because rows are created, updated, and read
continuously while the system runs -- a vehicle arriving INSERTs a new
session row and UPDATEs a slot row; a vehicle paying and leaving UPDATEs
that same session row and flips the slot row back to "free". Nothing
about the data is fixed at build time; the tables grow and change shape
of content (though not schema) with every entry and exit.

Schema
------
slots
    id      INTEGER PRIMARY KEY   -- physical slot number, 1..N
    status  TEXT                  -- 'free' or 'occupied'

sessions
    id          INTEGER PRIMARY KEY AUTOINCREMENT
    plate       TEXT              -- vehicle number plate
    slot_id     INTEGER           -- which slot this session used
    entry_time  TEXT              -- ISO timestamp of arrival
    exit_time   TEXT              -- ISO timestamp of payment/exit (NULL while parked)
    fee         INTEGER           -- amount charged in Kshs (NULL until paid)
    paid        INTEGER           -- 0 = not paid, 1 = paid

A session with exit_time IS NULL represents a vehicle currently parked;
closing it (setting exit_time, fee, paid=1) is what "checks it out" of
the system and is the audit trail management can use for reporting.
"""

import sqlite3
from contextlib import contextmanager

DB_PATH = "parking.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(total_slots: int) -> None:
    """Create tables if they don't exist yet, and seed slot rows once."""
    with get_conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS slots (
                   id INTEGER PRIMARY KEY,
                   status TEXT NOT NULL DEFAULT 'free'
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   plate TEXT NOT NULL,
                   slot_id INTEGER NOT NULL,
                   entry_time TEXT NOT NULL,
                   exit_time TEXT,
                   fee INTEGER,
                   paid INTEGER NOT NULL DEFAULT 0
               )"""
        )
        existing = conn.execute("SELECT COUNT(*) AS c FROM slots").fetchone()["c"]
        if existing == 0:
            conn.executemany(
                "INSERT INTO slots (id, status) VALUES (?, 'free')",
                [(i,) for i in range(1, total_slots + 1)],
            )


def get_all_slots():
    """Return every slot with the plate currently parked there, if any."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT s.id, s.status, sess.plate
               FROM slots s
               LEFT JOIN sessions sess
                 ON sess.slot_id = s.id AND sess.exit_time IS NULL
               ORDER BY s.id"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_free_slot_ids():
    with get_conn() as conn:
        rows = conn.execute("SELECT id FROM slots WHERE status='free'").fetchall()
        return [r["id"] for r in rows]


def set_slot_status(slot_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE slots SET status=? WHERE id=?", (status, slot_id))


def create_session(plate: str, slot_id: int, entry_time: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (plate, slot_id, entry_time) VALUES (?, ?, ?)",
            (plate, slot_id, entry_time),
        )
        return cur.lastrowid


def get_open_sessions():
    """All vehicles currently parked (exit_time IS NULL). Used on startup
    to rebuild the in-memory hash map of active vehicles."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE exit_time IS NULL"
        ).fetchall()
        return [dict(r) for r in rows]


def close_session(session_id: int, exit_time: str, fee: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET exit_time=?, fee=?, paid=1 WHERE id=?",
            (exit_time, fee, session_id),
        )
