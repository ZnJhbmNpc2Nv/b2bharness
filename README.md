# B2B-Harness (Specification-Driven Development Framework)

Каркас и оркестратор для **SDD (Specification-Driven Development)** с поддержкой пайплайна разработки, системы контроля безопасности (SAST) и концепции **Human-in-the-Loop** (экспертное подтверждение).

---

## 🚀 Архитектура и Структура Проекта

- `harness.yaml` — Конфигурация пайплайна и стандартов безопасности (`OWASP_ASVS_L2`, `CWE_TOP_25`).
- `src/api/main.py` — FastAPI-сервер для управления пайплайном, аппрувами и интеграцией с LLM.
- `src/engine/` — Оркестратор и статус-машина состояний пайплайна (`pre_sdd` ➔ `intent` ➔ `spec` ➔ `plan` ➔ `dev` ➔ `post_sdd` ➔ `ab_test`).
- `src/security/` — SAST-сканер уязвимостей в коде.
- `src/core/` — Логирование и аудит в SQLite базу данных (`data/harness.db`).
- `projects/` — Пространства для реализации конкретных задач с артефактами трассировки (`intent.md`, `spec.md`, `plan.md`).

---

## ⚙️ Системные требования и Зависимости

- **Python**: 3.10+ (рекомендуется 3.11 / 3.14)
- **Менеджер пакетов**: `pip` / `venv`

Основные зависимости:
- `fastapi` & `uvicorn` — для REST API бэкенда
- `pydantic` & `pydantic-settings` — для конфигурации и валидации
- `httpx` — для запросов к LLM API
- `pytest` — для модульного и интеграционного тестирования

---

## 🛠 Руководство по установке и развертыванию (Для LLM-агентов и разработчиков)

### 1. Клонирование и настройка окружения
```bash
git clone git@github.com:ZnJhbmNpc2Nv/b2bharness.git
cd b2bharness

# Создание и активация виртуального окружения
python -m venv .venv
# Для Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Для Linux/macOS:
# source .venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt  # (или установка зависимостей через pyproject.toml / вручную)
```

### 2. Конфигурация LLM и API-ключей (Секреты)
В репозитории **нет** реальных API-ключей. Для подключения к LLM-шлюзу настройте их одним из способов:

1. **Через файл `data/keys.json`**:
   Отредактируйте файл `data/keys.json` в корне проекта:
   ```json
   {
     "key": "YOUR_ACTUAL_API_KEY",
     "active": true,
     "added_at": 1790155297.0
   }
   ```

2. **Настройка базового URL LLM**:
   Базовый URL LLM-клиента задается в файле `src/api/llm_client.py`:
   ```python
   self.base_url = "https://llm.franciscodanconia.ru/v1" # Измените при необходимости
   ```

### 3. Запуск тестов (Верификация)
Для проверки работоспособности системы выполните:
```python
python -m pytest
```
*Все тесты должны завершиться успешно (`7 passed`).*

### 4. Запуск локального API-сервера
```bash
python -m uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```
После запуска:
- **Swagger UI документация**: `http://127.0.0.1:8000/docs`
- **Проверка статуса**: `http://127.0.0.1:8000/health`
