# Flow RMS Multi-Tenant Invoice Reconciliation — Implementation Guide

This guide outlines the phased delivery plan and detailed user stories for building the Flow RMS multi-tenant invoice reconciliation platform. It is designed for a senior Python backend engineer to drive the project from zero to production-ready state while satisfying functional, non-functional, and testing requirements.

---

## Guiding Principles

- **Tenant isolation first:** every read/write operation must be constrained by `tenant_id`; cross-tenant leakage is unacceptable.
- **Single source of truth:** expose REST and GraphQL interfaces through a shared service layer and repositories.
- **Deterministic reconciliation:** AI augments explanations only—the core matching engine is rule-based and testable.
- **Idempotency & resilience:** bulk imports and AI calls must be repeatable, fault-tolerant, and observable.
- **Testable architecture:** dependency injection, clear boundaries, and mocked AI clients enable comprehensive automated tests.

---

## Step-by-Step Delivery Plan

### Phase 0 – Project Scaffold & Tooling
1. **Repository Bootstrap**
   - Initialize Python 3.13 project (e.g., Poetry/UV/virtualenv).
   - Configure linting/formatting (ruff, black, isort, mypy optional).
   - Add `.env` loading (pydantic settings or python-dotenv) with placeholders for DB URL and AI credentials.
2. **FastAPI & Strawberry Setup**
   - Wire FastAPI app factory and Strawberry schema mounting under `/graphql`.
   - Enable lifespan management for DB sessions.
3. **Docker & Make Targets**
   - Create Dockerfile (multistage) and `docker-compose.yml` (if needed) with SQLite volume/shared storage.
   - Provide convenience scripts/Make targets for lint, test, run, format.

### Phase 1 – Persistence Layer & Models
1. **Database Engine Configuration**
   - Initialize SQLAlchemy 2.0 async or sync engine (sync recommended with FastAPI dependency-injected sessions).
   - Configure session management and base `DeclarativeBase`.
2. **Model Definitions**
   - Implement tables: `Tenant`, `Vendor`, `Invoice`, `BankTransaction`, `Match` (or `MatchCandidate`).
   - Add multi-tenant constraints: `tenant_id` foreign keys, indexes, and optional uniqueness (e.g., `(tenant_id, invoice_number)`).
3. **Utility & Repository Layer**
   - Create repository classes or data mappers per entity with CRUD plus filtered queries.
   - Add pagination helpers and filtering utilities (status, vendor, date range, amount range).
4. **Sample Migration / Seed Data**
   - Optional Alembic migration for structure (even if SQLite) to support future DB upgrades.

### Phase 2 – Multi-Tenancy Enforcement
1. **Request-Level Tenant Context**
   - Parse `tenant_id` from path (REST) and GraphQL inputs.
   - Implement dependency that validates tenant existence and injects `TenantContext`.
2. **Service Layer Tenant Guardrails**
   - Ensure every repository/service method requires tenant context; add defensive assertions.
   - Centralize 404/403 handling when data does not belong to requesting tenant.
3. **Test Isolation**
   - Add fixtures to create multiple tenants and verify cross-tenant access is blocked.

### Phase 3 – REST Endpoints
1. **Tenant Endpoints**
   - `POST /tenants` create.
   - `GET /tenants` list (optional but recommended for admin tooling).
2. **Invoice Endpoints**
   - `POST /tenants/{tenant_id}/invoices` with validation (amount required, defaults for currency).
   - `GET /tenants/{tenant_id}/invoices` with filters: status, vendor_id, date range, amount range.
   - `DELETE /tenants/{tenant_id}/invoices/{id}` with cascade/foreign-key safety.
3. **Bank Transaction Import**
   - `POST /tenants/{tenant_id}/bank-transactions/import` accepting list payload.
   - Implement idempotency via `Idempotency-Key` header or payload field; persist request hash.
   - Return created/ignored counts and imported records summary.
4. **Reconciliation & Matches**
   - `POST /tenants/{tenant_id}/reconcile` triggers deterministic engine, returns ranked matches.
   - `POST /tenants/{tenant_id}/matches/{match_id}/confirm` updates status and invoice/bank transaction state.
5. **AI Explanation Endpoint**
   - `GET /tenants/{tenant_id}/reconcile/explain` orchestrates AI/fallback logic.

