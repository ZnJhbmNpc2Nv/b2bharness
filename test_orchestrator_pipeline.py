#!/usr/bin/env python3
"""Comprehensive Unit and Integration Tests for B2BHarnessOrchestrator and A2A Messaging Protocol.

Zero external dependencies; pure standard library Python 3.8+ unittest.
Covers:
  - Models, Enums & A2A Envelope serialization/deserialization
  - StepSnapshot & HarnessConfig
  - 7-Stage End-to-End Pipeline Lifecycle (PRE_SDD -> AB_TEST)
  - AST-based reverse engineering & discovery.md generation
  - ASVS Level 2 AST SAST scanner
  - HITL Intent Approval gate and resumption
  - Post-SDD error loop recovery and max loops escalation gate
  - run_until_pause autonomous execution loop
  - A2A Envelope audit trail in SQLite WAL
"""

import ast
import json
import os
import shutil
import sys
import tempfile
import unittest

# Ensure corporate_speckit is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from b2b_harness.models import (
    PipelineStage,
    StageStatus,
    A2AEnvelope,
    StepSnapshot,
    HarnessConfig,
    compute_artifact_hash,
)
from b2b_harness.orchestrator import (
    B2BHarnessOrchestrator,
    SASTVisitor,
)


class TestB2BHarnessModels(unittest.TestCase):
    """Verifies all models, enums, serialization, and hashing logic."""

    def test_pipeline_stage_enum(self):
        self.assertEqual(PipelineStage.PRE_SDD.value, "PRE_SDD")
        self.assertEqual(PipelineStage.SDD_INTENT.value, "SDD_INTENT")
        self.assertEqual(PipelineStage.SDD_SPEC.value, "SDD_SPEC")
        self.assertEqual(PipelineStage.SDD_PLAN.value, "SDD_PLAN")
        self.assertEqual(PipelineStage.SDD_DEV.value, "SDD_DEV")
        self.assertEqual(PipelineStage.POST_SDD.value, "POST_SDD")
        self.assertEqual(PipelineStage.AB_TEST.value, "AB_TEST")

    def test_stage_status_enum(self):
        self.assertEqual(StageStatus.PENDING.value, "PENDING")
        self.assertEqual(StageStatus.RUNNING.value, "RUNNING")
        self.assertEqual(StageStatus.COMPLETED.value, "COMPLETED")
        self.assertEqual(StageStatus.FAILED.value, "FAILED")
        self.assertEqual(StageStatus.AWAITING_HUMAN.value, "AWAITING_HUMAN")
        self.assertEqual(StageStatus.SKIPPED.value, "SKIPPED")

    def test_a2a_envelope_serialization(self):
        envelope = A2AEnvelope(
            trace_id="trace-001",
            step_id="SDD_SPEC",
            iteration=1,
            sender={"agent_role": "spec_engineer", "model": "opus", "temperature": 0.1},
            recipient={"agent_role": "plan_architect"},
            payload={
                "artifact_type": "SPEC",
                "artifact_hash": "abc123hash",
                "content": "# Spec content",
                "referenced_artifacts": {"intent": "intent.md"},
                "metadata": {"req_count": 5},
            },
            status="APPROVED",
        )

        d = envelope.to_dict()
        self.assertEqual(d["trace_id"], "trace-001")
        self.assertEqual(d["sender"]["agent_role"], "spec_engineer")
        self.assertEqual(d["payload"]["artifact_type"], "SPEC")

        restored = A2AEnvelope.from_dict(d)
        self.assertEqual(restored.trace_id, envelope.trace_id)
        self.assertEqual(restored.payload["artifact_hash"], "abc123hash")
        self.assertEqual(restored.status, "APPROVED")

    def test_step_snapshot_serialization(self):
        snap = StepSnapshot(
            pipeline_id="pipe-123",
            stage="PRE_SDD",
            iteration=1,
            status="COMPLETED",
            input_artifacts={"source": "vibe.py"},
            output_artifacts={"discovery": "discovery.md"},
            error_message=None,
        )
        d = snap.to_dict()
        self.assertEqual(d["pipeline_id"], "pipe-123")
        self.assertEqual(d["stage"], "PRE_SDD")

        restored = StepSnapshot.from_dict(d)
        self.assertEqual(restored.pipeline_id, snap.pipeline_id)
        self.assertEqual(restored.output_artifacts["discovery"], "discovery.md")

    def test_harness_config(self):
        cfg = HarnessConfig()
        self.assertEqual(cfg.max_post_sdd_loops, 3)
        self.assertEqual(cfg.execution_timeout_sec, 60)
        self.assertTrue(cfg.auto_sandbox)
        self.assertTrue(cfg.require_hitl_intent)

        d = cfg.to_dict()
        restored = HarnessConfig.from_dict(d)
        self.assertEqual(restored.max_post_sdd_loops, 3)

    def test_compute_artifact_hash(self):
        text = "Hello Corporate Spec-Kit"
        h1 = compute_artifact_hash(text)
        h2 = compute_artifact_hash(text)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)


