# Архитектура Модулей и Расширений (BaseModule)

## 1. Принцип Модульности

Платформа построена на базе плагинной архитектуры: любой новый сервис или база данных подключается добавлением каталога в директорию `corporate_speckit/modules/`.

Встроенный менеджер `ModuleManager` автоматически:
1. Обнаруживает классы, наследующие `BaseModule`.
2. Создает необходимые таблицы в SQLite БД при старте.
3. Регистрирует HTTP REST API маршруты.
4. Добавляет новую вкладку в интерфейс Web Console.

---

## 2. Создание Собственного Модуля за 15 строк кода

```python
from modules.base import BaseModule

class CustomAnalyticsModule(BaseModule):
    @property
    def slug(self) -> str:
        return "analytics"

    @property
    def name(self) -> str:
        return "Корпоративная Аналитика"

    @property
    def icon(self) -> str:
        return "📈"

    def init_db(self, conn):
        conn.execute("CREATE TABLE IF NOT EXISTS analytics_events (id INTEGER PRIMARY KEY, event TEXT)")

    def get_routes(self):
        return [("GET", "/api/modules/analytics/stats", self._handle_stats)]

    def _handle_stats(self, handler):
        handler._send_json(200, {"status": "ok", "events_count": 0})
```
