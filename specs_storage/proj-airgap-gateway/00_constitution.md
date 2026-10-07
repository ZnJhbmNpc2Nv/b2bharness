# Project Constitution: Corporate Air-Gapped Secure Gateway

**Spec ID**: `proj-airgap-gateway` | **Status**: `APPROVED`

## Core Principles & Governance Rules

# Enterprise Security Constitution (v1.4)

1. **Zero External Egress**: No requests may exit internal network 10.0.0.0/8.
2. **Cryptographic Integrity**: All credentials and tokens must use hardware HSM or AES-256-GCM.
3. **Zero-Dependency Core**: Runtime components must execute without unverified external package repositories (pip/npm).
4. **Audit Traceability**: Every API invocation must produce an immutable audit log entry within 5ms.
