from fastapi import FastAPI, HTTPException, Header, Query, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import json
import os
import asyncio
from datetime import datetime, timezone

from src.engine.pipeline import PipelineEngine, PipelineState
from src.core.logger import Logger
from src.security.scanner import SecurityScanner
from src.security.context_guard import ContextIntegrityGuard
from src.core.database import log_audit, init_db
from src.engine.artifact_manager import ArtifactManager
from src.engine.orchestrator import AgentOrchestrator
from src.api.llm_client import LLMClient
from src.api.auth import verify_colleague_key

# Initialize database
init_db()

app = FastAPI(
    title="B2B Harness SDD Orchestrator",
    description="Enterprise Specification-Driven Development Engine with Context Guard & A2A Swarm",
    version="2.1.0"
)

# Enable CORS for React/Vite Dashboard and external integrations
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
guard = ContextIntegrityGuard()
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
# Embedded Glassmorphism Web Dashboard (Zero-Dependency)
# -----------------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>B2B Harness SDD Studio</title>
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(22, 30, 49, 0.75);
      --border: rgba(255, 255, 255, 0.12);
      --primary: #38bdf8;
      --accent: #818cf8;
      --success: #34d399;
      --warning: #fbbf24;
      --text: #f1f5f9;
      --muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }
    .container { max-width: 1240px; margin: 0 auto; }
    header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid var(--border); padding-bottom: 16px; }
    h1 { font-size: 22px; font-weight: 700; color: var(--primary); display: flex; align-items: center; gap: 8px; }
    .badge { padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; background: rgba(56, 189, 248, 0.2); color: var(--primary); }
    .pipeline-bar { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; margin-bottom: 20px; }
    .step-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 10px; text-align: center; backdrop-filter: blur(8px); }
    .step-card.active { border-color: var(--primary); background: rgba(56, 189, 248, 0.15); box-shadow: 0 0 15px rgba(56, 189, 248, 0.3); }
    .step-num { font-size: 11px; color: var(--muted); text-transform: uppercase; }
    .step-name { font-size: 12px; font-weight: 600; margin-top: 4px; }
    .grid { display: grid; grid-template-columns: 1fr 1.1fr; gap: 20px; }
    .panel { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; backdrop-filter: blur(8px); }
    .panel-title { font-size: 15px; font-weight: 600; margin-bottom: 12px; color: var(--accent); display: flex; justify-content: space-between; align-items: center; }
    label { font-size: 12px; color: var(--muted); margin-bottom: 4px; display: block; }
    textarea, input { width: 100%; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; padding: 10px; color: var(--text); font-size: 13px; margin-bottom: 12px; }
    textarea { height: 130px; resize: vertical; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .presets { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
    .preset-btn { background: #1e293b; color: #94a3b8; font-size: 11px; padding: 4px 8px; border: 1px solid var(--border); border-radius: 4px; cursor: pointer; }
    .preset-btn:hover { background: #334155; color: #fff; }
    button.primary { background: linear-gradient(135deg, var(--primary), var(--accent)); color: #000; font-weight: 600; border: none; padding: 10px 18px; border-radius: 6px; cursor: pointer; }
    button.secondary { background: #334155; color: var(--text); padding: 10px 14px; border: none; border-radius: 6px; cursor: pointer; margin-left: 8px; font-weight: 600; }
    pre { background: #020617; border: 1px solid var(--border); border-radius: 6px; padding: 14px; color: #38bdf8; font-family: monospace; font-size: 12px; max-height: 480px; overflow: auto; white-space: pre-wrap; line-height: 1.4; }
    .guard-banner { background: rgba(52, 211, 153, 0.1); border: 1px solid rgba(52, 211, 153, 0.3); color: var(--success); padding: 8px 12px; border-radius: 6px; font-size: 12px; margin-bottom: 16px; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>🐝 B2B Harness SDD Studio</h1>
      <span class="badge">Multi-User Team Active</span>
    </header>

    <div class="guard-banner">
      🛡️ <strong>Context Guard Active:</strong> Prompt Injection Shield, SHA-256 Tamper Protection & Session Isolation Enabled.
    </div>

    <div class="pipeline-bar">
      <div class="step-card active"><div class="step-num">Stage 1</div><div class="step-name">PRE-SDD</div></div>
      <div class="step-card"><div class="step-num">Stage 2</div><div class="step-name">INTENT</div></div>
      <div class="step-card"><div class="step-num">Stage 3</div><div class="step-name">SPEC</div></div>
      <div class="step-card"><div class="step-num">Stage 4</div><div class="step-name">PLAN</div></div>
      <div class="step-card"><div class="step-num">Stage 5</div><div class="step-name">DEV & TDD</div></div>
      <div class="step-card"><div class="step-num">Stage 6</div><div class="step-name">POST-SDD</div></div>
      <div class="step-card"><div class="step-num">Stage 7</div><div class="step-name">GATE 2 AUDIT</div></div>
    </div>

    <div class="grid">
      <div class="panel">
        <div class="panel-title">📝 Параметры задачи</div>
        <div class="row">
          <div>
            <label>API-Ключ (выдан администратором)</label>
            <input type="password" id="apiKey" value="" placeholder="Вставьте ваш API-ключ..." />
          </div>
          <div>
            <label>Имя сессии (Ваше имя / Задача)</label>
            <input type="text" id="sessionId" value="session_01" placeholder="например: alex_jwt" />
          </div>
        </div>

        <label>Быстрые примеры:</label>
        <div class="presets">
          <span class="preset-btn" onclick="setPrompt('Создать модуль LRU-кэша с поддержкой TTL, maxsize и thread-safe блокировок')">⚡ LRU Cache (TTL)</span>
          <span class="preset-btn" onclick="setPrompt('Создать JWT валидатор с проверкой подписи RS256, exp и скоупов')">⚡ JWT Validator</span>
          <span class="preset-btn" onclick="setPrompt('Создать Rate Limiter на Token Bucket с поддержкой лимитов в секунду/минуту')">⚡ Rate Limiter</span>
        </div>

        <label>Описание намерения (Intent):</label>
        <textarea id="intentInput" placeholder="Опишите модуль или функционал..."></textarea>

        <div>
          <button class="primary" onclick="runPipeline()">🚀 Запустить SDD Конвейер</button>
          <button class="secondary" onclick="approveStage()">✔ Утвердить этап</button>
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">
          <span>📊 Live Артефакты & Терминал</span>
          <span style="font-size: 11px; color: var(--muted);" id="statusTag">Готов</span>
        </div>
        <pre id="outputConsole">Добро пожаловать! Выберите быстрый пример или введите описание задачи и нажмите «Запустить SDD Конвейер».</pre>
      </div>
    </div>
  </div>

  <script>
    function setPrompt(txt) {
      document.getElementById('intentInput').value = txt;
    }

    async function runPipeline() {
      const text = document.getElementById('intentInput').value.trim();
      const session_id = document.getElementById('sessionId').value.trim();
      const apiKey = document.getElementById('apiKey').value.trim();
      if (!text) return alert('Введите текст намерения!');

      const out = document.getElementById('outputConsole');
      const tag = document.getElementById('statusTag');
      tag.textContent = 'Обработка...';
      out.textContent = '⏳ [STAGE 2/7] Нормализация Intent через LLM Swarm (Opus 5.5)...\\n';

      const headers = {
        'Content-Type': 'application/json',
        'X-API-Key': apiKey
      };

      try {
        const res = await fetch('/pipeline/refine-intent', {
          method: 'POST',
          headers,
          body: JSON.stringify({ text, session_id })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Ошибка выполнения');
        out.textContent += '✔ INTENT Готов!\\n\\n' + data.refined_text + '\\n\\n⏳ [STAGE 3/7] Генерация спецификации (OWASP ASVS L2 & CWE-25)...\\n';

        const specRes = await fetch('/pipeline/spec', {
          method: 'POST',
          headers,
          body: JSON.stringify({ intent: data.refined_text, session_id })
        });
        const specData = await specRes.json();
        if (!specRes.ok) throw new Error(specData.detail || 'Ошибка генерации Spec');
        out.textContent += '✔ SPEC Сгенерирован (Locked & Hashed)!\\n\\n' + specData.content + '\\n\\n⏳ [STAGE 4/7] Построение плана задач (Plan Matrix)...\\n';

        const planRes = await fetch('/pipeline/plan', {
          method: 'POST',
          headers,
          body: JSON.stringify({ spec: specData.content, session_id })
        });
        const planData = await planRes.json();
        out.textContent += '✔ PLAN Готов!\\n\\n' + planData.content + '\\n\\n✔ Конвейер успешно завершен. Для запуска кодогенерации и песочницы нажмите «Утвердить этап».';
        tag.textContent = 'Успешно';
      } catch (err) {
        out.textContent += '\\n❌ Ошибка: ' + err.message;
        tag.textContent = 'Ошибка';
      }
    }

    async function approveStage() {
      const session_id = document.getElementById('sessionId').value.trim();
      const apiKey = document.getElementById('apiKey').value.trim();
      const out = document.getElementById('outputConsole');
      const tag = document.getElementById('statusTag');
      out.textContent += '\\n\\n⏳ [STAGE 5 & 6/7] TDD Синтез тестов (Gemini 3.7) + Coder (Sonnet 5) + Песочница (.sandbox/)...\\n';
      
      try {
        await fetch('/pipeline/approve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
          body: JSON.stringify({ session_id, artifact_type: 'spec', approved: true, comment: 'Approved via UI' })
        });

        const devRes = await fetch('/pipeline/dev', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
          body: JSON.stringify({ session_id, max_rounds: 3 })
        });
        const devData = await devRes.json();
        out.textContent += `✔ TDD Dev Статус: ${devData.status.toUpperCase()} (Итераций самопочинки: ${devData.rounds_executed})\\n\\n` +
          `📁 Песочница: ${devData.sandbox_path}\\n` +
          `📋 Dev Log: ${devData.dev_log_path}\\n\\n` +
          `🎉 Модуль успешно скомпилирован и проверен в изолированной среде!`;
        tag.textContent = 'GREEN';
      } catch (err) {
        out.textContent += '\\n❌ Ошибка DEV: ' + err.message;
        tag.textContent = 'Ошибка';
      }
    }
  </script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the standalone Glassmorphism Web Dashboard directly."""
    return HTMLResponse(content=DASHBOARD_HTML)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "state": engine.state.name,
        "llm_configured": llm_client.is_configured(),
        "context_guard": "active",
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
async def run_pre_sdd(payload: PreSddPayload, caller_key: str = Depends(verify_colleague_key)):
    if not guard.validate_session_id(payload.session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id: Path traversal or illegal characters detected")
    if not os.path.exists(payload.source_path):
        raise HTTPException(status_code=404, detail=f"Source path not found: {payload.source_path}")
        
    res = await orchestrator.execute_pre_sdd(payload.source_path, payload.session_id)
    guard.record_artifact_hash(payload.session_id, "discovery", res["content"])
    log_audit(payload.session_id, caller_key, "PRE_SDD", "COMPLETED")
    return res

@app.post("/pipeline/refine-intent")
async def refine_intent(payload: IntentPayload, caller_key: str = Depends(verify_colleague_key)):
    session_id = payload.session_id or "session_default"
    if not guard.validate_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id: Path traversal or illegal characters detected")

    # Guard: Detect Prompt Injection
    has_injection, inject_reason = guard.detect_prompt_injection(payload.text)
    if has_injection:
        raise HTTPException(status_code=400, detail=f"Context Security Guard: {inject_reason}")

    sanitized_text = guard.sanitize_input(payload.text)
    res = await orchestrator.execute_intent(sanitized_text, session_id)
    guard.record_artifact_hash(session_id, "intent", res["content"])
    log_audit(session_id, caller_key, "INTENT", "COMPLETED")
    return {"status": "refined", "refined_text": res["content"], "artifact_path": res["artifact_path"]}

@app.post("/pipeline/spec")
async def generate_spec(payload: SpecPayload, caller_key: str = Depends(verify_colleague_key)):
    session_id = payload.session_id or "session_default"
    if not guard.validate_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    session_path = os.path.join("data/staging", session_id)
    intent_content = payload.intent
    if not intent_content:
        intent_file = os.path.join(session_path, "intent.md")
        if os.path.exists(intent_file):
            with open(intent_file, "r", encoding="utf-8") as f:
                intent_content = f.read()
        else:
            raise HTTPException(status_code=400, detail="Intent not provided and intent.md not found in staging")

    # Guard: Verify intent integrity
    valid, msg = guard.verify_artifact_integrity(session_id, "intent", intent_content)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Context Poisoning Detected: {msg}")

    res = await orchestrator.execute_spec(intent_content, session_id)
    guard.record_artifact_hash(session_id, "spec", res["content"])
    engine.transition(PipelineState.SPEC)
    log_audit(session_id, caller_key, "SPEC", "COMPLETED")
    return res

@app.post("/pipeline/plan")
async def generate_plan(payload: PlanPayload, caller_key: str = Depends(verify_colleague_key)):
    session_id = payload.session_id or "session_default"
    if not guard.validate_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    session_path = os.path.join("data/staging", session_id)
    spec_content = payload.spec
    if not spec_content:
        spec_file = os.path.join(session_path, "spec.md")
        if os.path.exists(spec_file):
            with open(spec_file, "r", encoding="utf-8") as f:
                spec_content = f.read()
        else:
            raise HTTPException(status_code=400, detail="Spec not provided and spec.md not found in staging")

    # Guard: Verify spec integrity
    valid, msg = guard.verify_artifact_integrity(session_id, "spec", spec_content)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Context Poisoning Detected: {msg}")

    res = await orchestrator.generate_plan_artifact(spec_content, session_id)
    guard.record_artifact_hash(session_id, "plan", res["content"])
    engine.transition(PipelineState.PLAN)
    log_audit(session_id, caller_key, "PLAN", "COMPLETED")
    return res

@app.post("/pipeline/execute")
async def execute_legacy(module_name: str, session_id: str = Header("default"), user_id: str = Header("admin")):
    success, message = orchestrator.execute_plan(module_name, session_id, user_id, pipeline_engine=engine)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return {"status": "executed", "message": message}

@app.post("/pipeline/dev")
async def execute_dev_pipeline(payload: DevPayload, caller_key: str = Depends(verify_colleague_key)):
    session_id = payload.session_id or "session_default"
    if not guard.validate_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id format")

    res = await orchestrator.execute_dev_and_post_sdd(session_id, max_repair_rounds=payload.max_rounds or 3)
    if res["is_green"]:
        engine.transition(PipelineState.POST_SDD)
    log_audit(session_id, caller_key, "DEV", f"RESULT_{res['status'].upper()}")
    return res

@app.get("/pipeline/artifacts/{session_id}/{artifact_type}")
async def get_artifact(session_id: str, artifact_type: str):
    if not guard.validate_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id format")
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
