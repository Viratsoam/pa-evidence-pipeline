# Event-Driven PA Evidence Pipeline

Backend take-home implementing PA intake, async evidence extraction, policy evaluation, and auditable outputs with PHI-aware boundaries.

## Architecture
- API (NestJS/TypeScript) handles PA requests, document uploads (Idempotency-Key), status retrieval, and audit retrieval.
- Worker (FastAPI/Python) consumes document events from Redis, runs OCR mock → extraction → policy evaluation → evidence pack persistence, with retries/backoff/DLQ and rate limiting.
- PostgreSQL with schemas: `core` (metadata, audit, decisions) and `phi` (documents, evidence details).
- Redis queues: `document_uploaded` main queue; `document_uploaded_dlq` dead-letter queue.

```mermaid
flowchart TB
    subgraph Client[" "]
        C[Client/Postman]
    end
    
    subgraph API["API Service (NestJS :3000)"]
        A1[POST /v1/pa-requests<br/>Create PA Request]
        A2[POST /v1/pa-requests/{id}/documents<br/>Upload Document<br/>Idempotency-Key]
        A3[GET /v1/pa-requests/{id}<br/>Get Status + Evidence Pack]
        A4[GET /v1/audit<br/>Get Audit Events]
    end
    
    subgraph Queue["Redis Queue"]
        Q[document_uploaded<br/>Main Queue]
        DLQ[document_uploaded_dlq<br/>Dead Letter Queue]
    end
    
    subgraph Worker["Worker Service (FastAPI :8000)"]
        W1[Consume Event<br/>brpop with timeout]
        W2[Stage A: OCR Mock<br/>Retryable errors]
        W3[Stage B: Evidence Extraction<br/>Heuristic/LLM-hybrid<br/>Guardrails + Citations]
        W4[Stage C: Policy Evaluation<br/>TKA PT-required]
        W5[Stage D: Evidence Pack<br/>Persist + Audit Event]
    end
    
    subgraph DB["PostgreSQL"]
        CORE[(core schema<br/>pa_requests<br/>document_jobs<br/>evidence_packs<br/>audit_events)]
        PHI[(phi schema<br/>documents<br/>evidence_details)]
    end
    
    subgraph Observability[" "]
        M[/metrics<br/>Prometheus]
        L[Structured Logs<br/>JSON, no PHI]
    end
    
    C -->|REST| A1
    C -->|REST| A2
    C -->|REST| A3
    C -->|REST| A4
    
    A1 -->|INSERT| CORE
    A2 -->|INSERT| PHI
    A2 -->|LPUSH| Q
    A3 -->|SELECT| CORE
    A3 -->|SELECT| PHI
    A4 -->|SELECT| CORE
    
    Q -->|brpop| W1
    W1 --> W2
    W2 -->|retry on error| W2
    W2 --> W3
    W3 -->|fallback if LLM fails| W3
    W3 --> W4
    W4 --> W5
    W5 -->|INSERT| CORE
    W5 -->|INSERT| PHI
    
    W1 -.->|max retries| DLQ
    
    Worker -->|/metrics| M
    API -->|JSON logs| L
    Worker -->|JSON logs| L
    
    style C fill:#e1f5ff
    style API fill:#fff4e1
    style Queue fill:#ffe1f5
    style Worker fill:#e1ffe1
    style DB fill:#f5e1ff
    style Observability fill:#ffe1e1
```

## Running locally
Prereqs: Docker + docker-compose.

```
docker compose up --build
```

Services:
- API: http://localhost:3000
- Worker: http://localhost:8000 (health/metrics)
- Postgres: localhost:5432 (appuser/appsecret/appdb)
- Redis: localhost:6379
- Postman collection: `postman/PA Evidence Pipeline.postman_collection.json` (import into Postman)

Environment (defaults in compose):
- `API_KEY=dev-api-key`
- `QUEUE_NAME=document_uploaded`, `DLQ_NAME=document_uploaded_dlq`
- `DATABASE_URL=postgres://appuser:appsecret@db:5432/appdb`
- `REDIS_URL=redis://redis:6379`
- `EXTRACTION_MODE=heuristic` (set to `hybrid` to try LLM-style extractor then fall back to heuristics)
- `MAX_ATTEMPTS=3` (worker retries before DLQ)
- `MAX_CONCURRENCY=5` (worker semaphore)
- `MAX_RATE_PER_SEC=5` (rate limiter simulating downstream limits)

## API endpoints (prefix /v1)
- `POST /v1/pa-requests`  
  - Headers: `x-api-key`  
  - Body: `{}` (no fields)  
  - Returns: `{ request_id }`
