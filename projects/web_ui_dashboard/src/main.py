import sys
sys.path.append("D:\\b2bharness")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.config import save_env_key
from src.engine.pipeline import PipelineEngine, PipelineState

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
    import json
    import os
    try:
        if os.path.exists("data/approval.json"):
            with open("data/approval.json", "r") as f:
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
    if engine.state == PipelineState.DEV:
        engine.transition(PipelineState.POST_SDD)
        return {"status": "advanced", "stage": engine.state.name}
    return {"status": "transitioned_to_next"}

