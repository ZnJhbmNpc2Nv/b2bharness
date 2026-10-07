# Архитектурные инварианты и контракты данных (System Invariants & Data Contracts)

> **Назначение документа**: Эталонная спецификация структур данных, схем таблиц SQLite и контрактов REST API. Передавайте этот документ агентам в качестве контекста, чтобы они знали точные типы полей и не изобретали несовместимые схемы.

---

## 1. Схема базы данных SQLite (WAL Режим)

Все базы данных используют `PRAGMA journal_mode = WAL` и `PRAGMA foreign_keys = ON`.

### Таблицы конвейера B2B-Harness (`pipeline_runs.db`)

#### 1. `pipeline_runs` (Основная таблица прогона конвейера)
```sql
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id TEXT PRIMARY KEY,                 -- Уникальный идентификатор: 'pipe-xxxxxxxxxxxx'
    project_name TEXT NOT NULL,          -- Название проекта/модуля
    input_path TEXT NOT NULL,            -- Директория с PoC кодом (относительно корня или абсолютная)
    initial_idea TEXT,                   -- Исходный текстовый промпт/намерение
    current_stage TEXT NOT NULL,         -- Enum: 'PRE_SDD' | 'SDD_INTENT' | 'SDD_SPEC' | 'SDD_PLAN' | 'SDD_DEV' | 'POST_SDD' | 'AB_TEST'
    current_iteration INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,                -- Enum: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'AWAITING_HUMAN' | 'SKIPPED'
    storage_dir TEXT NOT NULL,           -- Папка хранения артефактов: 'specs_storage/<id>'
    loop_count INTEGER NOT NULL DEFAULT 0, -- Счетчик циклов самоисцеления POST-SDD (макс. 3)
    created_at TEXT NOT NULL,            -- ISO 8601 UTC timestamp
    updated_at TEXT NOT NULL             -- ISO 8601 UTC timestamp
);
```