- `POST /v1/pa-requests/{request_id}/documents`  
  - Headers: `x-api-key`, **`Idempotency-Key` (required)**  
  - Body: `{ "text": "<synthetic note>" }`  
  - Returns: `{ request_id, job_id }`
- `GET /v1/pa-requests/{request_id}`  
  - Headers: `x-api-key`  
  - Returns: request status + latest evidence pack (if ready)
- `GET /v1/audit?request_id=...`  
  - Headers: `x-api-key`  
  - Returns: audit events (no PHI)

Quick E2E (happy path):
```
REQ=$(curl -s -X POST http://localhost:3000/v1/pa-requests -H "x-api-key: dev-api-key" | jq -r .request_id)
curl -s -X POST http://localhost:3000/v1/pa-requests/$REQ/documents \
  -H "x-api-key: dev-api-key" \
  -H "Idempotency-Key: demo-key-1" \
  -H "Content-Type: application/json" \
  -d '{ "text": "Patient: John Doe\nDx: Knee pain, suspected osteoarthritis.\nImaging: X-ray shows joint space narrowing and osteophytes.\nTherapy: Trial of NSAIDs for 3 weeks. No documented physical therapy.\nFunction: Difficulty climbing stairs; cannot walk > 1 block; ADLs impacted.\nPlan: Requesting total knee arthroplasty." }'
sleep 1
curl -s http://localhost:3000/v1/pa-requests/$REQ -H "x-api-key: dev-api-key"
curl -s "http://localhost:3000/v1/audit?request_id=$REQ" -H "x-api-key: dev-api-key"
```

## Tests
- Python tests (idempotency + retry→DLQ logic):  
  ```
  pip install -r worker/requirements.txt -r tests/requirements.txt
  PYTHONPATH=. pytest tests/test_worker_logic.py
  ```

## Reliability & observability
- Retries with exponential backoff (>=3 attempts), DLQ after max attempts.
- Idempotency enforced via Idempotency-Key (unique per request).
- Concurrency control with worker semaphore; rate limiter simulates external RPS limits.
- Metrics (`/metrics`): processed, failed, retried counters; latency histogram.
- Structured JSON logs (no PHI text), carrying request_id/job_id/trace_id/attempt.
- Audit log stored in DB with actor/action/timestamp/request_id/metadata.

## Production hardening plan (high level)
- Add JWT/service-to-service auth, scoped API keys, and RBAC.
- Encrypt PHI at rest, rotate secrets, and use separate DB roles per schema.
- Add message visibility timeouts/ack semantics (e.g., SQS) and idempotent worker writes with state machines.
- Add tracing (OpenTelemetry), dashboards/alerts on DLQ growth, latency SLOs.
- Harden validation (JSON schema), richer citation offsets, and model confidence scores.
- Blue/green deploys, migration gating, chaos testing for partial failures.
- LLM/RAG path: `EXTRACTION_MODE=hybrid` uses a placeholder LLM step with fallback to heuristics; to make it real, wire an LLM client with strict JSON schema validation, citations, confidence thresholds, timeouts, and rate limits, keeping the heuristic fallback.

## Trade-offs / cuts
- Extraction uses heuristics (regex/keyword) instead of LLM; offsets are line-level.
- Queue is Redis list (no visibility timeouts); suitable for local demo.
- Tests are focused on logic (idempotency skip + retry→DLQ) rather than full integration.
- No multi-tenant or full FHIR mapping; kept minimal to meet time-box.

## Synthetic note outcome
- Current policy: requires physical therapy; NSAIDs alone are insufficient. The provided example (NSAIDs, no PT) yields `NEEDS_MORE_INFO` with missing `conservative_therapy` (“physical therapy documentation”).
- Quick check:
  ```
  REQ=$(curl -s -X POST http://localhost:3000/v1/pa-requests -H "x-api-key: dev-api-key" | jq -r .request_id)
  curl -s -X POST http://localhost:3000/v1/pa-requests/$REQ/documents \
    -H "x-api-key: dev-api-key" \
    -H "Idempotency-Key: demo-pt-required" \
    -H "Content-Type: application/json" \
    -d '{ "text": "Patient: John Doe\nDx: Knee pain, suspected osteoarthritis.\nImaging: X-ray shows joint space narrowing and osteophytes.\nTherapy: Trial of NSAIDs for 3 weeks. No documented physical therapy.\nFunction: Difficulty climbing stairs; cannot walk > 1 block; ADLs impacted.\nPlan: Requesting total knee arthroplasty." }'
  curl -s http://localhost:3000/v1/pa-requests/$REQ -H "x-api-key: dev-api-key"
  ```
  Expect decision `NEEDS_MORE_INFO` and missing `conservative_therapy`.

