# FinFlow — Fintech Microservices Platform

A production-style fintech platform built as a 5-day intern challenge.
Two microservices communicate via Kafka with JWT external auth and HMAC internal auth.

---

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Environment Variables](#environment-variables)
- [Running the Services](#running-the-services)
- [Running Tests](#running-tests)
- [API Documentation](#api-documentation)
- [Key Endpoints](#key-endpoints)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## Overview

**Account Service** (Django REST Framework — port 8000)
- User registration and JWT login
- Account (wallet) CRUD
- Transaction create, list, get — publishes Kafka events
- KYC document upload/download via MinIO
- HMAC-protected internal endpoint for status updates
- Audit logging with PII scrubbing

**Processing Service** (FastAPI — port 8001)
- Consumes `transaction.created` Kafka events
- Triggers Airflow DAG stub for payment processing
- Calls Account Service internal endpoint with HMAC-signed request

---

## ArchitectureBrowser → JWT → Account Service :8000
POST /api/transactions/ → PENDING → Kafka: transaction.created
← PATCH /api/internal/transactions/{id}/ (HMAC) ← Processing Service
Kafka → Processing Service :8001
→ Airflow stub → HMAC PATCH → Account Service → COMPLETED/FAILEDSee `docs/ARCHITECTURE.md` for full details.

---

## Prerequisites

- Docker + Docker Compose
- Python 3.12+
- Git

For Codespaces (no Docker Desktop needed):
- GitHub Codespaces handles Docker automatically

---

## Setup

```bash
# 1. Clone
git clone https://github.com/tusharjoshi1804/finflow-project.git
cd finflow-project

# 2. Copy env file
cp .env.example .env

# 3. Start all services
docker-compose up --build

# 4. Run migrations (first time)
docker exec finflow-account-service python manage.py migrate
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| DJANGO_SECRET_KEY | Django secret key | dev-secret-change-me |
| DEBUG | Debug mode | True |
| DB_ENGINE | sqlite or postgres | sqlite |
| DB_NAME | PostgreSQL DB name | finflow |
| DB_USER | PostgreSQL user | postgres |
| DB_PASSWORD | PostgreSQL password | postgres |
| DB_HOST | PostgreSQL host | localhost |
| KAFKA_BROKER | Kafka broker URL | localhost:9092 |
| KAFKA_TOPIC_CREATED | Created events topic | transaction.created |
| KAFKA_TOPIC_UPDATED | Updated events topic | transaction.updated |
| MINIO_ENDPOINT | MinIO endpoint | localhost:9000 |
| MINIO_ACCESS_KEY | MinIO access key | minioadmin |
| MINIO_SECRET_KEY | MinIO secret key | minioadmin |
| MINIO_BUCKET | MinIO bucket | finflow-docs |
| HMAC_SECRET | Internal HMAC secret | dev-hmac-secret-change-me |
| ACCOUNT_SERVICE_URL | Account Service base URL | http://localhost:8000 |

---

## Running the Services

### With Docker Compose (recommended)
```bash
docker-compose up --build
```

### Locally without Docker (Codespaces)

**Account Service:**
```bash
cd account-service
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

**Processing Service:**
```bash
cd processing-service
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

---

## Running Tests

### Account Service
```bash
cd account-service
pytest --cov=apps --cov-report=term-missing -v
```

### Processing Service
```bash
cd processing-service
pip install -r requirements.txt
pytest --cov=app --cov-report=term-missing -v
```

### Coverage Results
- Account Service: **100%**
- Processing Service: **>86%**

### Linting
```bash
cd account-service
black apps/ --check
isort apps/ --check
flake8 apps/
```

---

## API Documentation

- Swagger UI: http://localhost:8000/api/docs/
- ReDoc: http://localhost:8000/api/redoc/
- Health check: http://localhost:8001/health
- MinIO Console: http://localhost:9001

---

## Key Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/token/ | Login — returns JWT |
| POST | /api/token/refresh/ | Refresh access token |

### Users
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/users/ | Register (no auth) |
| GET | /api/users/{id}/ | Get own profile |
| PATCH | /api/users/{id}/ | Update own profile |
| DELETE | /api/users/{id}/ | Soft-delete account |

### Accounts
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/accounts/ | List accounts |
| POST | /api/accounts/ | Create account |
| GET | /api/accounts/{id}/ | Get account |
| PATCH | /api/accounts/{id}/ | Update account |
| DELETE | /api/accounts/{id}/ | Soft-delete |

### Transactions
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/transactions/ | List transactions |
| POST | /api/transactions/ | Create → Kafka event |
| GET | /api/transactions/{id}/ | Get transaction |

### Documents
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/documents/ | List documents |
| POST | /api/documents/upload/ | Upload KYC file |
| GET | /api/documents/{id}/download/ | Download file |

### Internal (HMAC only)
| Method | Path | Description |
|--------|------|-------------|
| PATCH | /api/internal/transactions/{id}/ | Update status |

Required headers: `X-Timestamp`, `X-Nonce`, `X-Signature`

---

## Project Structurefinflow-project/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   └── API_CONTRACTS.md
├── account-service/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── manage.py
│   ├── pytest.ini
│   ├── setup.cfg
│   ├── mypy.ini
│   ├── config/
│   │   ├── settings.py
│   │   └── urls.py
│   └── apps/
│       ├── core/
│       │   ├── logging.py
│       │   ├── exceptions.py
│       │   ├── kafka_producer.py
│       │   ├── minio_client.py
│       │   └── hmac_middleware.py
│       ├── users/
│       ├── accounts/
│       ├── transactions/
│       ├── documents/
│       └── audit/
└── processing-service/
├── Dockerfile
├── requirements.txt
├── pytest.ini
└── app/
├── main.py
├── config.py
├── consumer.py
├── hmac_auth.py
├── airflow_stub.py
└── tests/
└── test_processing.py---

## Troubleshooting

**Postgres connection refused:**
```bash
docker start finflow-postgres
```

**Kafka not ready:**
```bash
docker-compose restart kafka
```

**MinIO not accessible:**
```bash
docker start finflow-minio
```

**Migrations not applied:**
```bash
docker exec finflow-account-service python manage.py migrate
```

**Tests failing — import errors:**
```bash
pip install -r requirements.txt
```

---

## Submission Checklist

- [x] `docker-compose up` starts all services
- [x] Swagger UI at http://localhost:8000/api/docs/
- [x] pytest passes — Account Service coverage 100%
- [x] pytest passes — Processing Service coverage >86%
- [x] No secrets hardcoded — all via .env
- [x] .env never committed
- [x] docs/ARCHITECTURE.md complete
- [x] docs/API_CONTRACTS.md complete
- [x] README.md complete
- [x] pre-commit config present
- [x] Audit logging with PII scrubbing
- [x] HMAC replay protection (timestamp + nonce)
