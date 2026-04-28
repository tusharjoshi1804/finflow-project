# FinFlow — API Contracts

## Base URL
- Account Service: `http://localhost:8000`
- Processing Service: `http://localhost:8001`

## Authentication

All endpoints except registration and token endpoints require:

```
Authorization: Bearer <access_token>
```

## Account Service Endpoints

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /api/token/ | None | Login — returns access + refresh JWT |
| POST | /api/token/refresh/ | None | Refresh access token |

**POST /api/token/** Request:
```json
{ "email": "user@example.com", "password": "StrongPass1!" }
```
Response 200:
```json
{ "access": "<jwt>", "refresh": "<jwt>" }
```

---

### Users

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /api/users/ | None | Register new user |
| GET | /api/users/{id}/ | JWT | Get own profile |
| PATCH | /api/users/{id}/ | JWT | Update own profile |
| DELETE | /api/users/{id}/ | JWT | Soft-delete own account |

**POST /api/users/** Request:
```json
{
  "email": "user@example.com",
  "password": "StrongPass1!",
  "first_name": "Jane",
  "last_name": "Doe",
  "phone": "+919876543210"
}
```
Response 201:
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "first_name": "Jane",
  "last_name": "Doe",
  "phone": "+919876543210"
}
```

---

### Accounts

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /api/accounts/ | JWT | List own accounts (paginated) |
| POST | /api/accounts/ | JWT | Create account |
| GET | /api/accounts/{id}/ | JWT | Get account |
| PATCH | /api/accounts/{id}/ | JWT | Update account |
| DELETE | /api/accounts/{id}/ | JWT | Soft-delete account |

**POST /api/accounts/** Request:
```json
{ "name": "Main Wallet", "currency": "USD" }
```
Currencies: `USD`, `INR`, `EUR`, `GBP`

Response 201:
```json
{ "id": "uuid", "name": "Main Wallet", "currency": "USD" }
```

---

### Transactions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /api/transactions/ | JWT | List own transactions (paginated) |
| POST | /api/transactions/ | JWT | Create transaction → Kafka event |
| GET | /api/transactions/{id}/ | JWT | Get transaction |

**POST /api/transactions/** Request:
```json
{
  "account": "account-uuid",
  "transaction_type": "DEBIT",
  "amount": "150.00",
  "reference": "REF-001"
}
```
Transaction types: `DEBIT`, `CREDIT`

Response 201:
```json
{
  "id": "uuid",
  "account_id": "uuid",
  "transaction_type": "DEBIT",
  "amount": "150.00",
  "status": "PENDING",
  "reference": "REF-001"
}
```

---

### Documents

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /api/documents/ | JWT | List own documents (paginated) |
| POST | /api/documents/upload/ | JWT | Upload KYC document (multipart) |
| GET | /api/documents/{id}/download/ | JWT | Download document |

**POST /api/documents/upload/** — multipart/form-data
- Field: `file`
- Allowed types: `image/jpeg`, `image/png`, `image/gif`, `application/pdf`
- Max size: 10 MB

Response 201:
```json
{
  "id": "uuid",
  "file_name": "kyc.pdf",
  "content_type": "application/pdf",
  "file_size": 204800,
  "owner_email": "user@example.com"
}
```

---

### Internal Endpoint (Processing Service → Account Service)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| PATCH | /api/internal/transactions/{id}/ | HMAC | Update transaction status |

**Required headers:**X-Timestamp: 1714300000
X-Nonce: <uuid4>
X-Signature: <hmac-sha256-hex>**PATCH /api/internal/transactions/{id}/** Request:
```json
{ "status": "COMPLETED" }
```
Valid statuses: `COMPLETED`, `FAILED`

Response 200:
```json
{ "id": "uuid", "status": "COMPLETED", ... }
```

Error responses:
- 400: already in terminal state, or invalid status
- 401: missing/bad HMAC headers
- 404: transaction not found

---

## Processing Service Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | / | None | Root status endpoint |
| GET | /health | None | Health check |

Response 200:
```json
{ "status": "ok", "service": "processing-service" }
```

---

## Kafka Events

The services communicate asynchronously via Kafka topics. All events are JSON-encoded.

### Topic: `transaction.created`

**Producer:** Account Service  
**Consumer:** Processing Service

**Event payload:**
```json
{
  "transaction_id": "uuid",
  "account_id": "uuid",
  "transaction_type": "DEBIT",
  "amount": "150.00",
  "status": "PENDING"
}
```

**Flow:**
1. Account Service publishes after `POST /api/transactions/` creates a transaction.
2. Processing Service consumes the event.
3. Processing Service triggers Airflow payment DAG (stub).
4. Processing Service calls `PATCH /api/internal/transactions/{id}/` with HMAC auth.

---

### Topic: `transaction.updated`

**Producer:** Account Service  
**Consumer:** (monitoring/future features)

**Event payload:**
```json
{
  "transaction_id": "uuid",
  "status": "COMPLETED"
}
```

**Published:** After Processing Service updates transaction status via HMAC callback.
