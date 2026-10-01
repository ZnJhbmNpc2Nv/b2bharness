from fastapi import FastAPI, HTTPException, Header, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import json
import os
import asyncio
from datetime import datetime, timezone

from src.engine.pipeline import PipelineEngine, PipelineState
from src.core.logger import Logger
from src.security.scanner import SecurityScanner
from src.core.database import log_audit, init_db
from src.engine.artifact_manager import ArtifactManager
from src.engine.orchestrator import AgentOrchestrator
from src.api.llm_client import LLMClient

# Initialize database
init_db()

app = FastAPI(
    title="B2B Harness SDD Orchestrator",
    description="Heavyweight Specification-Driven Development Engine & Agent Swarm API",
    version="2.0.0"
)

# Enable CORS for React/Vite Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = PipelineEngine()
logger = Logger()
scanner = SecurityScanner()
artifact_manager = ArtifactManager()
orchestrator = AgentOrchestrator()
llm_client = LLMClient()

# Request/Response Schemas
class IntentPayload(BaseModel):
    text: str
    session_id: Optional[str] = "session_default"

class PreSddPayload(BaseModel):
    source_path: str
    session_id: Optional[str] = "session_default"

class SpecPayload(BaseModel):
    intent: Optional[str] = None
    session_id: Optional[str] = "session_default"

class PlanPayload(BaseModel):
    spec: Optional[str] = None
    session_id: Optional[str] = "session_default"

class DevPayload(BaseModel):
    session_id: Optional[str] = "session_default"
    max_rounds: Optional[int] = 3

