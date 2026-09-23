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

## Troubleshooting & Patterns
- **SSL/TLS:** Using `tls internal` in Caddy for now due to Let's Encrypt rate limits.
- **API Issues:** Always verify `main.py` endpoints against frontend requirements. If UI hits "Loading...", check `/status` and `/health`.
- **Pipeline:** Status transitions are managed via `AgentOrchestrator` and `approval.json`. Manual overrides via `curl -X POST` are acceptable for MVP debugging.
