# Requirement Revision Ledger & Change History: Corporate Air-Gapped Secure Gateway

## History for REQ-LOG-002: Tamper-Evident SHA-256 Audit Trail

## History for REQ-PERF-004: Zero-Copy Direct Socket Proxying

### Version 1 - `CREATED` by Visual Craftsman (*Performance Lead*)
- **Timestamp**: `2026-10-07T13:10:17Z`
- **Justification**: Throughput optimization

## History for REQ-RT-003: Dynamic In-Memory Routing Table with Health Checks

## History for REQ-SEC-001: Strict Mutual TLS (mTLS) Authentication

### Version 1 - `CREATED` by Elena Voronova (*Security Architect*)
- **Timestamp**: `2026-10-07T13:06:22Z`
- **Justification**: Initial baseline draft from business intent

### Version 2 - `MODIFIED` by Dmitry Petrov (*Head of Corporate Audit*)
- **Timestamp**: `2026-10-07T13:06:22Z`
- **Justification**: Clarified rejection phase (must occur strictly at TLS handshake stage to prevent DoS).

```diff
--- v1
+++ v2
@@ -1 +1 @@
-The gateway must enforce client certificate validation against the Corporate CA.
+The gateway must enforce bidirectional mTLS with client certificate validation against the Corporate Root CA. Connections without valid certificates must be rejected at TLS handshake.
```

