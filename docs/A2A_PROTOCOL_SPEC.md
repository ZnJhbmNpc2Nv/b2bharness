# Спецификация Протокола Агентного Взаимодействия (A2A Protocol)

## 1. Концепция Конверта Сообщений (A2A Envelope)

В мультиагентном контуре обмен неструктурированным текстом приводит к рассинхронизации контекста и потере данных. Протокол **A2A (Agent-to-Agent)** стандартизирует все коммуникации через типизированный конверт `A2AEnvelope`.

### JSON Schema Структура Конверта

```json
{
  "trace_id": "b2b-trace-9f81a7b2-c0e4-4d89-b7b5",
  "step_id": "SDD_SPEC",
  "iteration": 1,
  "sender": {
    "agent_role": "SpecificationArchitect",
    "model": "gigacode",
    "temperature": 0.2
  },
  "recipient": {
    "agent_role": "SecurityCritic"
  },
  "payload": {
    "artifact_type": "spec.md",
    "artifact_hash": "sha256:4a3f281e05d9...",
    "content": "# Specification...",
    "referenced_artifacts": [
      {"type": "intent.md", "hash": "sha256:91bc830f..."}
    ],
    "metadata": {
      "asvs_level": "Level-2",
      "total_reqs": 5
    }
  },
  "status": "AWAITING_CRITIC_REVIEW",
  "timestamp": "2026-10-07T14:00:00Z"
}
```

---

## 2. Поля и Контракт Данных

| Поле | Тип | Описание |
|---|---|---|
| `trace_id` | `str` (UUID) | Сквозной идентификатор запуска пайплайна, связывающий все сообщения. |
| `step_id` | `str` (Enum) | Идентификатор этапа (`PRE_SDD`, `SDD_INTENT`, `SDD_SPEC`, `SDD_PLAN`, `SDD_DEV`, `POST_SDD`, `AB_TEST`). |
| `iteration` | `int` | Номер итерации исправления (1, 2, 3). |
| `sender` | `dict` | Метаданные агента-отправителя: `agent_role`, `model`, `temperature`. |
| `recipient` | `dict` | Метаданные агента-получателя: `agent_role`. |
| `payload` | `dict` | Полезная нагрузка: тип артефакта, SHA-256 хэш, тело, связанные артефакты. |
| `status` | `str` | Текущий статус обработки сообщения (`IN_PROGRESS`, `APPROVED`, `REJECTED`, `AWAITING_HUMAN`). |
| `timestamp` | `str` (ISO-8601) | Время формирования конверта по UTC. |

---

## 3. Модель Ролей и Консенсуса

Для предотвращения галлюцинаций и зацикливания система использует двухфазный консенсус:
1. **Actor (Генератор)**: Создает проект артефакта (`intent.md`, `spec.md`, `plan.md`, код).
2. **Critic (Аудитор)**: Проверяет проект артефакта на соответствие правилам безопасности, полноту и отсутствие пропущенных требований.
3. **Arbiter (Оркестратор)**: Фиксирует статус артефакта, следит за лимитом циклов (максимум 3 итерации в `POST_SDD`) и переводит систему в статус ожидания человека (`AWAITING_HUMAN`) при недостижении консенсуса.
