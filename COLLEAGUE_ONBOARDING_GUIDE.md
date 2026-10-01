# 🚀 Руководство по подключению к B2B-Harness SDD API для коллег

Добро пожаловать в **B2B-Harness SDD Engine** — автономную среду спецификационно-ориентированной разработки (Specification-Driven Development) с A2A Swarm оркестрацией (Claude Opus 5.5, Sonnet 5, Gemini 3.7 Flash, Kimi K3) и активной защитой контекста (Context Integrity Guard).

---

## 🔑 Авторизация (API Key)

Для выполнения запросов передавайте выданный администратором токен в заголовке `X-API-Key` или `Authorization: Bearer <token>`:

```http
X-API-Key: <ВАШ_ВЫДАННЫЙ_КЛЮЧ>
```

*(Ключи настраиваются администратором сервера через переменные окружения `HARNESS_API_KEYS` или в защищенном файле `.env`)*.

---

## 🌐 Вариант 1: Использование через Веб-Интерфейс (Без кода)

1. Откройте в браузере адрес сервера:
   ```text
   http://<IP_СЕРВЕРА>:8000/
   ```
2. Вставьте выданный вам ключ в поле **API-Ключ**.
3. В поле **Имя сессии** укажите идентификатор вашей задачи (например: `ivan_lru_cache` или `alex_jwt`).
4. Выберите быстрый шаблон или введите описание задачи и нажмите **🚀 Запустить SDD Конвейер**.
5. Все артефакты (`intent.md`, `spec.md`, `plan.md`, `dev_log.md`) будут сгенерированы в реальном времени в окне справа.
6. Интерактивная Swagger-документация: `http://<IP_СЕРВЕРА>:8000/docs`.

---

## 💻 Вариант 2: Использование через cURL / Терминал

### 1. Проверка доступности API
```bash
curl -X GET http://<IP_СЕРВЕРА>:8000/health
```

### 2. Шаг 1: Нормализация Intent (Канонические 4 секции)
```bash
curl -X POST http://<IP_СЕРВЕРА>:8000/pipeline/refine-intent \
  -H "X-API-Key: <ВАШ_КЛЮЧ>" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Создать модуль парсинга JWT токенов с проверкой подписи RS256 и TTL",
    "session_id": "jwt_auth_session"
  }'
```

### 3. Шаг 2: Генерация Спецификации с требованиями безопасности (OWASP / CWE)
```bash
curl -X POST http://<IP_СЕРВЕРА>:8000/pipeline/spec \
  -H "X-API-Key: <ВАШ_КЛЮЧ>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "jwt_auth_session"
  }'
```

### 4. Шаг 3: Построение плана разработки (Plan Matrix)
```bash
curl -X POST http://<IP_СЕРВЕРА>:8000/pipeline/plan \
  -H "X-API-Key: <ВАШ_КЛЮЧ>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "jwt_auth_session"
  }'
```

### 5. Шаг 4: TDD Синтез, генерация кода и Self-Healing в песочнице
```bash
curl -X POST http://<IP_СЕРВЕРА>:8000/pipeline/dev \
  -H "X-API-Key: <ВАШ_КЛЮЧ>" \
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

BASE_URL = "http://<IP_СЕРВЕРА>:8000"
API_KEY = "<ВАШ_КЛЮЧ>"
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

## 🛡️ Правила безопасности и Context Guard

1. **Изоляция сессий:** `session_id` должен состоять только из букв, цифр, дефисов и подчеркиваний (от 1 до 64 символов). Попытки передачи путей `../` блокируются.
2. **Защита от Prompt Injection:** Запросы, содержащие директивы сброса системных инструкций (`ignore previous instructions` и т.д.), блокируются защитным экраном со статусом `400 Context Security Guard`.
3. **Контроль целостности:** Запрещено ручное редактирование `spec.md` и `plan.md`. Система проверяет SHA-256 хэши перед кодогенерацией и блокирует подмену контекста.
