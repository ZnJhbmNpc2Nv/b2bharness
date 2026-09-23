# Infrastructure & Deployment Guide (B2B Harness)

## Connection
- **SSH Alias:** `secagent` (resolves to agentuser@production_ip)
- **Environment:** Ubuntu 24.04 LTS (Linux)

## Deployment Paths
- **Frontend Dist:** `/opt/apps/harness/frontend/dist`
- **Backend Code:** `/opt/b2bharness/`
- **Caddy Configs:** `/etc/caddy/conf.d/*.caddy`

## Infrastructure Context (Why Server-First?)
- **Environment Isolation:** Code execution (Caddy, FastAPI, Orchestrator) relies on Linux-specific system services (systemd, journalctl) and networking (DNS/TLS) that cannot be accurately replicated on the local Windows workstation.
- **Workflow:** Local workstation is for development/builds; the server is for integration and execution. Always verify state directly on the server.

## Deployment Updates (2026-09-19)
- **Backend Port**: Переведен с 8000 на 8001 для предотвращения конфликтов с другими сервисами (Marzban).
- **HTTPS**: Настроено автоматическое получение SSL-сертификатов через Let's Encrypt (Caddy).
- **Frontend Proxy**: Caddy настроен на проксирование `/api/*` запросов на локальный порт 8001 с использованием `handle_path` для корректной маршрутизации.
