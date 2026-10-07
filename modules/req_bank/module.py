"""Requirements Bank (База эталонных требований) Module for Corporate Spec-Kit.
Provides an enterprise catalog of pre-approved reusable requirements,
standards compliance templates, and 1-click adoption into active specifications.
"""
import sqlite3
import json
from typing import Dict, Any, List, Tuple, Callable
from ..base import BaseModule


class RequirementsBankModule(BaseModule):
    def __init__(self, db):
        self.db = db

    @property
    def slug(self) -> str:
        return "req_bank"

    @property
    def name(self) -> str:
        return "База эталонных требований (Requirements Bank)"

    @property
    def description(self) -> str:
        return "Корпоративный каталог проверенных эталонных требований (ИБ, комплаенс, надежность, GDPR/152-ФЗ)."

    @property
    def icon(self) -> str:
        return "🏦"

    def init_db(self, conn: sqlite3.Connection):
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS req_bank_templates (
            id TEXT PRIMARY KEY,
            domain TEXT NOT NULL DEFAULT 'SECURITY',
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            rationale TEXT NOT NULL,
            acceptance_criteria TEXT NOT NULL,
            tags TEXT NOT NULL,
            compliance_standard TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        );
        """)

        cur = conn.execute("SELECT COUNT(*) FROM req_bank_templates")
        if cur.fetchone()[0] == 0:
            self._seed_default_templates(conn)

    def _seed_default_templates(self, conn: sqlite3.Connection):
        templates = [
            (
                "BANK-SEC-01",
                "SECURITY",
                "Двусторонняя mTLS аутентификация микросервисов",
                "Все входящие межсервисные соединения должны валидироваться через клиентские сертификаты X.509, подписанные внутренним Корпоративным CA. Соединения без валидного сертификата прерываются на этапе TLS handshake.",
                "Исключает возможность несанкционированного доступа и подделки трафика внутри контура DMZ.",
                json.dumps([
                    "Клиент без сертификата отвергается на этапе TLS handshake с кодом SSL_CERTIFICATE_REQUIRED.",
                    "При валидном сертификате CN и SAN субъекта извлекаются в заголовки контекста запроса."
                ]),
                "mtls,security,tls,zero-trust",
                "ISO-27001 / PCI-DSS v4.0",
                1
            ),
            (
                "BANK-COMP-02",
                "COMPLIANCE",
                "Неизменяемый криптографический аудит-лог (Chained SHA-256)",
                "Каждое критическое действие или вызов API должен фиксироваться с сохранением SHA-256 дайджеста, включающего хэш предыдущей записи. Запись должна синхронно сбрасываться на локальный накопитель.",
                "Обеспечивает юридически значимую доказательную базу и невозможность удаления следов несанкционированных действий.",
                json.dumps([
                    "Каждая запись содержит prev_hash, образуя неразрывную цепочку от генезис-блока.",
                    "Команда верификации подтверждает 100% целостность цепочки."
                ]),
                "audit,iso27001,tamper-evident,sha256",
                "ISO-27001 A.12.4.1 / SOC2 Type II",
                1
            ),
            (
                "BANK-RESIL-03",
                "RELIABILITY",
                "Отказоустойчивый Circuit Breaker с неблокирующими таймаутами",
                "Вызовы нижележащих сервисов должны быть защищены паттерном Circuit Breaker. При превышении 3 последовательных ошибок 502/504 или таймаутов, вызовы мгновенно отсекаются (fail-fast) без ожидания сокета.",
                "Предотвращает каскадное исчерпание пула потоков/соединений при сбое зависимого бэкенда.",
                json.dumps([
                    "Таймаут ожидания ответа не превышает 15.0 секунд.",
                    "Состояние OPEN активируется после 3 последовательных неудач с периодом остывания 30 секунд."
                ]),
                "resilience,circuit-breaker,timeout,ha",
                "Site Reliability Engineering (SRE)",
                1
            ),
            (
                "BANK-PII-04",
                "PRIVACY",
                "Маскирование и токенизация персональных данных (ПДн)",
                "Все атрибуты персональных данных (ФИО, телефоны, email, паспорта) должны маскироваться при выводе в логи и журналы трассировки. Значения заменяются на необратимый токен или маску вида `+7 (***) ***-12-34`.",
                "Требование Федерального закона № 152-ФЗ 'О персональных данных' и европейского регламента GDPR.",
                json.dumps([
                    "В логах уровня INFO/DEBUG отсутствуют открытые номера карт и паспортные данные.",
                    "Утечка ПДн в audit_ledger пресекается фильтром санитизации."
                ]),
                "pii,privacy,gdpr,152-fz,masking",
                "152-ФЗ / GDPR Article 32",
                1
            )
        ]
        conn.executemany(
            "INSERT INTO req_bank_templates (id, domain, title, description, rationale, acceptance_criteria, tags, compliance_standard, version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            templates
        )

    def get_routes(self) -> List[Tuple[str, str, Callable]]:
        return [
            ("GET", "/api/modules/req_bank/templates", self._handle_list_templates),
            ("POST", "/api/modules/req_bank/adopt", self._handle_adopt_template),
        ]

    def _handle_list_templates(self, handler):
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM req_bank_templates ORDER BY id ASC").fetchall()
            templates = []
            for r in rows:
                item = dict(r)
                try:
                    item["acceptance_criteria"] = json.loads(item["acceptance_criteria"])
                except Exception:
                    item["acceptance_criteria"] = []
                templates.append(item)
            handler._send_json(200, {"templates": templates})

    def _handle_adopt_template(self, handler):
        data = handler._read_json_body()
        tmpl_id = data.get("template_id")
        spec_id = data.get("spec_id", "proj-airgap-gateway")
        author = data.get("author_name", "Corporate Architect")
        role = data.get("author_role", "Architect")

        if not tmpl_id:
            handler._send_json(400, {"error": "template_id required"})
            return

        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM req_bank_templates WHERE id = ?", (tmpl_id,)).fetchone()
            if not row:
                handler._send_json(404, {"error": f"Template {tmpl_id} not found"})
                return

            tmpl = dict(row)
            try:
                criteria = json.loads(tmpl["acceptance_criteria"])
            except Exception:
                criteria = []

            # Generate target REQ ID
            cur = conn.execute("SELECT COUNT(*) FROM requirements WHERE spec_id = ?", (spec_id,))
            num = cur.fetchone()[0] + 1
            domain_code = tmpl["domain"][:3].upper()
            target_req_id = f"REQ-{domain_code}-{num:03d}"

        # Create requirement in project via db API
        created = self.db.create_requirement(
            spec_id=spec_id,
            req_id=target_req_id,
            category=tmpl["domain"],
            title=tmpl["title"],
            description=tmpl["description"],
            rationale=f"[Adopted from Requirements Bank: {tmpl_id} ({tmpl['compliance_standard']})] {tmpl['rationale']}",
            acceptance_criteria=criteria,
            author_name=author,
            author_role=role,
            justification=f"Adopted corporate enterprise standard {tmpl_id}"
        )
        handler._send_json(201, {"status": "adopted", "requirement": created, "source_template": tmpl_id})
