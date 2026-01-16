import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgres://appuser:appsecret@localhost:5432/appdb")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
QUEUE_NAME = os.getenv("QUEUE_NAME", "document_uploaded")
DLQ_NAME = os.getenv("DLQ_NAME", "document_uploaded_dlq")
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "5"))
MAX_RATE_PER_SEC = int(os.getenv("MAX_RATE_PER_SEC", "5"))
BACKOFF_BASE_SECONDS = float(os.getenv("BACKOFF_BASE_SECONDS", "1.5"))
EXTRACTION_MODE = os.getenv("EXTRACTION_MODE", "heuristic")  # options: heuristic, hybrid