"""Cryptographic Tamper-Evident Audit Seal for Corporate Spec-Kit.
Zero external dependencies; uses Python standard library hashlib & sqlite3.
Implements chained SHA-256 cryptographic hashes (Merkle/blockchain-like audit log).
"""
import hashlib
import sqlite3
from typing import Dict, Any, List, Optional, Tuple, Union

GENESIS_HASH = "0" * 64


def compute_entry_hash(
    prev_hash: str,
    actor: str,
    role: str,
    action: str,
    entity_id: str,
    details: str,
    timestamp: str,
) -> str:
    """Computes chained SHA-256 cryptographic hash for an audit entry.
    Payload: prev_hash + actor + role + action + entity_id + details + timestamp
    """
    payload = f"{prev_hash}|{actor}|{role}|{action}|{entity_id}|{details}|{timestamp}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_latest_entry_hash(conn: sqlite3.Connection, spec_id: str) -> str:
    """Retrieves the entry_hash of the most recent audit entry for the spec,
    or GENESIS_HASH if no entries exist yet.
    """
    row = conn.execute(
        "SELECT entry_hash FROM audit_ledger WHERE spec_id = ? AND entry_hash != '' ORDER BY id DESC LIMIT 1",
        (spec_id,),
    ).fetchone()
    if row and row[0]:
        return row[0]
    return GENESIS_HASH


