"""Human-in-the-Loop (HITL) Gatekeeper for Corporate Spec-Kit B2B Harness.

Provides deterministic approval workflows, expert intervention checkpoints,
diff inspection, and clarification interviews (Grill-Me protocol).
Strict Python 3.8+ standard library implementation; zero external dependencies.
"""
import sqlite3
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


def get_iso_now() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class HitlGateManager:
    """Manages human approval gates and expert intervention across SDD pipeline stages."""

    STATE_PENDING = "PENDING"
    STATE_APPROVED = "APPROVED"
    STATE_REJECTED = "REJECTED"
    STATE_APPROVED_WITH_CONDITIONS = "APPROVED_WITH_CONDITIONS"

    VALID_STATES = {
        STATE_PENDING,
        STATE_APPROVED,
        STATE_REJECTED,
        STATE_APPROVED_WITH_CONDITIONS,
    }

    VALID_DECISIONS = {
        STATE_APPROVED,
        STATE_REJECTED,
        STATE_APPROVED_WITH_CONDITIONS,
    }

    @staticmethod
    def init_db(conn: sqlite3.Connection) -> None:
        """Ensure the HITL gates database table and indices are initialized."""
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS b2b_hitl_gates (
            gate_id TEXT PRIMARY KEY,
            pipeline_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            gate_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            diff_html TEXT,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by TEXT,
            resolved_role TEXT,
            rationale TEXT,
            modified_payload_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_b2b_hitl_pipeline ON b2b_hitl_gates(pipeline_id);
        CREATE INDEX IF NOT EXISTS idx_b2b_hitl_status ON b2b_hitl_gates(status);
        """)

    def create_gate(
        self,
        conn: sqlite3.Connection,
        pipeline_id: str,
        stage: str,
        gate_type: str,
        title: str,
        description: str,
        payload: Dict[str, Any],
        diff_html: Optional[str] = None,
    ) -> str:
        """Create a new human approval gate requiring expert review.

        Args:
            conn: Active SQLite connection.
            pipeline_id: Identifier of the active pipeline or project.
            stage: Pipeline stage (e.g. 'SDD-INTENT', 'SDD-SPEC', 'SDD-PLAN', 'SDD-DIFF').
            gate_type: Type of gate (e.g. 'APPROVAL', 'CLARIFICATION', 'DRIFT_REVIEW').
            title: Human-readable gate title.
            description: Explanation of why expert intervention is requested.
            payload: Structured context or candidate data to be approved.
            diff_html: Optional color-coded HTML diff for visual inspection.

        Returns:
            Newly generated unique gate_id.
        """
        self.init_db(conn)
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary")

        gate_id = f"gate-{uuid.uuid4().hex[:12]}"
        created_at = get_iso_now()
        payload_json = json.dumps(payload, ensure_ascii=False)

        conn.execute(
            """
            INSERT INTO b2b_hitl_gates (
                gate_id, pipeline_id, stage, gate_type, title, description,
                payload_json, diff_html, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                gate_id,
                pipeline_id,
                stage,
                gate_type,
                title,
                description,
                payload_json,
                diff_html,
                self.STATE_PENDING,
                created_at,
            ),
        )
        return gate_id

    def resolve_gate(
        self,
        conn: sqlite3.Connection,
        gate_id: str,
        decision: str,
        expert_name: str,
        expert_role: str,
        rationale: str,
        modified_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Resolve a pending gate with an expert decision and rationale.

        Args:
            conn: Active SQLite connection.
            gate_id: Target gate identifier.
            decision: Decision enum ('APPROVED', 'REJECTED', 'APPROVED_WITH_CONDITIONS').
            expert_name: Name of approving human expert.
            expert_role: Role/title of human expert.
            rationale: Justification or conditions for the decision.
            modified_payload: Optional modified payload with expert corrections.

        Returns:
            Dictionary containing the full resolved gate record.
        """
        self.init_db(conn)
        decision = decision.strip().upper()
        if decision not in self.VALID_DECISIONS:
            raise ValueError(
                f"Invalid decision '{decision}'. Must be one of: {sorted(self.VALID_DECISIONS)}"
            )

        cur = conn.execute(
            "SELECT * FROM b2b_hitl_gates WHERE gate_id = ?", (gate_id,)
        )
        row = cur.fetchone()
        if not row:
            raise KeyError(f"Gate '{gate_id}' not found.")

        current_status = row["status"] if isinstance(row, sqlite3.Row) else row[8]
        if current_status != self.STATE_PENDING:
            raise ValueError(
                f"Gate '{gate_id}' is already resolved with status '{current_status}'."
            )

        resolved_at = get_iso_now()
        modified_payload_json = (
            json.dumps(modified_payload, ensure_ascii=False)
            if modified_payload is not None
            else None
        )

        conn.execute(
            """
            UPDATE b2b_hitl_gates
            SET status = ?, resolved_at = ?, resolved_by = ?, resolved_role = ?,
                rationale = ?, modified_payload_json = ?
            WHERE gate_id = ?
            """,
            (
                decision,
                resolved_at,
                expert_name,
                expert_role,
                rationale,
                modified_payload_json,
                gate_id,
            ),
        )

        return self.get_gate(conn, gate_id)  # type: ignore

    def get_pending_gates(
        self, conn: sqlite3.Connection, pipeline_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve all currently pending gates requiring human review."""
        self.init_db(conn)
        if pipeline_id:
            cur = conn.execute(
                """
                SELECT * FROM b2b_hitl_gates
                WHERE status = 'PENDING' AND pipeline_id = ?
                ORDER BY created_at ASC
                """,
                (pipeline_id,),
            )
        else:
            cur = conn.execute(
                """
                SELECT * FROM b2b_hitl_gates
                WHERE status = 'PENDING'
                ORDER BY created_at ASC
                """
            )

        return [self._row_to_dict(r) for r in cur.fetchall()]

    def get_gate(
        self, conn: sqlite3.Connection, gate_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a gate record by its unique gate_id."""
        self.init_db(conn)
        cur = conn.execute(
            "SELECT * FROM b2b_hitl_gates WHERE gate_id = ?", (gate_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def list_gates(
        self,
        conn: sqlite3.Connection,
        pipeline_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List gates filtered optionally by pipeline_id and/or status."""
        self.init_db(conn)
        query = "SELECT * FROM b2b_hitl_gates WHERE 1=1"
        params: List[Any] = []

        if pipeline_id:
            query += " AND pipeline_id = ?"
            params.append(pipeline_id)
        if status:
            query += " AND status = ?"
            params.append(status.strip().upper())

        query += " ORDER BY created_at DESC"
        cur = conn.execute(query, params)
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def create_clarification_gate(
        self,
        conn: sqlite3.Connection,
        pipeline_id: str,
        stage: str,
        title: str,
        questions: List[Dict[str, Any]],
        description: str = "Clarification interview (Grill-Me) required for ambiguous requirements.",
        diff_html: Optional[str] = None,
    ) -> str:
        """Helper for SDD-INTENT 'Grill-Me' interview gate.

        Presents ambiguous questions, assumptions, and choice options to the expert.

        Args:
            conn: Active SQLite connection.
            pipeline_id: Identifier of pipeline.
            stage: Stage (typically 'SDD-INTENT').
            title: Title for clarification interview.
            questions: List of question objects, each containing:
                - question (str): The ambiguous question or dilemma.
                - assumption (str): What the pipeline assumes if not answered.
                - options (List[str]): Selectable options or choices.
                - selected (Optional[str]): Answer chosen by expert once resolved.
            description: Description of the interview.
            diff_html: Optional HTML diff preview.

        Returns:
            gate_id of created clarification gate.
        """
        payload = {
            "interview_type": "GRILL_ME_CLARIFICATION",
            "question_count": len(questions),
            "questions": questions,
        }
        return self.create_gate(
            conn=conn,
            pipeline_id=pipeline_id,
            stage=stage,
            gate_type="CLARIFICATION",
            title=title,
            description=description,
            payload=payload,
            diff_html=diff_html,
        )

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        """Convert an SQLite Row or tuple to a clean dictionary with deserialized JSON."""
        if isinstance(row, sqlite3.Row):
            d = dict(row)
        else:
            cols = [
                "gate_id",
                "pipeline_id",
                "stage",
                "gate_type",
                "title",
                "description",
                "payload_json",
                "diff_html",
                "status",
                "created_at",
                "resolved_at",
                "resolved_by",
                "resolved_role",
                "rationale",
                "modified_payload_json",
            ]
            d = dict(zip(cols, row))

        # Safely parse payload JSON
        try:
            d["payload"] = json.loads(d.get("payload_json") or "{}")
        except Exception:
            d["payload"] = d.get("payload_json")

        # Safely parse modified_payload JSON
        if d.get("modified_payload_json"):
            try:
                d["modified_payload"] = json.loads(d["modified_payload_json"])
            except Exception:
                d["modified_payload"] = d["modified_payload_json"]
        else:
            d["modified_payload"] = None

        return d
