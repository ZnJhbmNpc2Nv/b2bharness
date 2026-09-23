import pytest
from src.engine.pipeline import PipelineEngine, PipelineState

def test_pipeline_transition():
    engine = PipelineEngine()
    assert engine.state == PipelineState.PRE_SDD
    engine.transition(PipelineState.INTENT)
    assert engine.state == PipelineState.INTENT

def test_security_scanner():
    from src.security.scanner import SecurityScanner
    scanner = SecurityScanner()
    # Создадим временный файл с "опасным" кодом
    with open("tests/test_vuln.py", "w") as f:
        f.write("eval('print(1)')")
    
    success, _ = scanner.scan_file("tests/test_vuln.py")
    assert success == False
