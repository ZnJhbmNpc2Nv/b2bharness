"""Stage Attachments & Artifact Vault Module for Corporate Spec-Kit.
Enables file uploads, artifact versioning, and document lineage tracking at every lifecycle stage.
Pure standard library: base64, hashlib, os, sqlite3.
"""
import os
import sqlite3
import json
import base64
import hashlib
from typing import Dict, Any, List, Tuple, Callable
from ..base import BaseModule


class StageAttachmentsModule(BaseModule):
    def __init__(self, db, base_storage_dir: str = "specs_storage"):
        self.db = db
        self.base_storage_dir = base_storage_dir

    @property
    def slug(self) -> str:
        return "stage_attachments"

    @property
    def name(self) -> str:
        return "Файлы и артефакты (Stage Artifacts)"

    @property
    def description(self) -> str:
        return "Прикрепление исходных ТЗ, PDF регламентов, OpenAPI YAML схем, фикстур тестов и патчей к каждому этапу."

    @property
    def icon(self) -> str:
        return "📎"

    def init_db(self, conn: sqlite3.Connection):
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS stage_attachments (
            id TEXT PRIMARY KEY,
            spec_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            uploaded_by TEXT NOT NULL,
            uploaded_role TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            notes TEXT,
            relative_path TEXT NOT NULL
        );
        """)

        cur = conn.execute("SELECT COUNT(*) FROM stage_attachments")
        if cur.fetchone()[0] == 0:
            self._seed_default_attachments(conn)

    def _seed_default_attachments(self, conn: sqlite3.Connection):
        now = "2026-10-07T12:00:00Z"
        files = [
            (
                "FILE-001",
                "proj-airgap-gateway",
                "INTENT",
                "intent",
                "corporate_security_mandate_2026.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                48200,
                "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
                "Board of Directors",
                "Executive",
                now,
                "Директива Совета Безопасности о переводе периметра на Air-Gapped шлюзы",
                "attachments/intent/corporate_security_mandate_2026.docx"
            ),
            (
                "FILE-002",
                "proj-airgap-gateway",
                "CONSTITUTION",
                "constitution",
                "enterprise_infosec_standard_v1.4.pdf",
                "application/pdf",
                124500,
                "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",
                "Elena Voronova",
                "Chief Security Architect",
                now,
                "Корпоративный стандарт ИБ: криптография, запрет внешнего egress и аудит",
                "attachments/constitution/enterprise_infosec_standard_v1.4.pdf"
            ),
            (
                "FILE-003",
                "proj-airgap-gateway",
                "REQUIREMENT",
                "REQ-SEC-001",
                "dmz_gateway_openapi_v3.yaml",
                "text/yaml",
                14200,
                "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
                "Alexander Smirnov",
                "Lead Backend Engineer",
                now,
                "Контракт OpenAPI с аннотациями требований mTLS и контекстных заголовков",
                "attachments/requirements/dmz_gateway_openapi_v3.yaml"
            )
        ]
        conn.executemany(
            "INSERT INTO stage_attachments (id, spec_id, stage, entity_id, filename, file_type, file_size, sha256, uploaded_by, uploaded_role, uploaded_at, notes, relative_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            files
        )

    def get_routes(self) -> List[Tuple[str, str, Callable]]:
        return [
            ("GET", "/api/modules/stage_attachments/list", self._handle_list_attachments),
            ("POST", "/api/modules/stage_attachments/upload", self._handle_upload_attachment),
        ]

    def _handle_list_attachments(self, handler):
        query = handler.path.split("?", 1)[1] if "?" in handler.path else ""
        params = dict(qc.split("=", 1) for qc in query.split("&") if "=" in qc)
        spec_id = params.get("spec_id", "proj-airgap-gateway")
        stage = params.get("stage")

        with self.db.get_connection() as conn:
            if stage:
                rows = conn.execute("SELECT * FROM stage_attachments WHERE spec_id = ? AND stage = ? ORDER BY id ASC", (spec_id, stage)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM stage_attachments WHERE spec_id = ? ORDER BY id ASC", (spec_id,)).fetchall()
            handler._send_json(200, {"attachments": [dict(r) for r in rows]})

    def _handle_upload_attachment(self, handler):
        data = handler._read_json_body()
        spec_id = data.get("spec_id", "proj-airgap-gateway")
        stage = data.get("stage", "REQUIREMENT").upper()
        entity_id = data.get("entity_id", "general")
        filename = data.get("filename", "unnamed_artifact.dat")
        content_b64 = data.get("content_base64", "")
        author = data.get("uploaded_by", "Engineer")
        role = data.get("uploaded_role", "Developer")
        notes = data.get("notes", "")

        try:
            file_bytes = base64.b64decode(content_b64.encode("utf-8")) if content_b64 else b""
        except Exception:
            file_bytes = b""

        file_size = len(file_bytes)
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # Save to disk
        rel_dir = os.path.join(self.base_storage_dir, spec_id, "attachments", stage.lower())
        os.makedirs(rel_dir, exist_ok=True)
        disk_path = os.path.join(rel_dir, filename)
        with open(disk_path, "wb") as f:
            f.write(file_bytes)

        fid = f"FILE-{int(sqlite3.time.time())}"
        now = "2026-10-07T12:00:00Z"
        rel_path = f"attachments/{stage.lower()}/{filename}"

        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO stage_attachments (id, spec_id, stage, entity_id, filename, file_type, file_size, sha256, uploaded_by, uploaded_role, uploaded_at, notes, relative_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (fid, spec_id, stage, entity_id, filename, "application/octet-stream", file_size, file_hash, author, role, now, notes, rel_path)
            )

        handler._send_json(201, {"status": "uploaded", "file_id": fid, "sha256": file_hash, "path": rel_path})

    def get_lineage_contributions(self, conn: sqlite3.Connection, spec_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Inject attached files into Lineage DAG as document nodes."""
        rows = conn.execute("SELECT * FROM stage_attachments WHERE spec_id = ?", (spec_id,)).fetchall()
        nodes = []
        edges = []

        for r in rows:
            node_id = f"node-file-{r['id']}"
            nodes.append({
                "id": node_id,
                "spec_id": spec_id,
                "node_type": "ATTACHMENT",
                "entity_id": r["id"],
                "label": f"📄 {r['filename'][:24]}...",
                "meta_json": json.dumps({"stage": r["stage"], "sha256": r["sha256"][:12], "size": r["file_size"]})
            })

            target_node = f"node-{r['entity_id']}" if not r['entity_id'].startswith("node-") else r['entity_id']
            edges.append({
                "id": hash(f"{node_id}->{target_node}"),
                "spec_id": spec_id,
                "from_node_id": node_id,
                "to_node_id": target_node,
                "relation": "EVIDENCE_FOR"
            })

        return {"nodes": nodes, "edges": edges}
