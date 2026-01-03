import sqlite3
import os

class DocsetIndex:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("DROP TABLE IF EXISTS searchIndex")
        self.conn.execute(
            "CREATE TABLE searchIndex(id INTEGER PRIMARY KEY, name TEXT, type TEXT, path TEXT)"
        )
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS anchor ON searchIndex (name, type, path)"
        )

    def add_entry(self, name, type, path):
        # Dash documentation recommends stripping tags from names and ensuring they aren't empty
        name = name.strip()
        if not name:
            return
            
        self.conn.execute(
            "INSERT OR IGNORE INTO searchIndex(name, type, path) VALUES (?, ?, ?)",
            (name, type, path),
        )

    def close(self):
        if self.conn:
            self.conn.commit()
            self.conn.close()