### Phase 4 – GraphQL API (Strawberry)
1. **Schema Definition**
   - Mirror models with GraphQL types; reuse Pydantic schemas or dataclasses via Strawberry `@type`.
2. **Query Resolvers**
   - `tenants`, `invoices`, optional `bankTransactions`, `matchCandidates`, `explainReconciliation`.
   - Implement pagination/filter arguments consistent with REST.
3. **Mutation Resolvers**
   - `createTenant`, `createInvoice`, `deleteInvoice`, `importBankTransactions`, `reconcile`, `confirmMatch`.
4. **Shared Service Usage**
   - Ensure resolvers call same service layer used by REST for consistent behavior.

### Phase 5 – Reconciliation Engine
1. **Heuristic Rules Implementation**
   - Rules: exact amount (weight 0.5), tolerance match (0.2), date proximity (0.2), text similarity (0.1), vendor name boost.
   - Normalize scores to 0–1; compute composite score per invoice/transaction pair.
2. **Matching Strategy**
   - For each open invoice, produce top-N bank transactions above threshold.
   - Optionally deduplicate conflicting matches using greedy highest-score first.
3. **Persistence**
   - Store match candidates with status `proposed|confirmed|rejected`, tenant_id, score.
   - Update invoice status on confirmation.
4. **Service Contracts & DTOs**
   - Return service-layer DTO describing candidate, score, and reasoning snippet for AI context.

### Phase 6 – AI Explanation Layer
1. **Client Abstraction**
   - Define `AIClient` interface with `explain_match(context: MatchContext) -> Explanation`.
   - Provide `OpenAIClient` (config-driven) and `DeterministicFallbackClient`.
2. **Context Construction**
   - Limit to tenant-authorized data: invoice amount/date/vendor/description, transaction amount/date/description, heuristic score breakdown.
3. **Graceful Failure**
   - Wrap AI calls with timeout & error handling; on failure, log and fallback to deterministic explanation (template-based with score bands).
4. **Testing Strategy**
   - Mock AI client in unit tests; add integration smoke test for fallback path.

### Phase 7 – Testing & Quality Gates
1. **Pytest Suite**
   - Fixtures for in-memory SQLite DB and FastAPI test client.
   - Tests per requirement:
     - Create/list/delete invoices with filters.
     - Import bank transactions + idempotency conflict.
     - Reconciliation ranking deterministic behavior.
     - Match confirmation status transitions.
     - AI explanation endpoint with mocked success + forced failure fallback.
2. **Coverage & Lint**
   - Target >=85% coverage; enforce via pytest-cov.
   - Run lint/format in CI pipeline (GitHub Actions).

### Phase 8 – Packaging, Docs & Delivery
1. **README Authoring**
   - Document setup, run, reconciliation scoring, idempotency strategy, AI configuration, testing commands.
2. **Container Verification**
   - Build & run Docker image locally, ensure migrations auto-run and both REST & GraphQL mount correctly.
3. **Final QA**
   - Smoke-test tenants/invoices/import/reconcile/AI flows via REST client & GraphQL playground.
   - Prepare final artifact (git repo/zip) with instructions.

---



## Dependencies & Risk Mitigation

- **Database Transactions:** wrap bulk imports and reconciliation writes in transactions to prevent partial state.
- **Performance Considerations:** for large datasets, add batching to reconciliation or SQL-side filtering to limit candidate explosion.
- **AI Cost & Latency:** implement rate limiting and optional circuit breaker to protect tenants from slow AI requests.
- **Observability:** include structured logging with tenant_id, request IDs, and metrics for reconciliation/AI latency.

---

## Deliverables Checklist

- [x] FastAPI + Strawberry app with shared service layer.
- [x] SQLAlchemy models, schema migrations, and repository abstractions.
- [x] Tenant-aware REST endpoints with idempotent batch import.
- [x] Deterministic reconciliation engine persisting match candidates.
- [x] AI explanation client with fallback path and configuration.
- [x] GraphQL schema exposing queries and mutations.
- [x] Comprehensive pytest suite with mocked AI client.
- [x] Dockerfile and README documenting setup, scoring logic, idempotency approach, and testing instructions.

