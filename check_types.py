import sqlite3
conn = sqlite3.connect('data/harness.db')
cursor = conn.cursor()
cursor.execute("SELECT DISTINCT artifact_type FROM artifact_store;")
print("Available artifact types:", cursor.fetchall())
conn.close()
