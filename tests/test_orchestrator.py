from src.engine.orchestrator import AgentOrchestrator
from src.engine.artifact_manager import ArtifactManager

def test_orchestrator_execution():
    orchestrator = AgentOrchestrator()
    artifact_manager = ArtifactManager()
    
    # Setup mock artifact
    module = "test_module"
    plan = "bash:echo hello > tests/hello.txt"
    artifact_manager.store_artifact(module, "plan", plan)
    
    # Execute
    success, msg = orchestrator.execute_plan(module, "test_session", "admin")
    
    assert success == True
    import os
    assert os.path.exists("tests/hello.txt")
    os.remove("tests/hello.txt")
