import sqlite3
import os
import datetime

DB_PATH = "data/harness.db"

def get_connection():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            status TEXT,
            data TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            user_id TEXT,
            stage TEXT,
            action TEXT,
            timestamp DATETIME
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS artifact_store (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_name TEXT,
            artifact_type TEXT,
            content TEXT,
            version_hash TEXT,
            timestamp DATETIME
        )
    """)
    conn.commit()
    conn.close()

def log_audit(session_id, user_id, stage, action):
    conn = get_connection()
    conn.execute(
        "INSERT INTO audit_log (session_id, user_id, stage, action, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, user_id, stage, action, datetime.datetime.utcnow())
    )
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
