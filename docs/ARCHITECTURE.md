# FinFlow — Architecture Document

## 1. System Overview

FinFlow is a fintech platform composed of two independent microservices that communicate asynchronously via Kafka and synchronously via HMAC-signed HTTP calls.

```
Browser / API Client
│
│  JWT Bearer Token
▼
┌─────────────────────────┐
│   Account Service :8000  │  Django REST Framework
│                          │
│  /api/users/             │  — User registration & JWT login
│  /api/accounts/          │  — Wallet CRUD
│  /api/transactions/      │  — Transaction create/list/get
│  /api/documents/         │  — KYC upload/download (MinIO)
│  /api/internal/          │  — HMAC-protected status update
└──────────┬───────────────┘
│
│  Publishes: transaction.created
│  Publishes: transaction.updated
▼
┌─────────────┐
│    Kafka     │
└──────┬──────┘
│  Consumes: transaction.created
▼
┌─────────────────────────┐
│  Processing Service :8001│  FastAPI + aiokafka
│                          │
│  Kafka consumer          │  — Receives transaction.created
│  Airflow stub            │  — Triggers payment DAG (stub)
│  HMAC signer             │  — Signs PATCH request
│  → PATCH /api/internal/  │  — Updates status: COMPLETED/FAILED
└─────────────────────────┘
```

## 2. Data Stores

| Store      | Purpose                                      |
|------------|----------------------------------------------|
| PostgreSQL | All structured data: users, accounts, transactions, documents metadata, audit logs |
| MinIO      | KYC document file bytes (DB stores metadata only) |
| Kafka      | Async event bus between the two services     |

## 3. Event Flow

### 3.1 Transaction Lifecycle

1. Client sends `POST /api/transactions/` with JWT.
2. Account Service saves transaction as **PENDING**.
3. Account Service publishes `transaction.created` event to Kafka.
4. Processing Service Kafka consumer receives the event.
5. Processing Service calls Airflow stub (simulates payment gateway).
6. Processing Service sends `PATCH /api/internal/transactions/<id>/` with HMAC signature.
7. Account Service verifies HMAC, validates nonce/timestamp, updates status to **COMPLETED** or **FAILED**.
8. Account Service publishes `transaction.updated` event.

### 3.2 Kafka Topics

| Topic                 | Producer         | Consumer            |
|-----------------------|------------------|---------------------|
| `transaction.created` | Account Service  | Processing Service  |
| `transaction.updated` | Account Service  | (monitoring/future) |

## 4. Authentication & Security

### 4.1 External Auth — JWT

- All public-facing endpoints require a Bearer JWT token.
- Tokens issued via `POST /api/token/` (SimpleJWT).
- Access token lifetime: 1 hour. Refresh token: 7 days.
- Expired/invalid tokens return HTTP 401.

### 4.2 Internal Auth — HMAC-SHA256

- Processing Service signs every internal request with HMAC-SHA256.
- Signature is computed over: `{method}\n{path}\n{timestamp}\n{nonce}\n{body_hash}`.
- Account Service verifies: signature match + timestamp within ±5 minutes + nonce not reused.
- Nonce replay protection uses an in-memory set (production: Redis).
- Missing headers, bad signatures, stale timestamps, reused nonces → HTTP 401.

## 5. Document Storage

- Upload: file bytes go to MinIO, metadata (filename, content_type, size, object_name) saved to PostgreSQL.
- Download: Account Service fetches bytes from MinIO and streams to client.
- Ownership enforced: users can only access their own documents.
- Allowed types: image/jpeg, image/png, image/gif, application/pdf.
- Max file size: 10 MB.

## 6. Engineering Practices

- **Soft delete**: no hard deletes anywhere; `is_deleted` + `deleted_at` on every model.
- **PII scrubbing**: passwords, tokens, emails redacted in all structured logs.
- **Kafka resilience**: publish failures are caught, logged, and never propagate to the HTTP response.
- **MinIO resilience**: storage failures return HTTP 502, request is not crashed.
- **Audit logging**: all state changes recorded in `audit_logs` table with PII scrubbed snapshots.
- **Test coverage**: >86% across all core modules; all external services mocked in tests.