def seal_audit_entry(
    conn: sqlite3.Connection,
    spec_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_name: str,
    actor_role: str,
    details: str,
    timestamp: str,
) -> Dict[str, Any]:
    """Computes chained SHA-256 cryptographic hash and writes sealed audit entry."""
    prev_hash = get_latest_entry_hash(conn, spec_id)
    entry_hash = compute_entry_hash(
        prev_hash=prev_hash,
        actor=actor_name,
        role=actor_role,
        action=action,
        entity_id=entity_id,
        details=details,
        timestamp=timestamp,
    )

    cur = conn.execute(
        """
        INSERT INTO audit_ledger (
            spec_id, entity_type, entity_id, action,
            actor_name, actor_role, details, timestamp,
            prev_hash, entry_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            spec_id,
            entity_type,
            entity_id,
            action,
            actor_name,
            actor_role,
            details,
            timestamp,
            prev_hash,
            entry_hash,
        ),
    )
    new_id = cur.lastrowid
    return {
        "id": new_id,
        "spec_id": spec_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "actor_name": actor_name,
        "actor_role": actor_role,
        "details": details,
        "timestamp": timestamp,
        "prev_hash": prev_hash,
        "entry_hash": entry_hash,
    }


class AuditVerificationResult:
    """Encapsulates the audit ledger integrity check results."""

    def __init__(
        self,
        is_valid: bool,
        total_entries: int,
        verified_entries: int,
        tampered_entries: Optional[List[Dict[str, Any]]] = None,
        specs_checked: Optional[List[str]] = None,
        entries_detail: Optional[List[Dict[str, Any]]] = None,
        message: str = "",
    ):
        self.is_valid = is_valid
        self.valid = is_valid  # Alias
        self.total_entries = total_entries
        self.verified_entries = verified_entries
        self.tampered_entries = tampered_entries or []
        self.specs_checked = specs_checked or []
        self.entries_detail = entries_detail or []
        self.message = message

    def __bool__(self) -> bool:
        return self.is_valid

    def __repr__(self) -> str:
        status = "PASSED" if self.is_valid else "FAILED"
        return f"<AuditVerificationResult status={status} checked={self.verified_entries}/{self.total_entries} tampered={len(self.tampered_entries)}>"

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        if item == "errors":
            return [t.get("reason", "") for t in self.tampered_entries]
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except KeyError:
            return default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.is_valid,
            "is_valid": self.is_valid,
            "total_entries": self.total_entries,
            "verified_entries": self.verified_entries,
            "tampered_entries": self.tampered_entries,
            "specs_checked": self.specs_checked,
            "entries_detail": self.entries_detail,
            "message": self.message,
        }


def verify_ledger_integrity(
    db: Any,
    spec_id: Optional[str] = None,
) -> AuditVerificationResult:
    """Validates the entire audit chain from genesis to latest entry.
    Detects any manual database tampering, payload alteration, insertion, or row deletion.

    Accepts:
      - SpecDatabase instance
      - sqlite3.Connection
      - Path string to SQLite database
    """
    # Resolve connection
    conn = None
    should_close = False

    if hasattr(db, "get_connection"):
        conn = db.get_connection()
        should_close = True
    elif isinstance(db, sqlite3.Connection):
        conn = db
    elif isinstance(db, str):
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        should_close = True
    else:
        raise ValueError(f"Unsupported database object: {type(db)}")

    try:
        # Determine specs to check
        if spec_id:
            specs = [spec_id]
        else:
            cur = conn.execute("SELECT DISTINCT spec_id FROM audit_ledger ORDER BY spec_id")
            specs = [r[0] for r in cur.fetchall()]

        total_entries = 0
        verified_entries = 0
        tampered_entries: List[Dict[str, Any]] = []
        entries_detail: List[Dict[str, Any]] = []

        for sid in specs:
            rows = conn.execute(
                """
                SELECT id, spec_id, entity_type, entity_id, action,
                       actor_name, actor_role, details, timestamp,
                       prev_hash, entry_hash
                FROM audit_ledger
                WHERE spec_id = ?
                ORDER BY id ASC
                """,
                (sid,),
            ).fetchall()

            expected_prev = GENESIS_HASH

            for row in rows:
                total_entries += 1
                row_dict = dict(row)
                row_id = row_dict["id"]
                stored_prev = row_dict.get("prev_hash") or ""
                stored_entry = row_dict.get("entry_hash") or ""
                actor = row_dict.get("actor_name") or ""
                role = row_dict.get("actor_role") or ""
                action = row_dict.get("action") or ""
                entity_id = row_dict.get("entity_id") or ""
                details = row_dict.get("details") or ""
                timestamp = row_dict.get("timestamp") or ""

                # Compute expected entry hash
                computed_hash = compute_entry_hash(
                    prev_hash=stored_prev,
                    actor=actor,
                    role=role,
                    action=action,
                    entity_id=entity_id,
                    details=details,
                    timestamp=timestamp,
                )

                chain_broken = stored_prev != expected_prev
                payload_tampered = stored_entry != computed_hash

                is_entry_valid = (not chain_broken) and (not payload_tampered)

                detail_record = {
                    "id": row_id,
                    "spec_id": sid,
                    "timestamp": timestamp,
                    "action": action,
                    "entity_id": entity_id,
                    "actor": f"{actor} ({role})",
                    "prev_hash": stored_prev,
                    "expected_prev": expected_prev,
                    "entry_hash": stored_entry,
                    "computed_hash": computed_hash,
                    "valid": is_entry_valid,
                }
                entries_detail.append(detail_record)

                if is_entry_valid:
                    verified_entries += 1
                    expected_prev = stored_entry
                else:
                    reasons = []
                    if chain_broken:
                        reasons.append(
                            f"Broken chain link: stored prev_hash '{stored_prev[:12]}...' != expected '{expected_prev[:12]}...'"
                        )
                    if payload_tampered:
                        reasons.append(
                            f"Payload altered: stored hash '{stored_entry[:12]}...' != recomputed '{computed_hash[:12]}...'"
                        )
                    tampered_entry = {
                        "id": row_id,
                        "spec_id": sid,
                        "timestamp": timestamp,
                        "entity_id": entity_id,
                        "action": action,
                        "reason": "; ".join(reasons),
                        "stored_prev": stored_prev,
                        "expected_prev": expected_prev,
                        "stored_entry": stored_entry,
                        "computed_hash": computed_hash,
                    }
                    tampered_entries.append(tampered_entry)
                    # For subsequent checks, attempt to track using stored_entry to check next links
                    expected_prev = stored_entry

        is_all_valid = len(tampered_entries) == 0
        if is_all_valid:
            msg = f"Audit ledger integrity 100% verified. All {verified_entries} entries cryptographically sealed from genesis."
        else:
            msg = f"CRITICAL: Integrity failure! Detected {len(tampered_entries)} tampered or corrupted audit entries."

        return AuditVerificationResult(
            is_valid=is_all_valid,
            total_entries=total_entries,
            verified_entries=verified_entries,
            tampered_entries=tampered_entries,
            specs_checked=specs,
            entries_detail=entries_detail,
            message=msg,
        )
    finally:
        if should_close and conn:
            conn.close()
