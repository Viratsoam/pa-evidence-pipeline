-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Schemas for PHI separation
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS phi;

-- PA requests (non-PHI)
CREATE TABLE IF NOT EXISTS core.pa_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL DEFAULT 'pending',
  latest_pack_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Document ingestion jobs (non-PHI metadata)
CREATE TABLE IF NOT EXISTS core.document_jobs (
  job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID NOT NULL REFERENCES core.pa_requests(id) ON DELETE CASCADE,
  idempotency_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  trace_id UUID NOT NULL DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (request_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_document_jobs_request ON core.document_jobs(request_id);

-- Stored document text (PHI)
CREATE TABLE IF NOT EXISTS phi.documents (
  job_id UUID PRIMARY KEY REFERENCES core.document_jobs(job_id) ON DELETE CASCADE,
  request_id UUID NOT NULL REFERENCES core.pa_requests(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Evidence pack (non-PHI summary)
CREATE TABLE IF NOT EXISTS core.evidence_packs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID NOT NULL REFERENCES core.pa_requests(id) ON DELETE CASCADE,
  decision TEXT NOT NULL,
  explanation TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evidence_packs_request ON core.evidence_packs(request_id);

-- Evidence details (PHI)
CREATE TABLE IF NOT EXISTS phi.evidence_details (
  pack_id UUID PRIMARY KEY REFERENCES core.evidence_packs(id) ON DELETE CASCADE,
  evidence JSONB NOT NULL,
  sources JSONB,
  missing_fields TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Audit events (non-PHI)
CREATE TABLE IF NOT EXISTS core.audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID REFERENCES core.pa_requests(id) ON DELETE CASCADE,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_request ON core.audit_events(request_id);
