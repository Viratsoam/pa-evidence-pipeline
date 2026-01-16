# AI Development Notes

- Tools used: Cursor (ChatGPT-powered), ChatGPT in this session.
- Key prompts used:
  1) “Read the Basys Backend Engineer assignment doc and list requirements.”  
  2) “Propose plan for API (NestJS) + worker (FastAPI) + Redis + Postgres.”  
  3) “Implement idempotent document upload endpoint with Redis queue and Postgres.”  
  4) “Implement worker pipeline with retries/backoff/DLQ and policy evaluation.”  
  5) “Add tests for idempotency skip and retry→DLQ behavior.”  
  6) “Toggle policy between PT-only vs PT-or-NSAIDs and align docs/tests.”
- Accepted vs rejected:
- Accepted: Redis list as simple queue + DLQ; line-level citation guardrails; JSON logs without PHI; PT-required policy to match expected NEEDS_MORE_INFO for the sample note.
- Rejected: Allowing empty Idempotency-Key (would accidentally dedupe unrelated uploads); PT-or-NSAIDs default (we chose PT-required to align with expected outcome).
- Correction example: AI initially drafted Redis client init placeholders in the worker; corrected to single `Redis.from_url(REDIS_URL)` to avoid misconfigured connections and ensure metrics/queue use the same client. Also adjusted policy/guardrails so missing therapy yields NEEDS_MORE_INFO instead of DLQ.
