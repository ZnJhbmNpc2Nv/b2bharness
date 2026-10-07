"""Database layer for Corporate Spec-Kit.
Zero external dependencies; uses Python standard library sqlite3 in WAL mode.
"""
import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path

from .audit_seal import (
    seal_audit_entry,
    verify_ledger_integrity,
    GENESIS_HASH,
    compute_entry_hash,
)


def get_iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SpecDatabase:
    def __init__(self, db_path: str = "specs_storage/speckit.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                intent TEXT NOT NULL,
                constitution TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS requirements (
                id TEXT PRIMARY KEY,
                spec_id TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'FUNCTIONAL',
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                rationale TEXT NOT NULL,
                acceptance_criteria TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PROPOSED',
                current_version INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                created_role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (spec_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS requirement_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                req_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                rationale TEXT NOT NULL,
                acceptance_criteria TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL,
                author_name TEXT NOT NULL,
                author_role TEXT NOT NULL,
                change_type TEXT NOT NULL,
                justification TEXT NOT NULL,
                diff_unified TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (req_id) REFERENCES requirements(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS clarifications (
                id TEXT PRIMARY KEY,
                spec_id TEXT NOT NULL,
                req_id TEXT,
                question TEXT NOT NULL,
                asked_by TEXT NOT NULL,
                asked_role TEXT NOT NULL,
                answer TEXT,
                answered_by TEXT,
                answered_role TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY (spec_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                spec_id TEXT NOT NULL,
                req_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                assignee TEXT NOT NULL DEFAULT 'Unassigned',
                status TEXT NOT NULL DEFAULT 'TODO',
                test_case_id TEXT,
                code_targets TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (spec_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (req_id) REFERENCES requirements(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS lineage_nodes (
                id TEXT PRIMARY KEY,
                spec_id TEXT NOT NULL,
                node_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                label TEXT NOT NULL,
                meta_json TEXT,
                FOREIGN KEY (spec_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS lineage_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spec_id TEXT NOT NULL,
                from_node_id TEXT NOT NULL,
                to_node_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                FOREIGN KEY (spec_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS audit_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spec_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                details TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                prev_hash TEXT NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000',
                entry_hash TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (spec_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """)

            # Schema migration for existing audit_ledger tables
            cols = [r[1] for r in conn.execute("PRAGMA table_info(audit_ledger)").fetchall()]
            if "prev_hash" not in cols:
                conn.execute("ALTER TABLE audit_ledger ADD COLUMN prev_hash TEXT NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000'")
            if "entry_hash" not in cols:
                conn.execute("ALTER TABLE audit_ledger ADD COLUMN entry_hash TEXT NOT NULL DEFAULT ''")

            # Check if initial project exists, seed if empty
            cur = conn.execute("SELECT COUNT(*) FROM projects")
            if cur.fetchone()[0] == 0:
                self._seed_default_project(conn)
            else:
                # Backfill unsealed legacy rows if any
                unsealed = conn.execute("SELECT id FROM audit_ledger WHERE entry_hash = '' LIMIT 1").fetchone()
                if unsealed:
                    self._backfill_audit_hashes(conn)

    def _backfill_audit_hashes(self, conn: sqlite3.Connection):
        """Backfill cryptographic SHA-256 hashes for legacy unsealed audit entries."""
        specs = [r[0] for r in conn.execute("SELECT DISTINCT spec_id FROM audit_ledger ORDER BY spec_id").fetchall()]
        for sid in specs:
            rows = conn.execute(
                "SELECT id, entity_type, entity_id, action, actor_name, actor_role, details, timestamp FROM audit_ledger WHERE spec_id = ? ORDER BY id ASC",
                (sid,)
            ).fetchall()
            prev_hash = GENESIS_HASH
            for row in rows:
                h = compute_entry_hash(
                    prev_hash=prev_hash,
                    actor=row["actor_name"],
                    role=row["actor_role"],
                    action=row["action"],
                    entity_id=row["entity_id"],
                    details=row["details"],
                    timestamp=row["timestamp"]
                )
                conn.execute(
                    "UPDATE audit_ledger SET prev_hash = ?, entry_hash = ? WHERE id = ?",
                    (prev_hash, h, row["id"])
                )
                prev_hash = h

    def _seed_default_project(self, conn: sqlite3.Connection):
        now = get_iso_now()
        spec_id = "proj-airgap-gateway"
        
        # 1. Project
        intent = (
            "Build an internal Corporate Air-Gapped API Gateway that runs on enterprise intranet servers "
            "with zero internet egress, strict mTLS client certificate authentication, full request tracing, "
            "and real-time tampering-resistant audit logging compliant with ISO-27001."
        )
        constitution = (
            "# Enterprise Security Constitution (v1.4)\n\n"
            "1. **Zero External Egress**: No requests may exit internal network 10.0.0.0/8.\n"
            "2. **Cryptographic Integrity**: All credentials and tokens must use hardware HSM or AES-256-GCM.\n"
            "3. **Zero-Dependency Core**: Runtime components must execute without unverified external package repositories (pip/npm).\n"
            "4. **Audit Traceability**: Every API invocation must produce an immutable audit log entry within 5ms."
        )
        conn.execute(
            "INSERT INTO projects (id, title, intent, constitution, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (spec_id, "Corporate Air-Gapped Secure Gateway", intent, constitution, "APPROVED", now, now)
        )

        # 2. Requirements
        reqs = [
            (
                "REQ-SEC-001",
                spec_id,
                "SECURITY",
                "Strict Mutual TLS (mTLS) Authentication",
                "The gateway must enforce bidirectional mTLS with client certificate validation against the Corporate Root CA. Connections without valid certificates must be rejected at TLS handshake.",
                "Prevents spoofing and unauthorized network access inside corporate DMZ.",
                json.dumps([
                    "Given a client connecting without a client certificate, when TLS handshake occurs, then the connection is immediately aborted with SSL_CERTIFICATE_REQUIRED.",
                    "Given a valid cert signed by Corporate CA, when handshake succeeds, then client CN and SAN are extracted into request context headers."
                ]),
                "ACCEPTED",
                2,
                "Elena Voronova",
                "Chief Security Architect",
                now,
                now
            ),
            (
                "REQ-LOG-002",
                spec_id,
                "COMPLIANCE",
                "Tamper-Evident SHA-256 Audit Trail",
                "Every incoming request and outbound proxy dispatch must be logged with timestamp, client fingerprint, route, status code, and a chained SHA-256 hash verifying log integrity.",
                "Required by internal corporate compliance and ISO-27001 audit standards.",
                json.dumps([
                    "Each log entry includes previous_hash, computing chained integrity.",
                    "Log buffer writes synchronously to local disk before returning HTTP 200/204 to client."
                ]),
                "ACCEPTED",
                1,
                "Mikhail Sidorov",
                "Compliance Officer",
                now,
                now
            ),
            (
                "REQ-RT-003",
                spec_id,
                "FUNCTIONAL",
                "Dynamic In-Memory Routing Table with Health Checks",
                "Gateway routes incoming HTTP requests to backend microservices based on prefix matches with passive circuit breaker failover if upstream 5xx rate exceeds 10%.",
                "Ensures high availability without requiring external Consul or etcd cluster.",
                json.dumps([
                    "Route lookup latency must be under 0.5ms for 1000 registered endpoints.",
                    "Circuit breaker trips to OPEN on 3 consecutive 502/504 errors, failing fast without blocking."
                ]),
                "ACCEPTED",
                1,
                "Alexander Smirnov",
                "Lead Backend Engineer",
                now,
                now
            )
        ]
        conn.executemany(
            "INSERT INTO requirements (id, spec_id, category, title, description, rationale, acceptance_criteria, status, current_version, created_by, created_role, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            reqs
        )

        # 3. Requirement Revisions (showing how REQ-SEC-001 was amended from v1 to v2)
        v1_desc = "The gateway must enforce client certificate validation against the Corporate CA."
        v1_crit = json.dumps(["Clients must present a certificate during TLS handshake."])
        conn.execute(
            "INSERT INTO requirement_revisions (req_id, version, title, description, rationale, acceptance_criteria, category, status, author_name, author_role, change_type, justification, diff_unified, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "REQ-SEC-001", 1, "Strict Mutual TLS (mTLS) Authentication", v1_desc,
                "Prevents unauthorized network access.", v1_crit, "SECURITY", "PROPOSED",
                "Elena Voronova", "Security Architect", "CREATED", "Initial baseline draft from business intent",
                None, now
            )
        )
        
        v2_desc = "The gateway must enforce bidirectional mTLS with client certificate validation against the Corporate Root CA. Connections without valid certificates must be rejected at TLS handshake."
        v2_crit = reqs[0][6]
        diff_text = "--- v1\n+++ v2\n@@ -1 +1 @@\n-The gateway must enforce client certificate validation against the Corporate CA.\n+The gateway must enforce bidirectional mTLS with client certificate validation against the Corporate Root CA. Connections without valid certificates must be rejected at TLS handshake."
        conn.execute(
            "INSERT INTO requirement_revisions (req_id, version, title, description, rationale, acceptance_criteria, category, status, author_name, author_role, change_type, justification, diff_unified, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "REQ-SEC-001", 2, "Strict Mutual TLS (mTLS) Authentication", v2_desc,
                "Prevents spoofing and unauthorized network access inside corporate DMZ.", v2_crit, "SECURITY", "AUGMENTED",
                "Dmitry Petrov", "Head of Corporate Audit", "MODIFIED",
                "Clarified rejection phase (must occur strictly at TLS handshake stage to prevent DoS).", diff_text, now
            )
        )

        # 4. Clarification Loop (Spec-Kit Q&A)
        conn.execute(
            "INSERT INTO clarifications (id, spec_id, req_id, question, asked_by, asked_role, answer, answered_by, answered_role, status, created_at, resolved_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "CLAR-001", spec_id, "REQ-SEC-001",
                "What happens if an internal client certificate is revoked via CRL or OCSP in an air-gapped environment without internet access?",
                "Alexander Smirnov", "Lead Backend Engineer",
                "Revocation lists will be loaded from a pre-synced local SQLite/file cache updated daily via internal corporate admin bundle.",
                "Elena Voronova", "Chief Security Architect",
                "RESOLVED", now, now
            )
        )

        # 5. Tasks & Verification
        tasks = [
            (
                "TASK-001", spec_id, "REQ-SEC-001",
                "Implement SSLContext with ssl.CERT_REQUIRED and local CA bundle verification",
                "Configure standard Python ssl socket wrapper with client cert validation.",
                "Dev Team", "DONE", "TEST-MTLS-01", "sec_gateway/tls.py:wrap_socket", now, now
            ),
            (
                "TASK-002", spec_id, "REQ-LOG-002",
                "Implement chained SHA-256 rolling digest log writer",
                "Zero-dependency write loop with atomic flush.",
                "Dev Team", "DONE", "TEST-LOG-02", "sec_gateway/audit.py:write_audit_entry", now, now
            ),
            (
                "TASK-003", spec_id, "REQ-RT-003",
                "Implement non-blocking in-memory prefix trie router with circuit breaker",
                "Fast URL matching with consecutive error counter.",
                "Dev Team", "IN_PROGRESS", "TEST-RT-03", "sec_gateway/router.py:resolve_route", now, now
            )
        ]
        conn.executemany(
            "INSERT INTO tasks (id, spec_id, req_id, title, description, assignee, status, test_case_id, code_targets, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tasks
        )

        # 6. Lineage Graph Nodes
        nodes = [
            ("node-intent", spec_id, "INTENT", "intent", "Business Need: Air-Gapped Secure Gateway", json.dumps({"source": "CEO / Security Board Directive"})),
            ("node-const", spec_id, "CONSTITUTION", "constitution", "Constitution: Zero-Egress & Integrity", json.dumps({"rules": 4})),
            ("node-req-sec", spec_id, "REQUIREMENT", "REQ-SEC-001", "REQ-SEC-001: Strict mTLS Auth (v2)", json.dumps({"category": "SECURITY", "author": "Elena Voronova"})),
            ("node-req-log", spec_id, "REQUIREMENT", "REQ-LOG-002", "REQ-LOG-002: Chained SHA-256 Audit", json.dumps({"category": "COMPLIANCE", "author": "Mikhail Sidorov"})),
            ("node-req-rt", spec_id, "REQUIREMENT", "REQ-RT-003", "REQ-RT-003: In-Memory Router & Breaker", json.dumps({"category": "FUNCTIONAL", "author": "Alexander Smirnov"})),
            ("node-clar-01", spec_id, "CLARIFICATION", "CLAR-001", "CLAR-001: Air-gapped CRL/OCSP offline cache", json.dumps({"status": "RESOLVED"})),
            ("node-task-01", spec_id, "TASK", "TASK-001", "TASK-001: TLS Socket Wrapper", json.dumps({"status": "DONE"})),
            ("node-test-01", spec_id, "TEST", "TEST-MTLS-01", "TEST-MTLS-01: Handshake Abort on Missing Cert", json.dumps({"type": "Unit & Integration"})),
            ("node-code-01", spec_id, "CODE", "sec_gateway/tls.py", "CODE: sec_gateway/tls.py#L42", json.dumps({"symbol": "wrap_socket"}))
        ]
        conn.executemany(
            "INSERT INTO lineage_nodes (id, spec_id, node_type, entity_id, label, meta_json) VALUES (?, ?, ?, ?, ?, ?)",
            nodes
        )

        # 7. Lineage Graph Edges
        edges = [
            (spec_id, "node-intent", "node-req-sec", "DERIVED_FROM"),
            (spec_id, "node-intent", "node-req-log", "DERIVED_FROM"),
            (spec_id, "node-intent", "node-req-rt", "DERIVED_FROM"),
            (spec_id, "node-const", "node-req-sec", "CONSTRAINED_BY"),
            (spec_id, "node-const", "node-req-log", "CONSTRAINED_BY"),
            (spec_id, "node-req-sec", "node-clar-01", "CLARIFIED_BY"),
            (spec_id, "node-req-sec", "node-task-01", "IMPLEMENTS"),
            (spec_id, "node-task-01", "node-test-01", "VERIFIES"),
            (spec_id, "node-task-01", "node-code-01", "PRODUCES")
        ]
        conn.executemany(
            "INSERT INTO lineage_edges (spec_id, from_node_id, to_node_id, relation) VALUES (?, ?, ?, ?)",
            edges
        )

        # 8. Audit Ledger (Cryptographically sealed chain from Genesis)
        audit_events = [
            (spec_id, "PROJECT", spec_id, "CREATED", "Elena Voronova", "Chief Security Architect", "Project initialized with Air-Gapped Security Constitution", now),
            (spec_id, "REQUIREMENT", "REQ-SEC-001", "CREATED", "Elena Voronova", "Chief Security Architect", "Created v1 draft for mTLS validation", now),
            (spec_id, "REQUIREMENT", "REQ-LOG-002", "CREATED", "Mikhail Sidorov", "Compliance Officer", "Created v1 draft for audit trail", now),
            (spec_id, "CLARIFICATION", "CLAR-001", "RESOLVED", "Elena Voronova", "Chief Security Architect", "Resolved offline CRL cache mechanism", now),
            (spec_id, "REQUIREMENT", "REQ-SEC-001", "MODIFIED", "Dmitry Petrov", "Head of Corporate Audit", "Amended v2 with strict TLS handshake abort requirement", now)
        ]
        for ev in audit_events:
            self._record_audit_with_conn(
                conn, spec_id=ev[0], entity_type=ev[1], entity_id=ev[2], action=ev[3],
                actor_name=ev[4], actor_role=ev[5], details=ev[6], timestamp=ev[7]
            )

    # ------------------ AUDIT & SEALING HELPERS ------------------ #

    def _record_audit_with_conn(
        self,
        conn: sqlite3.Connection,
        spec_id: str,
        entity_type: str,
        entity_id: str,
        action: str,
        actor_name: str,
        actor_role: str,
        details: str,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = timestamp or get_iso_now()
        return seal_audit_entry(
            conn=conn,
            spec_id=spec_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_name=actor_name,
            actor_role=actor_role,
            details=details,
            timestamp=now,
        )

    def record_audit(
        self,
        spec_id: str,
        entity_type: str,
        entity_id: str,
        action: str,
        actor_name: str,
        actor_role: str,
        details: str,
        timestamp: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        """External hook / API to record cryptographically sealed audit events."""
        if conn:
            return self._record_audit_with_conn(
                conn, spec_id, entity_type, entity_id, action, actor_name, actor_role, details, timestamp
            )
        with self.get_connection() as c:
            return self._record_audit_with_conn(
                c, spec_id, entity_type, entity_id, action, actor_name, actor_role, details, timestamp
            )

    def verify_audit_integrity(self, spec_id: Optional[str] = None):
        """Verifies the SHA-256 tamper-evident audit ledger integrity."""
        return verify_ledger_integrity(self, spec_id=spec_id)

    # ------------------ CRUD APIS ------------------ #

    def list_projects(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
            return [dict(r) for r in rows]

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            return dict(row) if row else None

    def create_project(self, project_id: str, title: str, intent: str, constitution: str) -> Dict[str, Any]:
        now = get_iso_now()
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO projects (id, title, intent, constitution, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'DRAFT', ?, ?)",
                (project_id, title, intent, constitution, now, now)
            )
            # Add root intent node
            conn.execute(
                "INSERT INTO lineage_nodes (id, spec_id, node_type, entity_id, label, meta_json) VALUES (?, ?, 'INTENT', 'intent', ?, ?)",
                (f"node-{project_id}-intent", project_id, f"Intent: {title}", json.dumps({"intent": intent}))
            )
            self._record_audit_with_conn(
                conn, spec_id=project_id, entity_type='PROJECT', entity_id=project_id,
                action='CREATED', actor_name='Admin', actor_role='User',
                details='Initialized project', timestamp=now
            )
        return self.get_project(project_id)

    def list_requirements(self, spec_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM requirements WHERE spec_id = ? ORDER BY id ASC", (spec_id,)).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["acceptance_criteria"] = json.loads(item["acceptance_criteria"])
                except Exception:
                    item["acceptance_criteria"] = []
                results.append(item)
            return results

    def get_requirement(self, req_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM requirements WHERE id = ?", (req_id,)).fetchone()
            if not row:
                return None
            item = dict(row)
            try:
                item["acceptance_criteria"] = json.loads(item["acceptance_criteria"])
            except Exception:
                item["acceptance_criteria"] = []
            return item

    def create_requirement(self, spec_id: str, req_id: str, category: str, title: str, description: str, rationale: str, acceptance_criteria: List[str], author_name: str, author_role: str, justification: str = "Initial Requirement Definition") -> Dict[str, Any]:
        now = get_iso_now()
        crit_json = json.dumps(acceptance_criteria)
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO requirements (id, spec_id, category, title, description, rationale, acceptance_criteria, status, current_version, created_by, created_role, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'PROPOSED', 1, ?, ?, ?, ?)",
                (req_id, spec_id, category, title, description, rationale, crit_json, author_name, author_role, now, now)
            )
            conn.execute(
                "INSERT INTO requirement_revisions (req_id, version, title, description, rationale, acceptance_criteria, category, status, author_name, author_role, change_type, justification, diff_unified, timestamp) "
                "VALUES (?, 1, ?, ?, ?, ?, ?, 'PROPOSED', ?, ?, 'CREATED', ?, NULL, ?)",
                (req_id, title, description, rationale, crit_json, category, author_name, author_role, justification, now)
            )
            # Add lineage node and connect to intent
            node_id = f"node-{req_id}"
            conn.execute(
                "INSERT OR REPLACE INTO lineage_nodes (id, spec_id, node_type, entity_id, label, meta_json) VALUES (?, ?, 'REQUIREMENT', ?, ?, ?)",
                (node_id, spec_id, req_id, f"{req_id}: {title} (v1)", json.dumps({"category": category, "author": author_name, "role": author_role}))
            )
            # Find intent node
            intent_node = conn.execute("SELECT id FROM lineage_nodes WHERE spec_id = ? AND node_type = 'INTENT'", (spec_id,)).fetchone()
            if intent_node:
                conn.execute(
                    "INSERT INTO lineage_edges (spec_id, from_node_id, to_node_id, relation) VALUES (?, ?, ?, 'DERIVED_FROM')",
                    (spec_id, intent_node[0], node_id)
                )
            self._record_audit_with_conn(
                conn, spec_id=spec_id, entity_type='REQUIREMENT', entity_id=req_id,
                action='CREATED', actor_name=author_name, actor_role=author_role,
                details=f"Created {req_id} v1: {title}", timestamp=now
            )
        return self.get_requirement(req_id)

    def update_requirement(self, req_id: str, category: str, title: str, description: str, rationale: str, acceptance_criteria: List[str], status: str, author_name: str, author_role: str, justification: str, diff_unified: str = "") -> Dict[str, Any]:
        now = get_iso_now()
        crit_json = json.dumps(acceptance_criteria)
        with self.get_connection() as conn:
            cur = conn.execute("SELECT current_version, spec_id FROM requirements WHERE id = ?", (req_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Requirement {req_id} not found")
            new_version = row[0] + 1
            spec_id = row[1]

            conn.execute(
                "UPDATE requirements SET category = ?, title = ?, description = ?, rationale = ?, acceptance_criteria = ?, status = ?, current_version = ?, updated_at = ? WHERE id = ?",
                (category, title, description, rationale, crit_json, status, new_version, now, req_id)
            )
            conn.execute(
                "INSERT INTO requirement_revisions (req_id, version, title, description, rationale, acceptance_criteria, category, status, author_name, author_role, change_type, justification, diff_unified, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'MODIFIED', ?, ?, ?)",
                (req_id, new_version, title, description, rationale, crit_json, category, status, author_name, author_role, justification, diff_unified, now)
            )
            # Update lineage node label
            node_id = f"node-{req_id}"
            conn.execute(
                "UPDATE lineage_nodes SET label = ?, meta_json = ? WHERE id = ?",
                (f"{req_id}: {title} (v{new_version})", json.dumps({"category": category, "author": author_name, "role": author_role, "version": new_version}), node_id)
            )
            self._record_audit_with_conn(
                conn, spec_id=spec_id, entity_type='REQUIREMENT', entity_id=req_id,
                action='MODIFIED', actor_name=author_name, actor_role=author_role,
                details=f"Updated {req_id} to v{new_version}. Rationale: {justification}", timestamp=now
            )
        return self.get_requirement(req_id)

    def get_requirement_revisions(self, req_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM requirement_revisions WHERE req_id = ? ORDER BY version ASC", (req_id,)).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["acceptance_criteria"] = json.loads(item["acceptance_criteria"])
                except Exception:
                    item["acceptance_criteria"] = []
                results.append(item)
            return results

    def list_clarifications(self, spec_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM clarifications WHERE spec_id = ? ORDER BY created_at DESC", (spec_id,)).fetchall()
            return [dict(r) for r in rows]

    def add_clarification(self, spec_id: str, clar_id: str, req_id: Optional[str], question: str, asked_by: str, asked_role: str) -> Dict[str, Any]:
        now = get_iso_now()
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO clarifications (id, spec_id, req_id, question, asked_by, asked_role, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?)",
                (clar_id, spec_id, req_id, question, asked_by, asked_role, now)
            )
            # Lineage
            node_id = f"node-{clar_id}"
            conn.execute(
                "INSERT INTO lineage_nodes (id, spec_id, node_type, entity_id, label, meta_json) VALUES (?, ?, 'CLARIFICATION', ?, ?, ?)",
                (node_id, spec_id, clar_id, f"{clar_id}: {question[:45]}...", json.dumps({"status": "OPEN", "req_id": req_id}))
            )
            if req_id:
                parent_node = f"node-{req_id}"
                conn.execute(
                    "INSERT INTO lineage_edges (spec_id, from_node_id, to_node_id, relation) VALUES (?, ?, ?, 'CLARIFIED_BY')",
                    (spec_id, parent_node, node_id)
                )
            self._record_audit_with_conn(
                conn, spec_id=spec_id, entity_type='CLARIFICATION', entity_id=clar_id,
                action='QUESTION_ASKED', actor_name=asked_by, actor_role=asked_role,
                details=f"Raised question for {req_id or 'Spec'}: {question}", timestamp=now
            )
            row = conn.execute("SELECT * FROM clarifications WHERE id = ?", (clar_id,)).fetchone()
            return dict(row)

    def resolve_clarification(self, clar_id: str, answer: str, answered_by: str, answered_role: str) -> Dict[str, Any]:
        now = get_iso_now()
        with self.get_connection() as conn:
            cur = conn.execute("SELECT spec_id, req_id, question FROM clarifications WHERE id = ?", (clar_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("Clarification not found")
            spec_id, req_id, question = row[0], row[1], row[2]

            conn.execute(
                "UPDATE clarifications SET answer = ?, answered_by = ?, answered_role = ?, status = 'RESOLVED', resolved_at = ? WHERE id = ?",
                (answer, answered_by, answered_role, now, clar_id)
            )
            # Update lineage node
            node_id = f"node-{clar_id}"
            conn.execute(
                "UPDATE lineage_nodes SET meta_json = ? WHERE id = ?",
                (json.dumps({"status": "RESOLVED", "answered_by": answered_by, "req_id": req_id}), node_id)
            )
            self._record_audit_with_conn(
                conn, spec_id=spec_id, entity_type='CLARIFICATION', entity_id=clar_id,
                action='RESOLVED', actor_name=answered_by, actor_role=answered_role,
                details=f"Resolved clarification {clar_id}. Answer: {answer}", timestamp=now
            )
            res = conn.execute("SELECT * FROM clarifications WHERE id = ?", (clar_id,)).fetchone()
            return dict(res)

    def list_tasks(self, spec_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM tasks WHERE spec_id = ? ORDER BY id ASC", (spec_id,)).fetchall()
            return [dict(r) for r in rows]

    def create_task(self, spec_id: str, task_id: str, req_id: str, title: str, description: str, assignee: str, test_case_id: str = "", code_targets: str = "") -> Dict[str, Any]:
        now = get_iso_now()
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO tasks (id, spec_id, req_id, title, description, assignee, status, test_case_id, code_targets, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'TODO', ?, ?, ?, ?)",
                (task_id, spec_id, req_id, title, description, assignee, test_case_id, code_targets, now, now)
            )
            # Lineage node for task
            node_task = f"node-{task_id}"
            conn.execute(
                "INSERT INTO lineage_nodes (id, spec_id, node_type, entity_id, label, meta_json) VALUES (?, ?, 'TASK', ?, ?, ?)",
                (node_task, spec_id, task_id, f"{task_id}: {title}", json.dumps({"status": "TODO", "req_id": req_id}))
            )
            conn.execute(
                "INSERT INTO lineage_edges (spec_id, from_node_id, to_node_id, relation) VALUES (?, ?, ?, 'IMPLEMENTS')",
                (spec_id, f"node-{req_id}", node_task)
            )
            if test_case_id:
                node_test = f"node-{test_case_id}"
                conn.execute(
                    "INSERT OR IGNORE INTO lineage_nodes (id, spec_id, node_type, entity_id, label, meta_json) VALUES (?, ?, 'TEST', ?, ?, ?)",
                    (node_test, spec_id, test_case_id, f"TEST: {test_case_id}", json.dumps({}))
                )
                conn.execute(
                    "INSERT INTO lineage_edges (spec_id, from_node_id, to_node_id, relation) VALUES (?, ?, ?, 'VERIFIES')",
                    (spec_id, node_task, node_test)
                )
            if code_targets:
                node_code = f"node-{code_targets.replace('/', '_').replace(':', '_')}"
                conn.execute(
                    "INSERT OR IGNORE INTO lineage_nodes (id, spec_id, node_type, entity_id, label, meta_json) VALUES (?, ?, 'CODE', ?, ?, ?)",
                    (node_code, spec_id, code_targets, f"CODE: {code_targets}", json.dumps({}))
                )
                conn.execute(
                    "INSERT INTO lineage_edges (spec_id, from_node_id, to_node_id, relation) VALUES (?, ?, ?, 'PRODUCES')",
                    (spec_id, node_task, node_code)
                )
            self._record_audit_with_conn(
                conn, spec_id=spec_id, entity_type='TASK', entity_id=task_id,
                action='CREATED', actor_name='Architect', actor_role='Tech Lead',
                details=f"Decomposed {task_id} from {req_id}: {title}", timestamp=now
            )
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row)

    def update_task_status(self, task_id: str, status: str, actor_name: str = "Developer", actor_role: str = "Dev") -> Dict[str, Any]:
        now = get_iso_now()
        with self.get_connection() as conn:
            cur = conn.execute("SELECT spec_id, title FROM tasks WHERE id = ?", (task_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("Task not found")
            spec_id, title = row[0], row[1]
            conn.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (status, now, task_id))
            self._record_audit_with_conn(
                conn, spec_id=spec_id, entity_type='TASK', entity_id=task_id,
                action='STATUS_CHANGED', actor_name=actor_name, actor_role=actor_role,
                details=f"Changed task {task_id} status to {status}", timestamp=now
            )
            res = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(res)

    def list_lineage(self, spec_id: str) -> Dict[str, Any]:
        with self.get_connection() as conn:
            nodes = [dict(r) for r in conn.execute("SELECT * FROM lineage_nodes WHERE spec_id = ?", (spec_id,)).fetchall()]
            edges = [dict(r) for r in conn.execute("SELECT * FROM lineage_edges WHERE spec_id = ?", (spec_id,)).fetchall()]
            return {"nodes": nodes, "edges": edges}

    def list_audit(self, spec_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM audit_ledger WHERE spec_id = ? ORDER BY id DESC LIMIT 200", (spec_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_setting(self, key: str, default: str = "") -> str:
        with self.get_connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str):
        with self.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
