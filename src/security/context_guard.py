import re
import hashlib
import os
import json
from typing import Tuple, Optional

# Injection patterns to prevent context poisoning & system prompt override
SUSPICIOUS_INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"(?i)disregard\s+(all\s+)?(previous|prior)\s+instructions",
    r"(?i)you\s+are\s+now\s+(in\s+)?(dan|jailbreak|unrestricted)\s+mode",
    r"(?i)<\|im_start\|>",
    r"(?i)<\|im_end\|>",
    r"(?i)\[system\]",
    r"(?i)\[developer\]",
    r"(?i)\bexec\s*\(",
    r"(?i)\beval\s*\(",
    r"(?i)system:\s*you\s+are",
    r"(?i)bypass\s+(all\s+)?safety\s+filters"
]

SESSION_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.]{1,64}$')

class ContextIntegrityGuard:
    def __init__(self, staging_dir: str = "data/staging"):
        self.staging_dir = staging_dir

    @staticmethod
    def validate_session_id(session_id: str) -> bool:
        """Validates that session ID is alphanumeric and cannot traverse paths."""
        if not session_id or not SESSION_ID_PATTERN.match(session_id):
            return False
        if ".." in session_id or "/" in session_id or "\\" in session_id:
            return False
        return True

    @staticmethod
    def detect_prompt_injection(text: str) -> Tuple[bool, Optional[str]]:
        """Scans user input for adversarial context-poisoning and jailbreak tokens."""
        if not text:
            return False, None
            
        for pattern in SUSPICIOUS_INJECTION_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return True, f"Prompt injection token detected: '{match.group(0)}'"
                
        return False, None

    @staticmethod
    def sanitize_input(text: str, max_length: int = 16000) -> str:
        """Cleans and bounds user input to prevent context window bloat and control-char injection."""
        if not text:
            return ""
        # Strip null bytes and control chars except newlines and tabs
        sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
        return sanitized[:max_length].strip()

    def record_artifact_hash(self, session_id: str, artifact_type: str, content: str) -> str:
        """Computes SHA-256 hash and records it in the session metadata to prevent tampering."""
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        session_path = os.path.join(self.staging_dir, session_id)
        os.makedirs(session_path, exist_ok=True)
        
        meta_file = os.path.join(session_path, "integrity_manifest.json")
        manifest = {}
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                manifest = {}

        manifest[artifact_type] = {
            "hash": content_hash,
            "bytes": len(content.encode("utf-8"))
        }

        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return content_hash

    def verify_artifact_integrity(self, session_id: str, artifact_type: str, content: str) -> Tuple[bool, str]:
        """Ensures that locked specifications or plans have not been tampered with or poisoned."""
        session_path = os.path.join(self.staging_dir, session_id)
        meta_file = os.path.join(session_path, "integrity_manifest.json")
        
        if not os.path.exists(meta_file):
            return True, "No prior hash record (fresh artifact)"

        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            recorded = manifest.get(artifact_type, {}).get("hash")
            if not recorded:
                return True, "No record for artifact type"

            current_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if current_hash != recorded:
                return False, f"Integrity Violation: {artifact_type}.md content hash mismatch (expected {recorded[:12]}..., got {current_hash[:12]}...)"
                
            return True, "Verified"
        except Exception as e:
            return False, f"Integrity check error: {str(e)}"
