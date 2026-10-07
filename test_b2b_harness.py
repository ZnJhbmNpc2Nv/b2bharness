"""Comprehensive Unit and Integration Test Suite for Corporate Spec-Kit B2B Harness.

Tests:
1. HitlGateManager (HITL approval gates, states, and Grill-Me clarification interview)
2. MockGateway (Deterministic I/O record & replay, env/http mocking)
3. AbComparator (Functional equivalence, drift detection, test_log.md & spec_correction.md generation)
4. ModulePackager (Packaging, manifest, Dockerfile, runner, test harness, SBOM, and README)
5. NomineePromoter (Extracting hardening candidates, domain mapping, req_bank integration)

Strict Python 3.8+ standard library unittest; zero external dependencies.
"""
import unittest
import os
import sys
import tempfile
import sqlite3
import json
import shutil
import subprocess
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from b2b_harness.hitl_gate import HitlGateManager
from b2b_harness.ab_testing import MockGateway, AbComparator
from b2b_harness.packager import ModulePackager
from b2b_harness.nominee import NomineePromoter


class TestHitlGateManager(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.mgr = HitlGateManager()

    def tearDown(self):
        self.conn.close()

    def test_create_and_get_pending_gates(self):
        """Verify gate creation and pending gate retrieval."""
        payload = {"candidate_spec": "REQ-TEST-001", "impact": "HIGH"}
        gate_id = self.mgr.create_gate(
            conn=self.conn,
            pipeline_id="pipe-100",
            stage="SDD-SPEC",
            gate_type="APPROVAL",
            title="Approve Spec Changes",
            description="High impact security changes require architect sign-off",
            payload=payload,
            diff_html="<div class='diff'>+ new requirement</div>",
        )
        self.assertTrue(gate_id.startswith("gate-"))

        # Check pending gates
        pending = self.mgr.get_pending_gates(self.conn, pipeline_id="pipe-100")
        self.assertEqual(len(pending), 1)
        g = pending[0]
        self.assertEqual(g["gate_id"], gate_id)
        self.assertEqual(g["status"], HitlGateManager.STATE_PENDING)
        self.assertEqual(g["payload"], payload)
        self.assertIn("diff", g["diff_html"])

    def test_resolve_gate_approved(self):
        """Verify resolution with APPROVED decision."""
        gate_id = self.mgr.create_gate(
            conn=self.conn,
            pipeline_id="pipe-200",
            stage="SDD-PLAN",
            gate_type="APPROVAL",
            title="Approve Plan",
            description="Plan review",
            payload={"steps": [1, 2, 3]},
        )

        resolved = self.mgr.resolve_gate(
            conn=self.conn,
            gate_id=gate_id,
            decision="APPROVED",
            expert_name="Alice Smith",
            expert_role="Lead Architect",
            rationale="Architecture matches ISO-27001 requirements",
        )
        self.assertEqual(resolved["status"], "APPROVED")
        self.assertEqual(resolved["resolved_by"], "Alice Smith")
        self.assertEqual(resolved["resolved_role"], "Lead Architect")
        self.assertIsNotNone(resolved["resolved_at"])

        # Should no longer be pending
        pending = self.mgr.get_pending_gates(self.conn, pipeline_id="pipe-200")
        self.assertEqual(len(pending), 0)

    def test_resolve_gate_approved_with_conditions(self):
        """Verify resolution with APPROVED_WITH_CONDITIONS and modified payload."""
        gate_id = self.mgr.create_gate(
            conn=self.conn,
            pipeline_id="pipe-300",
            stage="SDD-DIFF",
            gate_type="DRIFT_REVIEW",
            title="Drift Approval",
            description="Review detected drift",
            payload={"timeout_ms": 5000},
        )

        mod_payload = {"timeout_ms": 15000, "retry_count": 3}
        resolved = self.mgr.resolve_gate(
            conn=self.conn,
            gate_id=gate_id,
            decision="APPROVED_WITH_CONDITIONS",
            expert_name="Bob Miller",
            expert_role="Security Officer",
            rationale="Approved with adjusted timeout and retries",
            modified_payload=mod_payload,
        )
        self.assertEqual(resolved["status"], "APPROVED_WITH_CONDITIONS")
        self.assertEqual(resolved["modified_payload"], mod_payload)

    def test_resolve_gate_rejected(self):
        """Verify resolution with REJECTED decision."""
        gate_id = self.mgr.create_gate(
            conn=self.conn,
            pipeline_id="pipe-400",
            stage="SDD-SPEC",
            gate_type="APPROVAL",
            title="Flawed Spec",
            description="Contains security defect",
            payload={"flaw": True},
        )
        resolved = self.mgr.resolve_gate(
            conn=self.conn,
            gate_id=gate_id,
            decision="REJECTED",
            expert_name="Carol Danvers",
            expert_role="Chief Security Officer",
            rationale="Violates air-gap non-egress invariant",
        )
        self.assertEqual(resolved["status"], "REJECTED")

        # Resolving again should raise ValueError
        with self.assertRaises(ValueError):
            self.mgr.resolve_gate(
                conn=self.conn,
                gate_id=gate_id,
                decision="APPROVED",
                expert_name="Carol",
                expert_role="CSO",
                rationale="Retrying",
            )

    def test_invalid_decision_validation(self):
        """Verify invalid decision string raises ValueError."""
        gate_id = self.mgr.create_gate(
            conn=self.conn,
            pipeline_id="pipe-500",
            stage="SDD-SPEC",
            gate_type="APPROVAL",
            title="Test",
            description="Test",
            payload={},
        )
        with self.assertRaises(ValueError):
            self.mgr.resolve_gate(
                conn=self.conn,
                gate_id=gate_id,
                decision="MAYBE",
                expert_name="Dan",
                expert_role="Eng",
                rationale="None",
            )

    def test_clarification_gate_grill_me(self):
        """Verify create_clarification_gate for Grill-Me interview."""
        questions = [
            {
                "question": "Should client authentication require mTLS or API token?",
                "assumption": "Defaulting to mTLS client certificates.",
                "options": ["Strict mTLS only", "Dual (mTLS + Token)", "Token only"],
            },
            {
                "question": "Max permissible timeout for upstream proxy calls?",
                "assumption": "15.0 seconds before circuit breaker trip.",
                "options": ["5.0 seconds", "15.0 seconds", "30.0 seconds"],
            },
        ]
        gate_id = self.mgr.create_clarification_gate(
            conn=self.conn,
            pipeline_id="pipe-interview-1",
            stage="SDD-INTENT",
            title="SDD-INTENT Clarification Interview",
            questions=questions,
        )
        gate = self.mgr.get_gate(self.conn, gate_id)
        self.assertIsNotNone(gate)
        self.assertEqual(gate["gate_type"], "CLARIFICATION")
        self.assertEqual(gate["payload"]["interview_type"], "GRILL_ME_CLARIFICATION")
        self.assertEqual(gate["payload"]["question_count"], 2)


class TestMockGateway(unittest.TestCase):
    def setUp(self):
        self.gateway = MockGateway()

    def test_record_and_get_mock_response(self):
        """Verify recording call and replaying response."""
        self.gateway.record_call(
            service="auth-service",
            endpoint="/verify",
            request_data={"token": "secret-123"},
            response_data={"valid": True, "subject": "admin"},
        )

        # Retrieve exact match
        resp = self.gateway.get_mock_response(
            service="auth-service",
            endpoint="/verify",
            request_data={"token": "secret-123"},
        )
        self.assertEqual(resp, {"valid": True, "subject": "admin"})

        # Wildcard or fallback match
        resp_fallback = self.gateway.get_mock_response(
            service="auth-service",
            endpoint="/verify",
            request_data=None,
        )
        self.assertEqual(resp_fallback, {"valid": True, "subject": "admin"})

    def test_export_and_load_fixtures(self):
        """Verify fixture JSON export and import."""
        self.gateway.set_fixture(
            service="vault",
            endpoint="/secret/key",
            response_data={"key": "xyz-999"},
        )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            fpath = tf.name

        try:
            self.gateway.export_fixtures(fpath)
            self.assertTrue(os.path.exists(fpath))

            new_gateway = MockGateway()
            new_gateway.load_fixtures(fpath)
            resp = new_gateway.get_mock_response("vault", "/secret/key")
            self.assertEqual(resp, {"key": "xyz-999"})
        finally:
            if os.path.exists(fpath):
                os.remove(fpath)

    def test_mock_env(self):
        """Verify mock_env temporarily sets and restores variables."""
        os.environ["EXISTING_KEY"] = "original"
        with self.gateway.mock_env({"EXISTING_KEY": "temp_val", "NEW_KEY": "123"}):
            self.assertEqual(os.environ["EXISTING_KEY"], "temp_val")
            self.assertEqual(os.environ["NEW_KEY"], "123")

        self.assertEqual(os.environ["EXISTING_KEY"], "original")
        self.assertNotIn("NEW_KEY", os.environ)
        os.environ.pop("EXISTING_KEY", None)

    def test_mock_http_urllib(self):
        """Verify mock_http intercepts urllib.request.urlopen."""
        self.gateway.set_fixture(
            service="api.internal.corp",
            endpoint="/data",
            response_data={"status": "MOCKED_OK", "items": [1, 2, 3]},
        )

        with self.gateway.mock_http():
            with urllib.request.urlopen("http://api.internal.corp/data") as resp:
                self.assertEqual(resp.getcode(), 200)
                content = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(content["status"], "MOCKED_OK")
                self.assertEqual(content["items"], [1, 2, 3])


class TestAbComparator(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="speckit_ab_test_")
        self.ref_dir = os.path.join(self.test_dir, "ref")
        self.dist_dir = os.path.join(self.test_dir, "dist")
        os.makedirs(self.ref_dir)
        os.makedirs(self.dist_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_equivalent_implementations_pass(self):
        """Verify AbComparator passes when ref and dist produce identical outputs."""
        ref_code = """
def handle_request(payload):
    return 200, {"success": True, "user_id": payload.get("id"), "role": "USER"}
"""
        dist_code = """
def handle_request(payload):
    # Normalized, clean code with identical contract
    uid = payload.get("id")
    return 200, {"success": True, "user_id": uid, "role": "USER"}
"""
        with open(os.path.join(self.ref_dir, "worker.py"), "w", encoding="utf-8") as f:
            f.write(ref_code)
        with open(os.path.join(self.dist_dir, "worker.py"), "w", encoding="utf-8") as f:
            f.write(dist_code)

        scenarios = [
            {
                "name": "Valid User Invocation",
                "module": "worker",
                "function": "handle_request",
                "input": {"id": "usr-42"},
            }
        ]

        comparator = AbComparator()
        report = comparator.compare_implementations(self.ref_dir, self.dist_dir, scenarios)

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["passed_count"], 1)
        self.assertEqual(report["failed_count"], 0)
        self.assertEqual(report["equivalence_rate"], "100.0%")
        self.assertTrue(os.path.exists(report["test_log_path"]))
        self.assertIsNone(report["spec_correction_path"])

    def test_functional_drift_detected(self):
        """Verify AbComparator detects schema drift and generates spec_correction.md."""
        ref_code = """
def process(payload):
    # Reference preserves legacy 'user_code' field
    return 200, {"status": "OK", "user_code": 1001, "authenticated": True}
"""
        dist_code = """
def process(payload):
    # Drift: renamed 'user_code' to 'uid'
    return 200, {"status": "OK", "uid": 1001, "authenticated": True}
"""
        with open(os.path.join(self.ref_dir, "mod.py"), "w", encoding="utf-8") as f:
            f.write(ref_code)
        with open(os.path.join(self.dist_dir, "mod.py"), "w", encoding="utf-8") as f:
            f.write(dist_code)

        scenarios = [
            {
                "name": "Authentication Edge Check",
                "module": "mod",
                "function": "process",
                "input": {"username": "admin"},
            }
        ]

        comparator = AbComparator()
        report = comparator.compare_implementations(self.ref_dir, self.dist_dir, scenarios)

        self.assertEqual(report["status"], "DRIFT_DETECTED")
        self.assertEqual(report["passed_count"], 0)
        self.assertEqual(report["failed_count"], 1)
        self.assertTrue(os.path.exists(report["spec_correction_path"]))
        self.assertIn("REQ-DRIFT-001", report["spec_correction_content"])
        self.assertIn("user_code", report["test_log_content"])


class TestModulePackager(unittest.TestCase):
    def setUp(self):
        self.pkg_dir = tempfile.mkdtemp(prefix="speckit_pkg_")

    def tearDown(self):
        shutil.rmtree(self.pkg_dir, ignore_errors=True)

    def test_package_module_generation(self):
        """Verify complete package generation: manifest, Dockerfile, runner, test_harness, README, SBOM."""
        packager = ModulePackager()
        metadata = {
            "module_name": "corp_airgap_gateway",
            "version": "1.2.0",
            "description": "Air-gapped proxy gateway with mTLS enforcement",
            "asvs_level": "ASVS L3 - High Assurance",
            "git_commit": "c0de123456",
            "mcp_tools": [
                {
                    "name": "verify_client_cert",
                    "description": "Inspects and validates X.509 client certificate",
                    "input_schema": {
                        "type": "object",
                        "properties": {"cert_pem": {"type": "string"}},
                        "required": ["cert_pem"],
                    },
                }
            ],
            "openapi_endpoints": [
                {
                    "path": "/api/v1/verify",
                    "method": "POST",
                    "summary": "Validate client credentials",
                }
            ],
        }

        dist_code = {
            "gateway.py": "# Gateway core implementation\ndef run(): return True\n",
            "utils/crypto.py": "# Crypto helper\ndef verify(): return True\n",
        }

        result = packager.package_module(self.pkg_dir, metadata, dist_code)
        self.assertEqual(result["status"], "PACKAGED")
        self.assertEqual(result["module_name"], "corp_airgap_gateway")

        # Verify files created on disk
        for fname in [
            "module_manifest.json",
            "sbom.json",
            "Dockerfile",
            "run_module.py",
            "test_harness.py",
            "README.md",
            "gateway.py",
            "utils/crypto.py",
        ]:
            fpath = os.path.join(self.pkg_dir, fname)
            self.assertTrue(os.path.exists(fpath), f"Expected file {fname} not found")

        # Verify manifest contents
        with open(os.path.join(self.pkg_dir, "module_manifest.json"), "r", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["version"], "1.2.0")
        self.assertEqual(manifest["security"]["asvs_level"], "ASVS L3 - High Assurance")
        self.assertEqual(len(manifest["protocols"]["mcp"]["tools"]), 1)

        # Run generated runner health check
        runner_res = subprocess.run(
            [sys.executable, os.path.join(self.pkg_dir, "run_module.py"), "--health"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(runner_res.returncode, 0)
        self.assertIn("OK", runner_res.stdout)

        # Run generated test harness
        harness_res = subprocess.run(
            [sys.executable, os.path.join(self.pkg_dir, "test_harness.py")],
            capture_output=True,
            text=True,
            cwd=self.pkg_dir,
        )
        self.assertEqual(harness_res.returncode, 0, f"Harness failed:\n{harness_res.stderr}")


class TestNomineePromoter(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="speckit_nominee_")
        self.conn = sqlite3.connect(":memory:")
        self.promoter = NomineePromoter()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        self.conn.close()

    def test_extract_and_normalize_domain(self):
        """Verify nominee extraction and domain normalization."""
        incident = {
            "incident_id": "INC-SOCKET-TIMEOUT-99",
            "title": "Non-blocking socket timeout invariant",
            "category": "circuit-breaker",  # should map to RESILIENCE
            "problem": "Socket was blocking indefinitely under packet drop.",
            "solution": "Enforce strict 15.0s non-blocking timeout with circuit breaker fail-fast.",
            "acceptance_criteria": [
                "Socket timeout must not exceed 15.0 seconds.",
                "Circuit breaker trips after 3 consecutive failures.",
            ],
            "compliance_standard": "Site Reliability Engineering (SRE)",
            "tags": ["socket", "resilience", "timeout"],
        }
        nominee = self.promoter.extract_nominee_from_post_sdd(incident)
        self.assertEqual(nominee["domain"], "RESILIENCE")
        self.assertIn("NOM-RESI-", nominee["nominee_id"])
        self.assertEqual(len(nominee["acceptance_criteria"]), 2)

    def test_nominee_to_template_and_promote_to_req_bank(self):
        """Verify template conversion and SQLite promotion into req_bank_templates."""
        nominee = {
            "nominee_id": "NOM-SECU-MTLS01",
            "domain": "SECURITY",
            "title": "Enforce mTLS Client Certificate Validation",
            "description": "Reject handshake without valid Corporate CA cert.",
            "rationale": "Prevents unauthorized DMZ spoofing.",
            "acceptance_criteria": ["Return SSL_CERTIFICATE_REQUIRED on missing cert."],
            "tags": ["mtls", "security"],
            "compliance_standard": "ISO-27001",
            "version": 1,
        }

        template = self.promoter.nominee_to_template(nominee)
        self.assertEqual(template["id"], "BANK-SECU-MTLS01")
        self.assertEqual(template["domain"], "SECURITY")
        self.assertIn("SSL_CERTIFICATE_REQUIRED", template["acceptance_criteria"])

        # Promote to req_bank database table
        promoted = self.promoter.promote_to_req_bank(self.conn, nominee)
        self.assertEqual(promoted["id"], "BANK-SECU-MTLS01")

        # Verify row exists in sqlite table
        row = self.conn.execute(
            "SELECT * FROM req_bank_templates WHERE id = ?", ("BANK-SECU-MTLS01",)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "SECURITY")  # domain
        self.assertEqual(row[2], "Enforce mTLS Client Certificate Validation")  # title

    def test_export_and_parse_nominee_markdown(self):
        """Verify markdown export and round-trip parsing."""
        nominee = {
            "nominee_id": "NOM-PRIV-MASK01",
            "domain": "PRIVACY",
            "title": "PII Masking in Audit Ledger",
            "description": "Sanitize and mask all personal identifiable information.",
            "rationale": "GDPR and 152-FZ compliance requirement.",
            "acceptance_criteria": [
                "Audit logs must mask phone numbers to +7 (***) ***-12-34.",
                "Plaintext passport numbers must never enter audit ledger.",
            ],
            "tags": ["pii", "gdpr", "privacy"],
            "compliance_standard": "152-FZ / GDPR",
            "source_incident": "INC-LOG-LEAK",
            "version": 1,
        }

        md_path = os.path.join(self.tmp_dir, "nominee-001.md")
        out_path = self.promoter.export_nominee_markdown(nominee, md_path)
        self.assertTrue(os.path.exists(out_path))

        parsed = self.promoter.parse_nominee_markdown(out_path)
        self.assertEqual(parsed["nominee_id"], "NOM-PRIV-MASK01")
        self.assertEqual(parsed["domain"], "PRIVACY")
        self.assertEqual(parsed["title"], "PII Masking in Audit Ledger")
        self.assertEqual(len(parsed["acceptance_criteria"]), 2)
        self.assertIn("152-FZ", parsed["compliance_standard"])


if __name__ == "__main__":
    unittest.main()
