# FinFlow — Fintech Microservices Platform
 
FinFlow is a production-style fintech platform built as a two-service microservices system.
The repository contains:
- `account-service/` — Django REST Framework API for users, accounts, transactions, documents, and internal HMAC auth
- `processing-service/` — FastAPI Kafka consumer that simulates payment processing and updates transaction status via HMAC-signed callbacks
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
## Overview
 
FinFlow implements a secure transaction workflow with two independent services:
 
### Account Service — Django REST Framework (`:8000`)
- User registration and JWT authentication
- Account (wallet) CRUD operations with balance tracking
- Transaction creation, listing, and retrieval
- Account balance updated atomically on transaction completion — CREDIT increases balance, DEBIT decreases it; insufficient funds automatically marks the transaction as FAILED
- KYC document upload/download using MinIO
- Internal HMAC-signed endpoint for status updates
- Audit logging and soft-delete support
### Processing Service — FastAPI (`:8001`)
- Kafka consumer for `transaction.created`
- Simulated Airflow processing stub
- HMAC-signed `PATCH` callback to Account Service
- Root endpoint for service status
## Architecture
 
FinFlow uses a hybrid synchronous/asynchronous flow:
 
1. Client calls Account Service with JWT auth.
2. Account Service creates a transaction in `PENDING` state.
3. Account Service publishes `transaction.created` to Kafka.
4. Processing Service consumes the event.
5. Processing Service runs a payment stub and sends an HMAC-signed `PATCH` to Account Service.
6. Account Service validates the HMAC request, updates the transaction to `COMPLETED` or `FAILED`, and adjusts the account balance atomically using `select_for_update()`.
7. Account Service publishes `transaction.updated`.
### Security
- External auth: JWT Bearer tokens via `POST /api/token/`
- Internal auth: HMAC-SHA256 on `/api/internal/transactions/{id}/`
- The HMAC check validates signature, timestamp tolerance, and nonce replay protection
## Prerequisites
 
- Docker + Docker Compose
- Python 3.12+
- Git
For GitHub Codespaces, Docker is available in the environment.
 
## Setup
 
```bash
git clone https://github.com/tusharjoshi1804/finflow-project.git
cd finflow-project
cp .env.example .env
docker-compose up --build
```
 
After the containers are running, apply Django migrations:
 
```bash
docker exec finflow-account-service python manage.py migrate
```
 
## Environment Variables
 
| Variable | Description | Default |
|----------|-------------|---------|
| DJANGO_SECRET_KEY | Django secret key | dev-secret-change-me |
| DEBUG | Debug mode | True |
| DB_ENGINE | sqlite or postgres | sqlite |
| DB_NAME | Database name | finflow |
| DB_USER | Database user | postgres |
| DB_PASSWORD | Database password | postgres |
| DB_HOST | Database host | localhost |
| KAFKA_BROKER | Kafka broker URL | localhost:9092 |
| KAFKA_TOPIC_CREATED | Created transaction topic | transaction.created |
| KAFKA_TOPIC_UPDATED | Updated transaction topic | transaction.updated |
| MINIO_ENDPOINT | MinIO endpoint | localhost:9000 |
| MINIO_ACCESS_KEY | MinIO access key | minioadmin |
| MINIO_SECRET_KEY | MinIO secret key | minioadmin |
| MINIO_BUCKET | MinIO bucket name | finflow-docs |
| HMAC_SECRET | Internal HMAC secret (min 32 bytes) | dev-hmac-secret-change-me |
| ACCOUNT_SERVICE_URL | Account Service base URL | http://localhost:8000 |
 
## Running the Services
 
### Docker Compose (recommended)
 
```bash
docker-compose up --build
```
 
### Run locally without Docker
 
**Account Service**
 
```bash
cd account-service
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```
 
**Processing Service**
 
```bash
cd processing-service
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```
 
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
 
## API Documentation
 
- Swagger UI: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`
- Account Service root: `http://localhost:8000/` (redirects to Swagger)
- Processing Service root: `http://localhost:8001/`
- Processing Service health: `http://localhost:8001/health`
- MinIO Console: `http://localhost:9001`
## Key Endpoints
 
### Authentication
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/token/` | Login and obtain JWT |
| POST | `/api/token/refresh/` | Refresh JWT access token |
 
### Users
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/users/` | Register a new user |
| GET | `/api/users/{id}/` | Retrieve own profile |
| PATCH | `/api/users/{id}/` | Update own profile |
| DELETE | `/api/users/{id}/` | Soft-delete user |
 
### Accounts
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/accounts/` | List user accounts |
| POST | `/api/accounts/` | Create a new account |
| GET | `/api/accounts/{id}/` | Retrieve account details and balance |
| PATCH | `/api/accounts/{id}/` | Update account |
| DELETE | `/api/accounts/{id}/` | Soft-delete account |
 
### Transactions
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/transactions/` | List transactions |
| POST | `/api/transactions/` | Create transaction and publish Kafka event |
| GET | `/api/transactions/{id}/` | Get transaction details |
 
### Documents
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/documents/` | List documents |
| POST | `/api/documents/upload/` | Upload document (JPG, PNG, GIF, PDF up to 10MB) |
| GET | `/api/documents/{id}/download/` | Download document |
 
### Internal HMAC Endpoint
| Method | Path | Description |
|--------|------|-------------|
| PATCH | `/api/internal/transactions/{id}/` | Update transaction status and account balance |
 
Required headers: `X-Timestamp`, `X-Nonce`, `X-Signature`
 
## Project Structure
 
```text
finflow-project/
├── account-service/
│   ├── Dockerfile
│   ├── manage.py
│   ├── pytest.ini
│   ├── requirements.txt
│   ├── setup.cfg
│   ├── mypy.ini
│   ├── config/
│   │   ├── settings.py
│   │   └── urls.py
│   ├── apps/
│   │   ├── core/
│   │   │   ├── exceptions.py
│   │   │   ├── hmac_middleware.py
│   │   │   ├── kafka_producer.py
│   │   │   ├── logging.py
│   │   │   └── minio_client.py
│   │   ├── users/
│   │   ├── accounts/
│   │   ├── transactions/
│   │   ├── documents/
│   │   └── audit/
│   └── tests/
├── processing-service/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── consumer.py
│       ├── hmac_auth.py
│       ├── airflow_stub.py
│       └── tests/
├── docker-compose.yml
└── docs/
    ├── API_CONTRACTS.md
    └── ARCHITECTURE.md
```
 
## Troubleshooting
 
### Account Service root returns 404
Use `http://localhost:8000/`. It now redirects to Swagger docs.
 
### Processing Service root returns 404
Use `http://localhost:8001/`.
 
### Processing Service health
Use `http://localhost:8001/health`.
 
### Docker Compose issues
- Confirm `.env.example` was copied to `.env`
- Confirm Docker is running
- Confirm Kafka, Postgres, and MinIO are healthy
### Kafka broker configuration
- In Docker Compose: `KAFKA_BROKER=kafka:29092`
- From host machine: `localhost:9092`
### Kafka consumer fails on Python 3.12
The `kafka-python` package has a known incompatibility with Python 3.12. This project uses `kafka-python-ng` instead, which is already specified in `requirements.txt`.
 
### Running behind GitHub Codespaces
The Account Service is configured with `SECURE_PROXY_SSL_HEADER` and `USE_X_FORWARDED_HOST` to work correctly behind the GitHub Codespaces tunnel. Make sure port visibility is set to **Public** in the Ports tab for Swagger to authenticate correctly.
