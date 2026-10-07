# Engineering Tasks: Corporate Air-Gapped Secure Gateway

| Task ID | Linked Req | Title | Assignee | Status | Test Case | Target Code |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `TASK-001` | `REQ-SEC-001` | Implement SSLContext with ssl.CERT_REQUIRED and local CA bundle verification | Dev Team | `DONE` | `TEST-MTLS-01` | `sec_gateway/tls.py:wrap_socket` |
| `TASK-002` | `REQ-LOG-002` | Implement chained SHA-256 rolling digest log writer | Dev Team | `DONE` | `TEST-LOG-02` | `sec_gateway/audit.py:write_audit_entry` |
| `TASK-003` | `REQ-RT-003` | Implement non-blocking in-memory prefix trie router with circuit breaker | Dev Team | `IN_PROGRESS` | `TEST-RT-03` | `sec_gateway/router.py:resolve_route` |
| `TASK-004` | `REQ-PERF-004` | Benchmark splice/sendfile socket pump | Dev Team | `TODO` | `TEST-PERF-04` | `sec_gateway/pump.py` |
