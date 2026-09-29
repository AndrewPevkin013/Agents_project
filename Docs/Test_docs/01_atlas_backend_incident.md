# Atlas API - Production Incident Report

Document ID: ATL-INC-2026-0917
Service: Atlas API
Environment: Production
Incident date: 17 September 2026
Status: Resolved

## System overview

Atlas API is an internal backend service implemented with Python and FastAPI.
The production deployment uses PostgreSQL as the primary database and Redis
for short-lived cache entries. External HTTPS traffic is accepted on port 8443.
The service exposes `/health` for availability monitoring.

## Incident

At 09:42 UTC, monitoring detected an increase in request latency. The p95 latency
reached 612 ms. The operational threshold for p95 latency is 350 ms.

Investigation showed that the Redis connection pool was exhausted after a deployment.
Database availability remained normal and no data loss was detected.

## Recovery procedure

The on-call engineer captured a diagnostic bundle before restarting the affected
application workers. Restarting the service before preserving the diagnostic bundle
is prohibited by the operations procedure.

After the worker restart and Redis pool reconfiguration, p95 latency returned to
184 ms. The incident was closed at 10:21 UTC.

## Operational facts

- Production HTTPS port: 8443
- Health endpoint: /health
- Maximum acceptable p95 latency: 350 ms
- Primary database: PostgreSQL
- Cache: Redis
- Diagnostic bundle must be preserved before restart
- No customer data was lost

## Information intentionally absent

This document does not contain administrator passwords, root passwords, API secrets,
private keys, or database credentials.
