# Спецификация Упаковки Переиспользуемого Модуля

## 1. Манифест Модуля (`module_manifest.json`)

Каждый нормализованный модуль на выходе конвейера снабжается стандартным манифестом, позволяющим Core-агентам и оркестраторам подключать его без ручной адаптации.

### Пример Манифеста

```json
{
  "module_name": "corp-excel-parser",
  "version": "1.0.0",
  "domain": "finance",
  "runtime": "python:3.12-slim",
  "entrypoint": "run_module.py",
  "protocols": {
    "mcp": {
      "transport": "stdio",
      "tools": [
        {
          "name": "parse_report",
          "description": "Парсит финансовый отчет и возвращает валидированный JSON",
          "input_schema": {
            "type": "object",
            "properties": {
              "file_path": {"type": "string"}
            },
            "required": ["file_path"]
          }
        }
      ]
    },
    "openapi": {
      "path": "/openapi.json",
      "port": 8080
    }
  },
  "security": {
    "asvs_level": "Level-2",
    "sast_report_hash": "sha256:7b1e4a...",
    "sbom_path": "sbom.json"
  },
  "provenance": {
    "intent_hash": "sha256:91bc83...",
    "spec_hash": "sha256:4a3f28...",
    "plan_hash": "sha256:b22345..."
  }
}
```

---

## 2. Состав Дистрибутива Модуля

```
dist/
├── module_manifest.json    # Манифест метаданных и схем инструментов
├── sbom.json               # Software Bill of Materials (CycloneDX)
├── seal.json               # SHA-256 криптографическая печать целостности
├── Dockerfile              # Защищенный контейнер (non-root appuser:10001)
├── run_module.py           # Автономный раннер (--mcp, --http, --health)
├── test_harness.py         # Локальный валидатор работоспособности
├── README.md               # Документация модуля
└── module/                 # Исходный код пакета
    ├── __init__.py
    └── core.py
```
