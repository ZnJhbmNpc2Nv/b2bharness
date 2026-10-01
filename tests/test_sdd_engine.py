import pytest
import os
import shutil
import asyncio
from src.engine.orchestrator import AgentOrchestrator
from src.engine.pipeline import PipelineEngine, PipelineState
from src.security.scanner import SecurityScanner

@pytest.fixture
def orchestrator_fixture(tmp_path):
    staging_dir = str(tmp_path / "staging")
    sandbox_dir = str(tmp_path / "sandbox")
    return AgentOrchestrator(staging_dir=staging_dir, sandbox_dir=sandbox_dir)

@pytest.mark.anyio
async def test_pre_sdd_and_intent(orchestrator_fixture, tmp_path):
    # 1. Create a dummy PoC file
    poc_file = tmp_path / "sample_poc.py"
    poc_file.write_text("def add(a, b): return a + b\n")

    session_id = "test_sess_01"
    res_pre = await orchestrator_fixture.execute_pre_sdd(str(poc_file), session_id)
    assert res_pre["status"] == "completed"
    assert os.path.exists(res_pre["artifact_path"])
    assert "DISCOVERY" in res_pre["content"]

    # 2. Run Intent
    res_intent = await orchestrator_fixture.execute_intent(res_pre["content"], session_id)
    assert res_intent["status"] == "completed"
    assert os.path.exists(res_intent["artifact_path"])
    assert "Goals" in res_intent["content"]

@pytest.mark.anyio
async def test_spec_and_plan(orchestrator_fixture):
    session_id = "test_sess_02"
    intent_text = "# INTENT\n## 1. Goals\nCreate a safe mathematical calculator."
    
    # 1. Spec
    res_spec = await orchestrator_fixture.execute_spec(intent_text, session_id)
    assert res_spec["status"] == "completed"
    assert os.path.exists(res_spec["artifact_path"])

    # 2. Plan
    res_plan = await orchestrator_fixture.generate_plan_artifact(res_spec["content"], session_id)
    assert res_plan["status"] == "completed"
    assert os.path.exists(res_plan["artifact_path"])

def test_parse_file_blocks(orchestrator_fixture):
    raw_response = """
Here is the code:

*** FILE: calculator.py ***
class Calculator:
    def add(self, a, b):
        return a + b
*** END FILE ***

*** FILE: test_calc.py ***
import unittest
class TestCalc(unittest.TestCase):
    def test_add(self):
        self.assertEqual(1 + 1, 2)
*** END FILE ***
"""
    files = orchestrator_fixture.parse_file_blocks(raw_response)
    assert "calculator.py" in files
    assert "test_calc.py" in files
    assert "class Calculator:" in files["calculator.py"]
    assert "class TestCalc" in files["test_calc.py"]

def test_security_scanner(tmp_path):
    scanner = SecurityScanner()
    
    # Clean code
    clean_file = tmp_path / "clean.py"
    clean_file.write_text("def multiply(x, y): return x * y\n")
    is_clean, msg = scanner.scan_file(str(clean_file))
    assert is_clean is True
    assert "No security issues" in msg

    # Vulnerable code with forbidden eval
    vuln_file = tmp_path / "vuln.py"
    vuln_file.write_text("def dangerous(x): return eval(x)\n")
    is_clean, msg = scanner.scan_file(str(vuln_file))
    assert is_clean is False
    assert "Forbidden function 'eval'" in msg

@pytest.mark.anyio
async def test_async_approval_gate(orchestrator_fixture):
    session_id = "test_gate_sess"
    orchestrator_fixture.create_gate_request(session_id, "spec", "# Spec Content")
    
    # Background task to approve after 0.2s
    async def auto_approve():
        await asyncio.sleep(0.2)
        orchestrator_fixture.approve_artifact(session_id, "spec", "Looks solid")

    asyncio.create_task(auto_approve())
    approved, comment = await orchestrator_fixture.wait_for_verdict(session_id, "spec", timeout_seconds=2.0)
    assert approved is True
    assert comment == "Looks solid"
