"""Configuration for FinFlow Processing Service."""
from decouple import config

KAFKA_BROKER: str = config("KAFKA_BROKER", default="localhost:9092")
KAFKA_TOPIC_CREATED: str = config("KAFKA_TOPIC_CREATED", default="transaction.created")
KAFKA_TOPIC_UPDATED: str = config("KAFKA_TOPIC_UPDATED", default="transaction.updated")
KAFKA_GROUP_ID: str = config("KAFKA_GROUP_ID", default="processing-service")

ACCOUNT_SERVICE_URL: str = config("ACCOUNT_SERVICE_URL", default="http://localhost:8000")
HMAC_SECRET: str = config("HMAC_SECRET", default="dev-hmac-secret-change-me")

LOG_LEVEL: str = config("LOG_LEVEL", default="INFO")
