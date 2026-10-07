"""Knowledge Base & Architecture Decision Records (ADR) Module for Corporate Spec-Kit.
Provides corporate knowledge repository, ADR tracking, full-text search, and ADR-to-Requirement linkages.
"""
import sqlite3
import json
from typing import Dict, Any, List, Tuple, Callable
from ..base import BaseModule


class KnowledgeBaseModule(BaseModule):
    def __init__(self, db):
        self.db = db

    @property
    def slug(self) -> str:
        return "knowledge_base"

    @property
    def name(self) -> str:
        return "База знаний (Knowledge Vault)"

    @property
    def description(self) -> str:
        return "Корпоративная база знаний, архитектурные решения (ADR), стандарты кодирования и регламенты ИБ."

    @property
    def icon(self) -> str:
        return "📚"

    def init_db(self, conn: sqlite3.Connection):
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS kb_articles (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'ARCHITECTURE',
            content TEXT NOT NULL,
            tags TEXT NOT NULL,
            author TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'APPROVED',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS kb_req_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id TEXT NOT NULL,
            req_id TEXT NOT NULL,
            relation TEXT NOT NULL DEFAULT 'RATIONALE_FOR',
            FOREIGN KEY (article_id) REFERENCES kb_articles(id) ON DELETE CASCADE
        );
        """)

        # Seed default ADRs if table is empty
        cur = conn.execute("SELECT COUNT(*) FROM kb_articles")
        if cur.fetchone()[0] == 0:
            self._seed_default_articles(conn)

    def _seed_default_articles(self, conn: sqlite3.Connection):
        now = "2026-10-07T12:00:00Z"
        articles = [
            (
                "ADR-001",
                "ADR-001: Выбор Mutual TLS (mTLS) вместо статических API-токенов в контуре DMZ",
                "SECURITY",
                "### Контекст\nВ корпоративном закрытом контуре необходима строгая аутентификация микросервисов.\n\n"
                "### Решение\nИспользовать двусторонний mTLS с проверкой сертификата по внутреннему Root CA. "
                "Статические токены запрещены, так как подвержены утечкам при логировании.\n\n"
                "### Последствия\nТребуется наличие локального кэша списков отзыва сертификатов (CRL) для air-gap среды.",
                "mtls,security,dmz,ca,tls",
                "Elena Voronova (Chief Security Architect)",
                "APPROVED", now, now
            ),
            (
                "ADR-002",
                "ADR-002: Цепочечное хэширование SHA-256 для аудит-лога вместо распределенного реестра",
                "COMPLIANCE",
                "### Контекст\nТребуется подтверждать неизменяемость записей аудита по стандарту ISO-27001.\n\n"
                "### Решение\nКаждая запись аудита включает prev_hash предыдущей строки, вычисляя SHA-256 дайджест. "
                "Это даёт доказательную базу без накладных расходов на блокчейн-ноды.\n\n"
                "### Последствия\nЛюбая попытка ручной модификации SQLite выявляется за O(N) при проверке.",
                "audit,sha256,compliance,iso27001",
                "Mikhail Sidorov (Compliance Officer)",
                "APPROVED", now, now
            ),
            (
                "ADR-003",
                "ADR-003: In-Memory префиксный роутер с автоматическим Circuit Breaker",
                "ARCHITECTURE",
                "### Контекст\nШлюз должен маршрутизировать 10,000 rps в изоляции без внешнего Consul/etcd.\n\n"
                "### Решение\nРоутинг по in-memory префиксному дереву с пассивным счетчиком 5xx ошибок. "
                "При 3 последовательных сбоях брейкер переходит в OPEN и мгновенно отсекает запросы на 15 секунд.\n\n"
                "### Последствия\nZero-dependency в рантайме и защита от каскадных падений.",
                "router,circuit_breaker,resilience,performance",
                "Alexander Smirnov (Lead Backend Engineer)",
                "APPROVED", now, now
            )
        ]
        conn.executemany(
            "INSERT INTO kb_articles (id, title, category, content, tags, author, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            articles
        )

        # Seed linkages with project requirements
        links = [
            ("ADR-001", "REQ-SEC-001", "RATIONALE_FOR"),
            ("ADR-002", "REQ-LOG-002", "RATIONALE_FOR"),
            ("ADR-003", "REQ-RT-003", "RATIONALE_FOR"),
        ]
        conn.executemany(
            "INSERT INTO kb_req_links (article_id, req_id, relation) VALUES (?, ?, ?)",
            links
        )

    def get_routes(self) -> List[Tuple[str, str, Callable]]:
        return [
            ("GET", "/api/modules/knowledge_base/articles", self._handle_list_articles),
            ("POST", "/api/modules/knowledge_base/articles", self._handle_create_article),
            ("POST", "/api/modules/knowledge_base/link", self._handle_link_article),
        ]

    def _handle_list_articles(self, handler):
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT * FROM kb_articles ORDER BY id ASC").fetchall()
            articles = []
            for r in rows:
                item = dict(r)
                # fetch linked reqs
                links = conn.execute("SELECT req_id, relation FROM kb_req_links WHERE article_id = ?", (r["id"],)).fetchall()
                item["linked_reqs"] = [dict(l) for l in links]
                articles.append(item)
            handler._send_json(200, {"articles": articles})

    def _handle_create_article(self, handler):
        data = handler._read_json_body()
        aid = data.get("id") or f"ADR-{int(sqlite3.time.time())}"
        title = data.get("title", "")
        cat = data.get("category", "ARCHITECTURE")
        content = data.get("content", "")
        tags = data.get("tags", "")
        author = data.get("author", "Architect")
        now = "2026-10-07T12:00:00Z"
        with self.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO kb_articles (id, title, category, content, tags, author, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'APPROVED', ?, ?)",
                (aid, title, cat, content, tags, author, now, now)
            )
            linked_req = data.get("linked_req")
            if linked_req:
                conn.execute("INSERT INTO kb_req_links (article_id, req_id, relation) VALUES (?, ?, 'RATIONALE_FOR')", (aid, linked_req))
        handler._send_json(201, {"status": "created", "id": aid})

    def _handle_link_article(self, handler):
        data = handler._read_json_body()
        aid = data.get("article_id")
        rid = data.get("req_id")
        if not aid or not rid:
            handler._send_json(400, {"error": "article_id and req_id required"})
            return
        with self.db.get_connection() as conn:
            conn.execute("INSERT INTO kb_req_links (article_id, req_id, relation) VALUES (?, ?, 'RATIONALE_FOR')", (aid, rid))
        handler._send_json(200, {"status": "linked"})

    def get_lineage_contributions(self, conn: sqlite3.Connection, spec_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Inject ADR articles as provenance nodes connected to requirements."""
        links = conn.execute("SELECT article_id, req_id FROM kb_req_links").fetchall()
        nodes = []
        edges = []
        seen_articles = set()

        for l in links:
            aid = l["article_id"]
            rid = l["req_id"]
            node_id = f"node-kb-{aid}"

            if aid not in seen_articles:
                seen_articles.add(aid)
                art = conn.execute("SELECT title, category FROM kb_articles WHERE id = ?", (aid,)).fetchone()
                label = f"ADR: {aid}" if not art else f"{aid}: {art['title'][:30]}..."
                nodes.append({
                    "id": node_id,
                    "spec_id": spec_id,
                    "node_type": "KNOWLEDGE",
                    "entity_id": aid,
                    "label": label,
                    "meta_json": json.dumps({"category": art["category"] if art else "ADR"})
                })

            target_req_node = f"node-{rid}"
            edges.append({
                "id": hash(f"{node_id}->{target_req_node}"),
                "spec_id": spec_id,
                "from_node_id": node_id,
                "to_node_id": target_req_node,
                "relation": "JUSTIFIES"
            })

        return {"nodes": nodes, "edges": edges}
