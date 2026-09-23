import sys
sys.path.append("D:\\b2bharness")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.config import save_env_key
from src.engine.pipeline import PipelineEngine, PipelineState
import json
import os

app = FastAPI(title="UI Dashboard Backend")

# Добавляем CORS, чтобы React мог обращаться к бэкенду
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Загружаем актуальное состояние из файла, чтобы избежать проблем с reload
def get_current_stage():
    try:
        if os.path.exists("D:\\b2bharness\\data\\approval.json"):
            with open("D:\\b2bharness\\data\\approval.json", "r") as f:
                data = json.load(f)
                return data.get("approval_state", {}).get("current_stage", "UNKNOWN")
    except Exception:
        pass
    return "UNKNOWN"

engine = PipelineEngine()

class ApiKeyRequest(BaseModel):
    key_name: str
    value: str

@app.get("/status")
async def get_status():
    return {"stage": get_current_stage()}

@app.get("/health")
async def health():
    return {"status": "ok", "stage": engine.state.name}

@app.post("/config/keys")
async def update_keys(data: ApiKeyRequest):
    save_env_key(data.key_name, data.value)
    return {"status": "saved"}

@app.post("/pipeline/advance")
async def advance():
    if os.path.exists("D:\\b2bharness\\data\\approval.json"):
        with open("D:\\b2bharness\\data\\approval.json", "r") as f:
            approval = json.load(f)
        
        if not approval["approval_state"].get("approved", False):
            raise HTTPException(status_code=403, detail="Expert approval required: please approve stage in approval.json")

    if engine.state == PipelineState.DEV:
        engine.transition(PipelineState.POST_SDD)
        # Сбрасываем approved после перехода
        with open("D:\\b2bharness\\data\\approval.json", "w") as f:
            json.dump({"approval_state": {"current_stage": "POST_SDD", "approved": False, "human_review_required": True}}, f)
        return {"status": "advanced", "stage": "POST_SDD"}
    
    return {"status": "no_transition"}

@app.post("/pipeline/approve")
async def approve():
    with open("D:\\b2bharness\\data\\approval.json", "w") as f:
        json.dump({"approval_state": {"current_stage": engine.state.name, "approved": True, "human_review_required": False}}, f)
    return {"status": "approved"}