class ApprovalPayload(BaseModel):
    session_id: str
    artifact_type: str
    approved: bool
    comment: Optional[str] = ""

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "state": engine.state.name,
        "llm_configured": llm_client.is_configured(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/pipeline/graph")
async def get_graph():
    return {
        "nodes": [state.name for state in PipelineState],
        "current": engine.state.name,
        "stages": [
            {"id": "PRE_SDD", "name": "1. PRE-SDD Reverse Engineering", "role": "Architect (Opus 5.5)"},
            {"id": "INTENT", "name": "2. Canonical Intent Normalizer", "role": "Architect (Opus 5.5)"},
            {"id": "SPEC", "name": "3. Spec & Security Synthesis", "role": "Architect (Opus 5.5)"},
            {"id": "PLAN", "name": "4. Traceable Plan Matrix", "role": "Architect (Opus 5.5)"},
            {"id": "DEV", "name": "5. TDD & Sandbox Coding", "role": "Coder (Sonnet 5) + Tester (Gemini 3.7)"},
            {"id": "POST_SDD", "name": "6. Self-Healing & Gate 2 Audit", "role": "Auditor (Kimi K3 / Sonnet 5)"},
            {"id": "AB_TEST", "name": "7. A/B Parity Evaluation", "role": "Tester (Gemini 3.7)"}
        ]
    }

@app.post("/pipeline/pre-sdd")
async def run_pre_sdd(payload: PreSddPayload):
    if not os.path.exists(payload.source_path):
        raise HTTPException(status_code=404, detail=f"Source path not found: {payload.source_path}")
    res = await orchestrator.execute_pre_sdd(payload.source_path, payload.session_id)
    log_audit(payload.session_id, "api_user", "PRE_SDD", "COMPLETED")
    return res

@app.post("/pipeline/refine-intent")
async def refine_intent(payload: IntentPayload):
    res = await orchestrator.execute_intent(payload.text, payload.session_id or "session_default")
    log_audit(payload.session_id or "session_default", "api_user", "INTENT", "COMPLETED")
    return {"status": "refined", "refined_text": res["content"], "artifact_path": res["artifact_path"]}

@app.post("/pipeline/spec")
async def generate_spec(payload: SpecPayload):
    session_path = os.path.join("data/staging", payload.session_id)
    intent_content = payload.intent
    if not intent_content:
        intent_file = os.path.join(session_path, "intent.md")
        if os.path.exists(intent_file):
            with open(intent_file, "r", encoding="utf-8") as f:
                intent_content = f.read()
        else:
            raise HTTPException(status_code=400, detail="Intent not provided and intent.md not found in staging")

    res = await orchestrator.execute_spec(intent_content, payload.session_id)
    engine.transition(PipelineState.SPEC)
    log_audit(payload.session_id, "api_user", "SPEC", "COMPLETED")
    return res

@app.post("/pipeline/plan")
async def generate_plan(payload: PlanPayload):
    session_path = os.path.join("data/staging", payload.session_id)
    spec_content = payload.spec
    if not spec_content:
        spec_file = os.path.join(session_path, "spec.md")
        if os.path.exists(spec_file):
            with open(spec_file, "r", encoding="utf-8") as f:
                spec_content = f.read()
        else:
            raise HTTPException(status_code=400, detail="Spec not provided and spec.md not found in staging")

    res = await orchestrator.generate_plan_artifact(spec_content, payload.session_id)
    engine.transition(PipelineState.PLAN)
    log_audit(payload.session_id, "api_user", "PLAN", "COMPLETED")
    return res

@app.post("/pipeline/execute")
async def execute_legacy(module_name: str, session_id: str = Header("default"), user_id: str = Header("admin")):
    success, message = orchestrator.execute_plan(module_name, session_id, user_id, pipeline_engine=engine)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return {"status": "executed", "message": message}

@app.post("/pipeline/dev")
async def execute_dev_pipeline(payload: DevPayload):
    res = await orchestrator.execute_dev_and_post_sdd(payload.session_id, max_repair_rounds=payload.max_rounds or 3)
    if res["is_green"]:
        engine.transition(PipelineState.POST_SDD)
    log_audit(payload.session_id, "api_user", "DEV", f"RESULT_{res['status'].upper()}")
    return res

@app.get("/pipeline/artifacts/{session_id}/{artifact_type}")
async def get_artifact(session_id: str, artifact_type: str):
    path = f"data/staging/{session_id}/{artifact_type}.md"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Artifact not found")
    with open(path, "r", encoding="utf-8") as f:
        return {"content": f.read()}

@app.post("/pipeline/advance")
async def advance(session_id: str = Header("default"), user_id: str = Header("admin")):
    states = list(PipelineState)
    try:
        current_idx = states.index(engine.state)
        next_state = states[current_idx + 1] if current_idx + 1 < len(states) else states[-1]
    except Exception:
        next_state = PipelineState.INTENT

    engine.transition(next_state)
    log_audit(session_id, user_id, next_state.name, "ADVANCE")
    return {"status": "advanced", "state": engine.state.name}

@app.post("/pipeline/approve")
async def approve_stage(payload: Optional[ApprovalPayload] = None):
    session_id = payload.session_id if payload else "session_default"
    artifact_type = payload.artifact_type if payload else "intent"
    comment = payload.comment if payload else ""
    orchestrator.approve_artifact(session_id, artifact_type, comment or "")
    log_audit(session_id, "expert_user", artifact_type.upper(), f"APPROVED: {comment}")
    return {"status": "approved", "artifact_type": artifact_type}

@app.post("/security/scan")
async def scan(file_path: str):
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    success, message = scanner.scan_file(file_path)
    if not success:
        logger.log("SECURITY", f"Scan failed: {message}")
        raise HTTPException(status_code=400, detail=message)
    return {"status": "clean", "message": message}

@app.post("/config/keys")
async def save_key(data: dict):
    os.makedirs("data", exist_ok=True)
    with open("data/keys.json", "w", encoding="utf-8") as f:
        json.dump({"key": data.get("value"), "active": True, "added_at": datetime.now(timezone.utc).timestamp()}, f)
    # Refresh llm client
    global llm_client
    llm_client = LLMClient()
    return {"status": "success"}

@app.delete("/config/keys")
async def clear_key():
    if os.path.exists("data/keys.json"):
        os.remove("data/keys.json")
    global llm_client
    llm_client = LLMClient()
    return {"status": "cleared"}

@app.get("/config/status")
async def get_key_status():
    if not os.path.exists("data/keys.json"):
        return {"active": False}
    with open("data/keys.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"active": data.get("active", False)}
