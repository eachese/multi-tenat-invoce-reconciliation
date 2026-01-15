# Flow RMS Invoice Reconciliation API

A multi-tenant platform for reconciling invoices and bank transactions. The service exposes both REST and GraphQL interfaces, deterministic scoring heuristics, and optional AI-assisted explanations.

## Features

- Multi-tenant isolation enforced across services.
- REST API under `/api` with FastAPI docs at `/docs`.
- Strawberry GraphQL schema mounted at `/graphql`.
- Deterministic scoring engine with transparent reasoning output.
- Optional OpenAI-powered explanations with deterministic fallback.
- Idempotent bank transaction imports backed by conflict detection.

## Prerequisites

- Python 3.13
- [Poetry](https://python-poetry.org/) 1.7+
- Docker & Docker Compose (for container workflow)

Copy the example environment file and adjust as needed:

```bash
cp .env.example .env
```

Key environment variables:

| Variable | Description |
| --- | --- |
| `ENVIRONMENT` | Deployment environment label (default `development`). |
| `DATABASE_URL` | SQLAlchemy URL. Defaults to `sqlite:///./data/dev.db`. |
| `AI_API_KEY` | Optional OpenAI API key enabling AI explanations. Leave blank to use deterministic fallback. |
| `AI_MODEL` | OpenAI model identifier. Default `gpt-4o-mini`. |

## Local Development

Install dependencies and run the application:

```bash
make install
make dev
```

The development server reloads on code changes and listens at `http://localhost:8000`.

### Database schema management

The application automatically ensures the database schema exists during startup via `create_database_schema()` invoked in the FastAPI lifespan handler @app/main.py#29-41. When using SQLite, parent directories are created as needed @app/main.py#18-27.

For local development, the provided SQLite configuration is sufficient. If you switch to another database, update `DATABASE_URL` accordingly.

## Running Tests & Quality Gates

Target test coverage is enforced at ≥85% using pytest-cov.

```bash
make test          # pytest with coverage
make lint          # ruff check + mypy
make format        # black + isort
make format-check  # formatting verification only
```

## Domain Workflows

### Reconciliation Scoring

Transactions and invoices are scored deterministically using weighted components covering amount tolerance, date proximity, description similarity, and vendor boosts. See `score_match` and `MatchScore` for details @app/services/scoring.py#112-130.

`MatchScore.reasoning_text()` aggregates component details into a human-readable explanation consumed by the AI flow @app/services/scoring.py#28-45. This scoring feeds match proposals and confidence levels.

### Idempotent Bank Transaction Imports

The `BankTransactionService.import_transactions` method persists import batches under an idempotency key, preventing duplicate ingestion and raising conflicts on divergent payloads for the same key @app/services/reconciliation_service.py and tests covering the behavior @tests/test_services.py#61-100. Use stable `idempotency_key` values when re-submitting batches to ensure safe retries.

### AI Explanation Configuration

The explanation service attempts to resolve an OpenAI client when `AI_API_KEY` is available; otherwise it falls back to deterministic templates @app/services/explanation_service.py#22-80. The OpenAI client formats a structured prompt and classifies confidence bands `high`, `medium`, or `low` based on the reconciliation score @app/ai/provider.py#34-97. The fallback client mirrors the same confidence thresholds without network calls @app/ai/provider.py#99-121.

## API Access

### REST

- Health check: `GET /api/health`
- Create/list tenants: `POST /api/tenants`, `GET /api/tenants`
- Invoice management (tenant scoped):
  - `POST /api/tenants/{tenant_id}/invoices`
  - `GET /api/tenants/{tenant_id}/invoices`
    - Supports filters: `status`, `vendor_id`, `start_date`, `end_date`, `min_amount`, `max_amount`.
  - `DELETE /api/tenants/{tenant_id}/invoices/{invoice_id}`
- Bank transaction import (idempotent):
  - `POST /api/tenants/{tenant_id}/bank-transactions/import`
  - Requires `Idempotency-Key` header; repeated requests with the same key reuse the prior response payload.
- Reconciliation flow:
  - `POST /api/tenants/{tenant_id}/reconcile`
  - `POST /api/tenants/{tenant_id}/matches/{match_id}/confirm`
- AI explanation:
  - `GET /api/tenants/{tenant_id}/reconcile/explain?match_id=...`
  - The service resolves the match candidate before generating an AI or deterministic fallback explanation.

Interactive documentation is available at `http://localhost:8000/docs`.

### GraphQL

GraphQL endpoint is served at `http://localhost:8000/graphql` via Strawberry router @app/main.py#47-57. Use any GraphQL client or browser to introspect schema. Example query:

```graphql
query ExampleMatches($tenantId: ID!) {
  tenant(tenantId: $tenantId) {
    invoices(limit: 5) {
      items {
        id
        amount
        currency
        status
      }
    }
  }
}
```

## Docker & Container Workflow

Build and run using Docker Compose (auto-reloads for local iteration):

```bash
docker compose up --build
```

- The API listens on port 8000 by default.
- Volumes mount `./data` for SQLite persistence and `./app` for live code reload @docker-compose.yml#12-16.
- Database schema creation is handled on startup by the application's lifespan hook, so no external migration command is required @app/main.py#29-36.

For production-style execution without reloads, use the container CMD defined in the Dockerfile @Dockerfile#32-34 or run `docker run` with the built image.

## Final QA Checklist

Before delivery, verify the following smoke tests:

1. **Tenants** – Create a tenant via REST (`POST /api/tenants`) and confirm via GraphQL query that it is accessible by tenant-scoped resolvers.
2. **Invoices** – Create/list/delete invoices ensuring currency normalization and filters operate correctly.
3. **Bank Transactions** – Import a batch twice with the same idempotency key and confirm idempotent behavior; submit a divergent payload with the same key to observe the conflict response.
4. **Reconciliation** – Trigger reconciliation to produce matches, confirm match status transitions, and validate scoring confidence labels.
5. **AI Explanations** – With `AI_API_KEY` unset, ensure fallback explanations return deterministic messaging; with a fake or real key, validate error handling and fallback behavior @tests/test_explanation_service.py#88-124.
6. **REST & GraphQL** – Confirm `/api/health` responds with `{"status": "ok"}` and `/graphql` serves the schema and executes queries.

Document results of the QA run and package the repository or build artifacts with run instructions for final delivery.
