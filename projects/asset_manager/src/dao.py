import sqlite3
from datetime import datetime

class AssetDAO:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE,
                    file_hash TEXT,
                    last_modified TIMESTAMP
                )
            """)
            conn.commit()

    def upsert_asset(self, file_path: str, file_hash: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO assets (file_path, file_hash, last_modified)
                VALUES (?, ?, ?)
            """, (file_path, file_hash, datetime.now().isoformat()))
            conn.commit()

    def get_duplicates(self):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("""
                SELECT file_hash, GROUP_CONCAT(file_path)
                FROM assets
                GROUP BY file_hash
                HAVING COUNT(*) > 1
            """).fetchall()
