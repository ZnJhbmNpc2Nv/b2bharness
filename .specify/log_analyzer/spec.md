---
name: log_analyzer_spec
description: Спецификация Log Analyzer MCP.
type: spec
version: 1.0
---
# Spec: Log Analyzer

## Acceptance Criteria
1. Функция `parse(file_path)` возвращает количество ошибок.
2. Исключение при отсутствии файла.
3. Формат вывода: JSON с полями count, errors, timestamp.

## Security
- Только чтение файлов в рабочей директории.
- Не использовать eval/exec.
