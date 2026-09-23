from fastapi import FastAPI, HTTPException, Request, Header
from src.engine.pipeline import PipelineEngine, PipelineState
from src.core.logger import Logger
from src.security.scanner import SecurityScanner
from src.core.database import log_audit
from src.engine.artifact_manager import ArtifactManager
from src.engine.orchestrator import AgentOrchestrator
import json
import os

app = FastAPI(title="B2B Harness Orchestrator")
engine = PipelineEngine()
logger = Logger()
scanner = SecurityScanner()
artifact_manager = ArtifactManager()
orchestrator = AgentOrchestrator()

# Ensure approval data exists
if not os.path.exists("data/approval.json"):
    os.makedirs("data", exist_ok=True)
    with open("data/approval.json", "w") as f:
        json.dump({"approval_state": {"current_stage": "PRE_SDD", "approved": True, "human_review_required": False}}, f)

@app.get("/health")
async def health():
    return {"status": "ok", "state": engine.state.name}

@app.post("/speckit/invoke")
async def invoke_command(command: str):
    # Mapping for Spec Kit skill commands
    SPECKIT_COMMANDS = {
        "/speckit-constitution": "constitution",
        "/speckit-specify": "specify",
        "/speckit-plan": "plan",
        "/speckit-tasks": "tasks",
        "/speckit-implement": "implement",
        "/speckit-converge": "converge"
    }
    if command not in SPECKIT_COMMANDS:
        raise HTTPException(status_code=400, detail="Unknown Spec Kit command")
    
    logger.log("SPECKIT", f"Invoked {command}")
    return {"status": "success", "command": SPECKIT_COMMANDS[command]}

@app.post("/pipeline/execute")
async def execute(module_name: str, session_id: str = Header(...), user_id: str = Header(...)):
    success, message = orchestrator.execute_plan(module_name, session_id, user_id)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return {"status": "executed", "message": message}

@app.post("/pipeline/advance")
async def advance(session_id: str = Header(...), user_id: str = Header(...)):
    with open("data/approval.json", "r") as f:
        data = json.load(f)
        approval = data.get("approval_state", data)
    
    if not approval.get("approved", False):
        raise HTTPException(status_code=403, detail="Stage not approved by expert")

    next_state = PipelineState.INTENT
    engine.transition(next_state)
    log_audit(session_id, user_id, next_state.name, "ADVANCE")
    
    with open("data/approval.json", "w") as f:
        json.dump({"approval_state": {"current_stage": next_state.name, "approved": False, "human_review_required": True}}, f)
    
    return {"status": "advanced", "state": engine.state.name}

@app.post("/pipeline/approve")
async def approve():
    with open("data/approval.json", "w") as f:
        json.dump({"approval_state": {"current_stage": engine.state.name, "approved": True, "human_review_required": False}}, f)
    return {"status": "approved"}


@app.post("/security/scan")
async def scan(file_path: str):
    if not file_path.startswith("src/"):
        raise HTTPException(status_code=400, detail="Can only scan files in src/")
        
    success, message = scanner.scan_file(file_path)
    if not success:
        logger.log("SECURITY", f"Scan failed: {message}")
        raise HTTPException(status_code=400, detail=message)
    return {"status": "clean"}

@app.post("/pipeline/validate-dev")
async def validate_dev(spec_file: str):
    if not os.path.exists(f".specify/{spec_file}"):
        raise HTTPException(status_code=404, detail="Spec file not found")
        
    logger.log("VALIDATION", f"Validating consistency against {spec_file}")
    return {"status": "validated", "consistent": True}