#### 2. `stage_snapshots` (Контрольные точки стадий)
```sql
CREATE TABLE IF NOT EXISTS stage_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id TEXT NOT NULL,           -- FK -> pipeline_runs(id) ON DELETE CASCADE
    stage TEXT NOT NULL,
    iteration INTEGER NOT NULL,
    status TEXT NOT NULL,                -- 'COMPLETED' | 'FAILED' | 'AWAITING_HUMAN'
    input_artifacts TEXT NOT NULL,       -- JSON строка: входные файлы и метаданные
    output_artifacts TEXT NOT NULL,      -- JSON строка: выходные артефакты шага
    error_message TEXT,                  -- Текст ошибки (если статус FAILED)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

#### 3. `a2a_messages` (Реестр межагентных сообщений)
```sql
CREATE TABLE IF NOT EXISTS a2a_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,              -- Сквозной трейс: 'trace-pipe-xxxx-iter'
    pipeline_id TEXT NOT NULL,
    step_id TEXT NOT NULL,               -- Этап, на котором отправлен конверт
    iteration INTEGER NOT NULL,
    sender_role TEXT NOT NULL,           -- Роль: 'reverse_engineer' | 'intent_architect' | 'spec_engineer' | 'code_developer' | 'security_auditor'
    sender_metadata TEXT,                -- JSON: {model, temperature}
    recipient_role TEXT NOT NULL,        -- Роль получателя: 'plan_architect' | 'human_reviewer'
    payload TEXT NOT NULL,               -- JSON: {artifact_type, artifact_hash, content, referenced_artifacts}
    status TEXT NOT NULL,                -- 'IN_PROGRESS' | 'AWAITING_CRITIC_REVIEW' | 'APPROVED'
    timestamp TEXT NOT NULL
);
```

#### 4. `hitl_gates` (Human-in-the-Loop ворота)
```sql
CREATE TABLE IF NOT EXISTS hitl_gates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    iteration INTEGER NOT NULL,
    gate_type TEXT NOT NULL,             -- 'INTENT_APPROVAL' | 'LOOP_ESCALATION'
    status TEXT NOT NULL,                -- 'PENDING' | 'RESOLVED' | 'REJECTED'
    prompt TEXT NOT NULL,                -- Формулировка задачи человеку
    options TEXT,                        -- JSON массив: ["APPROVE_AS_IS", "ADD_ACCEPTANCE_CRITERIA", "REJECT"]
    human_response TEXT,                 -- JSON с ответом человека: {decision, expert_name, rationale, clarifications}
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
```

---

## 2. Спецификация REST API Конвейера (`/api/harness/*`)

Все эндпоинты возвращают `application/json; charset=utf-8`.

| Метод | URL | Назначение | Payload (Request) | Ответ (Response) |
|---|---|---|---|---|
| `GET` | `/api/harness/pipelines` | Список всех запусков | — | `{"pipelines": [{pipeline_id, project_name, current_stage, status, ...}]}` |
| `POST` | `/api/harness/pipeline/start` | Создание и запуск нового конвейера | `{"project_name": "...", "input_path": "workspace", "initial_idea": "...", "require_hitl_intent": true}` | `201 Created`: `{"status": "ok", "pipeline_id": "...", "state": {...}}` |
| `GET` | `/api/harness/pipeline/{id}/state` | Полное состояние конвейера | — | `200 OK`: `{pipeline_id, current_stage, status, loop_count, snapshots: [...], pending_gate: {...}}` |
| `POST` | `/api/harness/pipeline/{id}/step` | Выполнение ровно 1 шага | `{}` | `200 OK`: `{"result": {stage, status, ...}, "state": {...}}` |
| `POST` | `/api/harness/pipeline/{id}/run` | Автопрогон до паузы/финиша | `{}` | `200 OK`: `{"status": "paused_or_completed", "state": {...}}` |
| `GET` | `/api/harness/pipeline/{id}/messages` | Реестр A2A конвертов | — | `200 OK`: `{"messages": [{trace_id, step_id, sender_role, recipient_role, status, ...}]}` |
| `GET` | `/api/harness/pipeline/{id}/artifacts` | Список файлов на диске | — | `200 OK`: `{"artifacts": ["discovery.md", "intent.md", "spec.md", ...]}` |
| `GET` | `/api/harness/pipeline/{id}/artifact?name=...` | Получение содержимого файла | `?name=discovery.md` | `200 OK`: `{"name": "discovery.md", "content": "# Discovery Dossier..."}` |
| `POST` | `/api/harness/pipeline/{id}/resolve_gate` | Резолюция HITL-гейта | `{"decision": "APPROVE_AS_IS", "expert_name": "Lead", "rationale": "...", "clarifications": "..."}` | `200 OK`: `{"result": {...}, "state": {...}}` |

---

## 3. Модель A2A Конверта (`A2AEnvelope`)

Каждое сообщение между агентами валидируется по схеме:
```json
{
  "trace_id": "trace-pipe-95a570cd7490-1",
  "step_id": "SDD_SPEC",
  "iteration": 1,
  "sender": {
    "agent_role": "spec_engineer",
    "model": "euromodels/claude-opus-4.8",
    "temperature": 0.1
  },
  "recipient": {
    "agent_role": "plan_architect"
  },
  "payload": {
    "artifact_type": "SPEC",
    "artifact_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "content": "# Immutable Formal Specification...",
    "referenced_artifacts": {
      "intent": "intent.md"
    },
    "metadata": {
      "req_ids": ["REQ-CORE-001", "REQ-VAL-002", "REQ-PERF-003", "REQ-SEC-004", "REQ-SEC-005"],
      "asvs_level": 2
    }
  },
  "status": "APPROVED",
  "timestamp": "2026-10-07T19:40:00Z"
}
```

---

## 4. Контракт плагинов расширения (`modules/base.py`)

Если агенты создают новые модули в `modules/<module_name>/module.py`:
1. Модуль обязан наследоваться от `BaseModule`.
2. Обязан реализовать методы:
   * `manifest() -> Dict[str, Any]` (name, title, version, description).
   * `init_db(conn: sqlite3.Connection)` (создание таблиц с `IF NOT EXISTS`).
   * `handle_request(method: str, path: str, handler) -> bool` (возвращает `True`, если запрос обработан, иначе `False`).
3. Запрещено блокировать системный поток сервера бесконечными циклами.
