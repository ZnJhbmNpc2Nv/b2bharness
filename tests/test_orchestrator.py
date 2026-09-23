from src.engine.orchestrator import AgentOrchestrator
from src.engine.artifact_manager import ArtifactManager
from src.engine.pipeline import PipelineEngine, PipelineState

def test_orchestrator_execution():
    orchestrator = AgentOrchestrator()
    artifact_manager = ArtifactManager()
    pipeline_engine = PipelineEngine()
    
    # Setup mock artifact
    module = "test_module"
    plan = "bash:echo hello > tests/hello.txt"
    artifact_manager.store_artifact(module, "plan", plan)
    
    # Execute
    success, msg = orchestrator.execute_plan(module, "test_session", "admin", pipeline_engine=pipeline_engine)
    
    assert success == True
    assert pipeline_engine.state == PipelineState.POST_SDD
    import os
    assert os.path.exists("tests/hello.txt")
    os.remove("tests/hello.txt")
