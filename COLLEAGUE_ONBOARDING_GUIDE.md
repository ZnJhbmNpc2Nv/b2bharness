# 🚀 Руководство по подключению к B2B-Harness SDD API для коллег

Добро пожаловать в **B2B-Harness SDD Engine** — автономную среду спецификационно-ориентированной разработки (Specification-Driven Development) с A2A Swarm оркестрацией (Claude Opus 5.5, Sonnet 5, Gemini 3.7 Flash, Kimi K3) и активной защитой контекста (Context Integrity Guard).

---

## 🔑 Ваши персональные ключи доступа (API Keys)

Для авторизации запросов используйте один из выданных токенов в заголовке `X-API-Key` или `Authorization: Bearer <token>`:

| Пользователь / Роль | Выданный API-Ключ | Назначение |
| :--- | :--- | :--- |
| **Developer 1 (Коллега)** | `hb2b-colleague-dev1-7f8e4b2a9c1d` | Запуск стадий, генерация спецификаций и кода |
| **Developer 2 (Коллега)** | `hb2b-colleague-dev2-3a9d8f1e5c2b` | Запуск стадий, генерация спецификаций и кода |
| **Lead / Reviewer** | `hb2b-lead-auditor-9c2b4e8a1d7f` | Полный доступ + аудит и утверждение этапов |

*(На сервере ключи прописаны в переменной `HARNESS_API_KEYS`).*

---

## 🌐 Вариант 1: Использование через Веб-Интерфейс (Без кода)

1. Откройте в браузере адрес сервера:
   ```text
   http://<IP_ИЛИ_ХОСТ_СЕРВЕРА>:8000/
   ```
2. В поле **Session ID** укажите идентификатор вашей задачи (например, `session_ivan_01`).
3. Введите описание задачи в поле **Intent** и нажмите **🚀 Запустить SDD Конвейер**.
4. Все артефакты (`intent.md`, `spec.md`, `plan.md`, `dev_log.md`) будут отображаться в реальном времени в окне справа.
5. Интерактивная Swagger-документация: `http://<IP_СЕРВЕРА>:8000/docs`.

---

## 💻 Вариант 2: Использование через cURL / Терминал

### 1. Проверка доступности API
```bash
curl -X GET http://<IP_СЕРВЕРА>:8000/health
```

### 2. Шаг 1: Нормализация Intent (Канонические 4 секции)
```bash
curl -X POST http://<IP_СЕРВЕРА>:8000/pipeline/refine-intent \
  -H "X-API-Key: hb2b-colleague-dev1-7f8e4b2a9c1d" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Создать модуль парсинга JWT токенов с проверкой подписи RS256 и TTL",
    "session_id": "jwt_auth_session"
  }'
```

### 3. Шаг 2: Генерация Спецификации с требованиями безопасности (OWASP / CWE)
```bash
curl -X POST http://<IP_СЕРВЕРА>:8000/pipeline/spec \
  -H "X-API-Key: hb2b-colleague-dev1-7f8e4b2a9c1d" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "jwt_auth_session"
  }'
```

### 4. Шаг 3: Построение плана разработки (Plan Matrix)
```bash
curl -X POST http://<IP_СЕРВЕРА>:8000/pipeline/plan \
  -H "X-API-Key: hb2b-colleague-dev1-7f8e4b2a9c1d" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "jwt_auth_session"
  }'
```

### 5. Шаг 4: TDD Синтез, генерация кода и Self-Healing в песочнице
```bash
curl -X POST http://<IP_СЕРВЕРА>:8000/pipeline/dev \
  -H "X-API-Key: hb2b-colleague-dev1-7f8e4b2a9c1d" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "jwt_auth_session",
    "max_rounds": 3
  }'
```

### 6. Шаг 5: Просмотр сгенерированного артефакта
```bash
curl -X GET http://<IP_СЕРВЕРА>:8000/pipeline/artifacts/jwt_auth_session/spec
```

---

## 🐍 Вариант 3: Использование через Python Script

```python
import requests

BASE_URL = "http://127.0.0.1:8000"
API_KEY = "hb2b-colleague-dev1-7f8e4b2a9c1d"
SESSION_ID = "python_demo_01"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# 1. Отправляем Intent
intent_payload = {
    "text": "Реализовать Rate Limiter на алгоритме Token Bucket с поддержкой Redis/In-Memory",
    "session_id": SESSION_ID
}
resp = requests.post(f"{BASE_URL}/pipeline/refine-intent", json=intent_payload, headers=headers)
print("Intent response:", resp.json().get("refined_text"))

# 2. Генерируем Spec
resp = requests.post(f"{BASE_URL}/pipeline/spec", json={"session_id": SESSION_ID}, headers=headers)
print("\nSpec generated successfully!")

# 3. Запускаем TDD Dev Pipeline
resp = requests.post(f"{BASE_URL}/pipeline/dev", json={"session_id": SESSION_ID, "max_rounds": 3}, headers=headers)
dev_data = resp.json()
print(f"\nDev Status: {dev_data.get('status').upper()} (Rounds: {dev_data.get('rounds_executed')})")
```

---

## 🛡️ Правила безопасности и Context Guard (Важно!)

1. **Изоляция сессий:** `session_id` должен состоять только из букв, цифр, дефисов и подчеркиваний (от 1 до 64 символов). Попытки передачи путей `../` блокируются.
2. **Защита от Prompt Injection:** Запросы, содержащие директивы сброса системных инструкций (`ignore previous instructions` и т.д.), блокируются защитным экраном со статусом `400 Context Security Guard`.
3. **Контроль целостности:** Запрещено ручное редактирование `spec.md` и `plan.md`. Система проверяет SHA-256 хэши перед кодогенерацией и блокирует подмену контекста.
