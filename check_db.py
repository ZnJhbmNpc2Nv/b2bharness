import sqlite3
conn = sqlite3.connect('data/harness.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("Tables:", cursor.fetchall())
try:
    cursor.execute("SELECT * FROM artifact_store;")
    print("Artifacts:", cursor.fetchall())
except Exception as e:
    print("Error reading artifact_store:", e)
conn.close()
