"""Unit & Integration test suite for Corporate Spec-Kit Pluggable Modules Architecture.
Verifies ModuleManager, Knowledge Base (ADRs), Requirements Bank, and Stage Attachments.
Zero external dependencies; standard library unittest.
"""
import unittest
import os
import sys
import tempfile
import json
import base64

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from server.db import SpecDatabase
from server.lineage import LineageEngine
from modules.manager import ModuleManager
from modules.knowledge_base.module import KnowledgeBaseModule
from modules.req_bank.module import RequirementsBankModule
from modules.stage_attachments.module import StageAttachmentsModule


class TestModularArchitecture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db = SpecDatabase(self.tmp.name)
        self.modules = ModuleManager(self.db, modules_dir=os.path.join(SCRIPT_DIR, "modules"))
        self.lineage = LineageEngine(self.db, module_manager=self.modules)

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            try:
                os.remove(self.tmp.name)
            except Exception:
                pass

    def test_module_discovery(self):
        """Verify dynamic discovery of built-in modules."""
        manifest = self.modules.get_modules_manifest()
        slugs = [m["slug"] for m in manifest]
        self.assertIn("knowledge_base", slugs)
        self.assertIn("req_bank", slugs)
        self.assertIn("stage_attachments", slugs)

    def test_knowledge_base_articles_and_linking(self):
        """Verify Knowledge Base ADRs and requirement links."""
        kb_mod = self.modules.modules.get("knowledge_base")
        self.assertIsNotNone(kb_mod)

        # Check seeded ADRs
        with self.db.get_connection() as conn:
            articles = conn.execute("SELECT * FROM kb_articles").fetchall()
            self.assertGreaterEqual(len(articles), 3)

        # Check lineage contribution
        contrib = kb_mod.get_lineage_contributions(self.db.get_connection(), "proj-airgap-gateway")
        self.assertGreaterEqual(len(contrib["nodes"]), 3)
        self.assertGreaterEqual(len(contrib["edges"]), 3)
        self.assertTrue(any("ADR-001" in n["label"] for n in contrib["nodes"]))

    def test_requirements_bank_adoption(self):
        """Verify adopting a requirement template from the Bank into active specification."""
        bank_mod = self.modules.modules.get("req_bank")
        self.assertIsNotNone(bank_mod)

        with self.db.get_connection() as conn:
            templates = conn.execute("SELECT * FROM req_bank_templates").fetchall()
            self.assertGreaterEqual(len(templates), 4)

        # Adopt BANK-PII-04
        reqs_before = self.db.list_requirements("proj-airgap-gateway")
        count_before = len(reqs_before)

        # Mock handler to call adopt
        class MockHandler:
            def __init__(self, payload):
                self._payload = payload
                self.status = None
                self.data = None
            def _read_json_body(self):
                return self._payload
            def _send_json(self, status, data):
                self.status = status
                self.data = data

        handler = MockHandler({
            "template_id": "BANK-PII-04",
            "spec_id": "proj-airgap-gateway",
            "author_name": "Compliance Lead",
            "author_role": "DPO"
        })
        bank_mod._handle_adopt_template(handler)

        self.assertEqual(handler.status, 201)
        self.assertEqual(handler.data["status"], "adopted")
        
        reqs_after = self.db.list_requirements("proj-airgap-gateway")
        self.assertEqual(len(reqs_after), count_before + 1)
        adopted_req = handler.data["requirement"]
        self.assertIn("BANK-PII-04", adopted_req["rationale"])
        self.assertEqual(adopted_req["created_by"], "Compliance Lead")

    def test_stage_attachments_upload_and_lineage(self):
        """Verify file upload and stage attachment lineage synthesis."""
        att_mod = self.modules.modules.get("stage_attachments")
        self.assertIsNotNone(att_mod)

        # Upload a custom OpenAPI file via handler
        sample_yaml = "openapi: 3.0.0\ninfo:\n  title: Test Service\n  version: 1.0.0"
        b64_content = base64.b64encode(sample_yaml.encode("utf-8")).decode("utf-8")

        class MockHandler:
            def __init__(self, payload):
                self._payload = payload
                self.status = None
                self.data = None
            def _read_json_body(self):
                return self._payload
            def _send_json(self, status, data):
                self.status = status
                self.data = data

        handler = MockHandler({
            "spec_id": "proj-airgap-gateway",
            "stage": "REQUIREMENT",
            "entity_id": "REQ-SEC-001",
            "filename": "custom_api_spec.yaml",
            "content_base64": b64_content,
            "uploaded_by": "Test Architect",
            "uploaded_role": "Lead",
            "notes": "Custom test swagger file"
        })
        att_mod._handle_upload_attachment(handler)

        self.assertEqual(handler.status, 201)
        self.assertIn("file_id", handler.data)

        # Verify lineage contributions
        contrib = att_mod.get_lineage_contributions(self.db.get_connection(), "proj-airgap-gateway")
        self.assertGreaterEqual(len(contrib["nodes"]), 4) # 3 seeded + 1 uploaded
        self.assertTrue(any("custom_api_spec.yaml" in n["label"] for n in contrib["nodes"]))

    def test_lineage_engine_full_integration(self):
        """Verify that LineageEngine merges module contributions into full DAG."""
        graph = self.lineage.get_graph_data("proj-airgap-gateway")
        node_types = {n["node_type"] for n in graph["nodes"]}
        self.assertIn("KNOWLEDGE", node_types)
        self.assertIn("ATTACHMENT", node_types)
        self.assertIn("REQUIREMENT", node_types)


if __name__ == "__main__":
    unittest.main()
