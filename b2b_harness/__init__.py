"""Corporate Spec-Kit: Multi-Agent B2B SDD Harness & A2A Orchestration Framework.

Strict Python 3.8+ standard library; ZERO external dependencies.
Certified for air-gapped corporate intranets, defense workstations, and autonomous agent swarms.
"""

from .models import (
    PipelineStage,
    StageStatus,
    A2AEnvelope,
    StepSnapshot,
    HarnessConfig,
    get_iso_now,
    compute_artifact_hash,
)
from .orchestrator import (
    B2BHarnessOrchestrator,
    SASTVisitor,
)

# Optional exports from peer harness modules if present
try:
    from .sandbox import SecretScrubber, IsolatedSandboxRunner
except ImportError:
    SecretScrubber = None
    IsolatedSandboxRunner = None

try:
    from .security_sast import AstSastScanner, SbomGenerator, ModuleSealer
except ImportError:
    AstSastScanner = None
    SbomGenerator = None
    ModuleSealer = None

try:
    from .hitl_gate import HitlGateManager
except ImportError:
    HitlGateManager = None

try:
    from .ab_testing import MockGateway, AbComparator
except ImportError:
    MockGateway = None
    AbComparator = None

try:
    from .packager import ModulePackager
except ImportError:
    ModulePackager = None

try:
    from .nominee import NomineePromoter
except ImportError:
    NomineePromoter = None


__all__ = [
    # Core Orchestration & Protocol
    "PipelineStage",
    "StageStatus",
    "A2AEnvelope",
    "StepSnapshot",
    "HarnessConfig",
    "B2BHarnessOrchestrator",
    "SASTVisitor",
    "get_iso_now",
    "compute_artifact_hash",
    # Sandbox & Security
    "SecretScrubber",
    "IsolatedSandboxRunner",
    "AstSastScanner",
    "SbomGenerator",
    "ModuleSealer",
    # Extended Components
    "HitlGateManager",
    "MockGateway",
    "AbComparator",
    "ModulePackager",
    "NomineePromoter",
]
