import hashlib
from src.core.database import get_connection

class ArtifactManager:
    @staticmethod
    def store_artifact(module_name, artifact_type, content):
        version_hash = hashlib.sha256(content.encode()).hexdigest()
        conn = get_connection()
        conn.execute(
            "INSERT INTO artifact_store (module_name, artifact_type, content, version_hash, timestamp) VALUES (?, ?, ?, ?, datetime('now'))",
            (module_name, artifact_type, content, version_hash)
        )
        conn.commit()
        conn.close()
        return version_hash

    @staticmethod
    def get_latest_artifact(module_name, artifact_type):
        conn = get_connection()
        res = conn.execute(
            "SELECT content, version_hash FROM artifact_store WHERE module_name = ? AND artifact_type = ? ORDER BY timestamp DESC LIMIT 1",
            (module_name, artifact_type)
        ).fetchone()
        conn.close()
        return res
