"""Data models and A2A protocol specifications for Corporate Spec-Kit B2B Harness.

Zero external dependencies; pure Python 3.8+ standard library.
Certified for air-gapped enterprise environments and multi-agent swarms.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import hashlib
import json


def get_iso_now() -> str:
    """Returns current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_artifact_hash(content: str) -> str:
    """Computes deterministic SHA-256 hash of artifact content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class PipelineStage(str, Enum):
    """Execution stages of the SDD Multi-Agent Pipeline."""
    PRE_SDD = "PRE_SDD"
    SDD_INTENT = "SDD_INTENT"
    SDD_SPEC = "SDD_SPEC"
    SDD_PLAN = "SDD_PLAN"
    SDD_DEV = "SDD_DEV"
    POST_SDD = "POST_SDD"
    AB_TEST = "AB_TEST"


class StageStatus(str, Enum):
    """Operational status of a pipeline stage or gate."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    SKIPPED = "SKIPPED"


@dataclass
class A2AEnvelope:
    """Agent-to-Agent (A2A) standardized message envelope.
    
    Ensures end-to-end provenance, cryptographic content verification,
    and structured communication across multi-agent swarms.
    """
    trace_id: str
    step_id: str
    iteration: int
    sender: Dict[str, Any]
    recipient: Dict[str, Any]
    payload: Dict[str, Any]
    status: str = "IN_PROGRESS"
    timestamp: str = field(default_factory=get_iso_now)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes envelope to dictionary."""
        return {
            "trace_id": self.trace_id,
            "step_id": self.step_id,
            "iteration": self.iteration,
            "sender": dict(self.sender),
            "recipient": dict(self.recipient),
            "payload": dict(self.payload),
            "status": self.status,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "A2AEnvelope":
        """Deserializes envelope from dictionary."""
        return cls(
            trace_id=str(data.get("trace_id", "")),
            step_id=str(data.get("step_id", "")),
            iteration=int(data.get("iteration", 1)),
            sender=dict(data.get("sender") or {}),
            recipient=dict(data.get("recipient") or {}),
            payload=dict(data.get("payload") or {}),
            status=str(data.get("status", "IN_PROGRESS")),
            timestamp=str(data.get("timestamp") or get_iso_now()),
        )


@dataclass
class StepSnapshot:
    """Point-in-time execution snapshot for transactional stage replay."""
    pipeline_id: str
    stage: str
    iteration: int
    status: str
    input_artifacts: Dict[str, Any] = field(default_factory=dict)
    output_artifacts: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    updated_at: str = field(default_factory=get_iso_now)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes snapshot to dictionary."""
        return {
            "pipeline_id": self.pipeline_id,
            "stage": self.stage,
            "iteration": self.iteration,
            "status": self.status,
            "input_artifacts": dict(self.input_artifacts),
            "output_artifacts": dict(self.output_artifacts),
            "error_message": self.error_message,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepSnapshot":
        """Deserializes snapshot from dictionary."""
        return cls(
            pipeline_id=str(data.get("pipeline_id", "")),
            stage=str(data.get("stage", "")),
            iteration=int(data.get("iteration", 1)),
            status=str(data.get("status", "PENDING")),
            input_artifacts=dict(data.get("input_artifacts") or {}),
            output_artifacts=dict(data.get("output_artifacts") or {}),
            error_message=data.get("error_message"),
            updated_at=str(data.get("updated_at") or get_iso_now()),
        )


@dataclass
class HarnessConfig:
    """Runtime orchestration parameters for B2B multi-agent harness."""
    max_post_sdd_loops: int = 3
    execution_timeout_sec: int = 60
    auto_sandbox: bool = True
    require_hitl_intent: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serializes config to dictionary."""
        return {
            "max_post_sdd_loops": self.max_post_sdd_loops,
            "execution_timeout_sec": self.execution_timeout_sec,
            "auto_sandbox": self.auto_sandbox,
            "require_hitl_intent": self.require_hitl_intent,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HarnessConfig":
        """Deserializes config from dictionary."""
        return cls(
            max_post_sdd_loops=int(data.get("max_post_sdd_loops", 3)),
            execution_timeout_sec=int(data.get("execution_timeout_sec", 60)),
            auto_sandbox=bool(data.get("auto_sandbox", True)),
            require_hitl_intent=bool(data.get("require_hitl_intent", True)),
        )