class TestSASTVisitor(unittest.TestCase):
    """Verifies static application security testing (OWASP ASVS) on AST trees."""

    def test_detect_prohibited_calls(self):
        code = """
def bad_func():
    eval('2 + 2')
    exec('print(1)')
    import os
    os.system('ls -la')
"""
        tree = ast.parse(code)
        visitor = SASTVisitor()
        visitor.visit(tree)

        finding_types = [f["type"] for f in visitor.findings]
        self.assertIn("PROHIBITED_CALL", finding_types)
        self.assertIn("INSECURE_PROCESS_EXEC", finding_types)

    def test_clean_code_has_zero_findings(self):
        code = """
def clean_func(x: int) -> int:
    try:
        return x * 2
    except ValueError as e:
        return 0
"""
        tree = ast.parse(code)
        visitor = SASTVisitor()
        visitor.visit(tree)
        self.assertEqual(len(visitor.findings), 0)


class TestB2BHarnessOrchestrator(unittest.TestCase):
    """End-to-End integration tests for B2BHarnessOrchestrator."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="speckit_orch_test_")
        self.db_path = os.path.join(self.temp_dir, "db", "speckit_harness.db")
        self.storage_root = os.path.join(self.temp_dir, "storage")
        
        # Create a sample vibe-code file for AST reverse engineering
        self.sample_code_path = os.path.join(self.temp_dir, "vibe_service.py")
        with open(self.sample_code_path, "w", encoding="utf-8") as f:
            f.write('''"""Sample legacy vibe code for reverse engineering."""
import os

class LegacyDataService:
    """Old legacy service class."""
    def __init__(self, token="default"):
        self.token = token

    def run_query(self, query):
        return {"result": f"Executed {query}"}

def format_record(name, count):
    return f"{name}:{count}"
''')

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_orchestrator_initialization(self):
        orchestrator = B2BHarnessOrchestrator(
            db_path=self.db_path,
            storage_root=self.storage_root,
        )
        self.assertTrue(os.path.exists(self.db_path))
        with orchestrator._get_connection() as conn:
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(journal.lower(), "wal")

    def test_full_7_stage_pipeline_lifecycle(self):
        """Tests the complete step-by-step lifecycle from PRE_SDD through AB_TEST with HITL intent resolution."""
        orchestrator = B2BHarnessOrchestrator(
            db_path=self.db_path,
            storage_root=self.storage_root,
            config=HarnessConfig(require_hitl_intent=True),
        )

        pipeline_id = orchestrator.init_pipeline(
            project_name="DataSyncService",
            input_path=self.sample_code_path,
            initial_idea="Normalize legacy data query into enterprise spec-kit module",
        )
        self.assertTrue(pipeline_id.startswith("pipe-"))

        # 1. PRE_SDD Stage
        res_pre = orchestrator.step(pipeline_id)
        self.assertEqual(res_pre["stage"], PipelineStage.PRE_SDD.value)
        self.assertEqual(res_pre["status"], StageStatus.COMPLETED.value)
        state = orchestrator.get_pipeline_state(pipeline_id)
        self.assertEqual(state["current_stage"], PipelineStage.SDD_INTENT.value)
        discovery_file = os.path.join(state["storage_dir"], "discovery.md")
        self.assertTrue(os.path.exists(discovery_file))
        with open(discovery_file, "r", encoding="utf-8") as f:
            disc_content = f.read()
        self.assertIn("LegacyDataService", disc_content)
        self.assertIn("format_record", disc_content)

        # 2. SDD_INTENT Stage (HITL gate triggers because require_hitl_intent is True)
        res_intent = orchestrator.step(pipeline_id)
        self.assertEqual(res_intent["status"], StageStatus.AWAITING_HUMAN.value)
        self.assertEqual(res_intent["gate_type"], "INTENT_APPROVAL")

        state = orchestrator.get_pipeline_state(pipeline_id)
        self.assertEqual(state["status"], StageStatus.AWAITING_HUMAN.value)
        self.assertIsNotNone(state["pending_gate"])
        self.assertEqual(state["pending_gate"]["gate_type"], "INTENT_APPROVAL")

        # Calling step while awaiting human input returns early
        step_paused = orchestrator.step(pipeline_id)
        self.assertEqual(step_paused["status"], StageStatus.AWAITING_HUMAN.value)

        # Resume pipeline via HITL approval
        resumed_state = orchestrator.resume_pipeline(
            pipeline_id,
            {
                "decision": "APPROVE_AS_IS",
                "clarifications": "Clarification: Must support air-gapped sqlite transactions only.",
            },
        )
        self.assertEqual(resumed_state["current_stage"], PipelineStage.SDD_SPEC.value)
        self.assertIsNone(resumed_state["pending_gate"])

        # 3. SDD_SPEC Stage
        res_spec = orchestrator.step(pipeline_id)
        self.assertEqual(res_spec["stage"], PipelineStage.SDD_SPEC.value)
        self.assertEqual(res_spec["status"], StageStatus.COMPLETED.value)
        state = orchestrator.get_pipeline_state(pipeline_id)
        self.assertEqual(state["current_stage"], PipelineStage.SDD_PLAN.value)
        spec_file = os.path.join(state["storage_dir"], "spec.md")
        self.assertTrue(os.path.exists(spec_file))
        with open(spec_file, "r", encoding="utf-8") as f:
            spec_content = f.read()
        self.assertIn("REQ-CORE-001", spec_content)
        self.assertIn("REQ-VAL-002", spec_content)
        self.assertIn("REQ-SEC-004", spec_content)

        # 4. SDD_PLAN Stage
        res_plan = orchestrator.step(pipeline_id)
        self.assertEqual(res_plan["stage"], PipelineStage.SDD_PLAN.value)
        self.assertEqual(res_plan["status"], StageStatus.COMPLETED.value)
        self.assertEqual(res_plan["traceability_coverage"], 1.0)
        state = orchestrator.get_pipeline_state(pipeline_id)
        self.assertEqual(state["current_stage"], PipelineStage.SDD_DEV.value)
        plan_file = os.path.join(state["storage_dir"], "plan.md")
        self.assertTrue(os.path.exists(plan_file))

        # 5. SDD_DEV Stage
        res_dev = orchestrator.step(pipeline_id)
        self.assertEqual(res_dev["stage"], PipelineStage.SDD_DEV.value)
        self.assertEqual(res_dev["status"], StageStatus.COMPLETED.value)
        self.assertTrue(res_dev["tests_passed"])
        self.assertTrue(res_dev["sast_clean"])
        state = orchestrator.get_pipeline_state(pipeline_id)
        self.assertEqual(state["current_stage"], PipelineStage.POST_SDD.value)
        dev_log_file = os.path.join(state["storage_dir"], "dev_log.md")
        self.assertTrue(os.path.exists(dev_log_file))

        # 6. POST_SDD Stage (Tests passed -> nominee extracted)
        res_post = orchestrator.step(pipeline_id)
        self.assertEqual(res_post["stage"], PipelineStage.POST_SDD.value)
        self.assertEqual(res_post["status"], StageStatus.COMPLETED.value)
        state = orchestrator.get_pipeline_state(pipeline_id)
        self.assertEqual(state["current_stage"], PipelineStage.AB_TEST.value)
        nominee_file = os.path.join(state["storage_dir"], res_post["nominee_file"])
        self.assertTrue(os.path.exists(nominee_file))

        # 7. AB_TEST Stage
        res_ab = orchestrator.step(pipeline_id)
        self.assertEqual(res_ab["stage"], PipelineStage.AB_TEST.value)
        self.assertEqual(res_ab["status"], StageStatus.COMPLETED.value)
        self.assertFalse(res_ab["drift_detected"])
        state = orchestrator.get_pipeline_state(pipeline_id)
        self.assertEqual(state["status"], StageStatus.COMPLETED.value)
        test_log_file = os.path.join(state["storage_dir"], "test_log.md")
        self.assertTrue(os.path.exists(test_log_file))

        # Check A2A Envelopes recorded in database
        self.assertGreaterEqual(state["messages_count"], 7)

    def test_run_until_pause(self):
        """Verifies run_until_pause pauses at HITL gate and completes after resumption."""
        orchestrator = B2BHarnessOrchestrator(
            db_path=self.db_path,
            storage_root=self.storage_root,
            config=HarnessConfig(require_hitl_intent=True),
        )

        pipeline_id = orchestrator.init_pipeline(
            project_name="BatchProcessor",
            input_path=self.sample_code_path,
        )

        # 1st run: pauses at SDD_INTENT
        paused_state = orchestrator.run_until_pause(pipeline_id)
        self.assertEqual(paused_state["status"], StageStatus.AWAITING_HUMAN.value)
        self.assertEqual(paused_state["current_stage"], PipelineStage.SDD_INTENT.value)

        # Resume gate
        orchestrator.resume_pipeline(pipeline_id, {"decision": "APPROVE_AS_IS"})

        # 2nd run: executes all remaining stages through AB_TEST to completion
        final_state = orchestrator.run_until_pause(pipeline_id)
        self.assertEqual(final_state["status"], StageStatus.COMPLETED.value)
        self.assertEqual(final_state["current_stage"], PipelineStage.AB_TEST.value)

    def test_post_sdd_retry_and_escalation(self):
        """Verifies that failures in SDD_DEV trigger POST_SDD retries up to max loops and then escalate."""
        orchestrator = B2BHarnessOrchestrator(
            db_path=self.db_path,
            storage_root=self.storage_root,
            config=HarnessConfig(
                require_hitl_intent=False,  # auto-advance intent
                max_post_sdd_loops=2,
            ),
        )

        pipeline_id = orchestrator.init_pipeline(
            project_name="FaultyModule",
            input_path=self.sample_code_path,
            initial_idea="SIMULATE_PERSISTENT_ERROR: Force an error in SDD_DEV to test retry loop",
        )

        # Execute through PRE_SDD, SDD_INTENT, SDD_SPEC, SDD_PLAN
        orchestrator.step(pipeline_id)  # PRE_SDD -> SDD_INTENT
        orchestrator.step(pipeline_id)  # SDD_INTENT -> SDD_SPEC
        orchestrator.step(pipeline_id)  # SDD_SPEC -> SDD_PLAN
        orchestrator.step(pipeline_id)  # SDD_PLAN -> SDD_DEV

        # Step into SDD_DEV (SIMULATE_PERSISTENT_ERROR causes simulated test failure)
        res_dev = orchestrator.step(pipeline_id)
        self.assertEqual(res_dev["status"], StageStatus.FAILED.value)

        # Step into POST_SDD: Loop 1 triggers plan_corrections.md and loops back to SDD_DEV
        res_post = orchestrator.step(pipeline_id)
        self.assertEqual(res_post["status"], "RETRY_SCHEDULED")
        self.assertEqual(res_post["action"], "LOOP_BACK_TO_SDD_DEV")
        self.assertEqual(res_post["loop_count"], 1)

        # Pipeline is back in SDD_DEV with loop_count=1
        state = orchestrator.get_pipeline_state(pipeline_id)
        self.assertEqual(state["current_stage"], PipelineStage.SDD_DEV.value)
        self.assertEqual(state["loop_count"], 1)

        # Step into SDD_DEV again (attempt 1, still simulating error)
        res_dev2 = orchestrator.step(pipeline_id)
        self.assertEqual(res_dev2["status"], StageStatus.FAILED.value)

        # Step into POST_SDD: Loop 2 scheduled
        res_post2 = orchestrator.step(pipeline_id)
        self.assertEqual(res_post2["status"], "RETRY_SCHEDULED")
        self.assertEqual(res_post2["loop_count"], 2)

        # Step into SDD_DEV again (attempt 2, failed)
        res_dev3 = orchestrator.step(pipeline_id)
        self.assertEqual(res_dev3["status"], StageStatus.FAILED.value)

        # Step into POST_SDD: Loop count reaches max_post_sdd_loops (2) -> Escalate to HITL gate!
        res_post3 = orchestrator.step(pipeline_id)
        self.assertEqual(res_post3["status"], StageStatus.AWAITING_HUMAN.value)
        self.assertEqual(res_post3["gate_type"], "LOOP_ESCALATION")

        state2 = orchestrator.get_pipeline_state(pipeline_id)
        self.assertEqual(state2["status"], StageStatus.AWAITING_HUMAN.value)
        self.assertIsNotNone(state2["pending_gate"])
        self.assertEqual(state2["pending_gate"]["gate_type"], "LOOP_ESCALATION")

        # Resume via FORCE_APPROVE -> advances to AB_TEST
        resumed = orchestrator.resume_pipeline(pipeline_id, {"decision": "FORCE_APPROVE"})
        self.assertEqual(resumed["current_stage"], PipelineStage.AB_TEST.value)

        # Run AB_TEST to completion
        final_res = orchestrator.step(pipeline_id)
        self.assertEqual(final_res["status"], StageStatus.COMPLETED.value)
        final_state = orchestrator.get_pipeline_state(pipeline_id)
        self.assertEqual(final_state["status"], StageStatus.COMPLETED.value)

    def test_escalation_abort_decision(self):
        """Verifies that an ABORT decision during loop escalation marks pipeline as FAILED."""
        orchestrator = B2BHarnessOrchestrator(
            db_path=self.db_path,
            storage_root=self.storage_root,
            config=HarnessConfig(require_hitl_intent=False, max_post_sdd_loops=1),
        )

        pipeline_id = orchestrator.init_pipeline(
            project_name="AbortModule",
            input_path=self.sample_code_path,
            initial_idea="SIMULATE_PERSISTENT_ERROR: Test abort",
        )

        # PRE_SDD -> SDD_INTENT -> SDD_SPEC -> SDD_PLAN
        for _ in range(4):
            orchestrator.step(pipeline_id)
        orchestrator.step(pipeline_id)  # SDD_DEV (attempt 0, failed)
        orchestrator.step(pipeline_id)  # POST_SDD (loop 1 scheduled, loops to SDD_DEV)
        orchestrator.step(pipeline_id)  # SDD_DEV (attempt 1, failed)
        orchestrator.step(pipeline_id)  # POST_SDD (loop 1 >= max 1 -> AWAITING_HUMAN)

        state = orchestrator.get_pipeline_state(pipeline_id)
        self.assertEqual(state["status"], StageStatus.AWAITING_HUMAN.value)

        # Human decides to ABORT
        aborted = orchestrator.resume_pipeline(pipeline_id, {"decision": "ABORT"})
        self.assertEqual(aborted["status"], StageStatus.FAILED.value)

    def test_invalid_pipeline_id_handling(self):
        """Verifies proper ValueError on nonexistent pipeline queries."""
        orchestrator = B2BHarnessOrchestrator(
            db_path=self.db_path,
            storage_root=self.storage_root,
        )
        with self.assertRaises(ValueError):
            orchestrator.get_pipeline_state("nonexistent-pipeline-id")
        with self.assertRaises(ValueError):
            orchestrator.step("nonexistent-pipeline-id")
        with self.assertRaises(ValueError):
            orchestrator.resume_pipeline("nonexistent-pipeline-id", {"decision": "APPROVE"})


if __name__ == "__main__":
    unittest.main()

