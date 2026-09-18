# 0001: AgentHarbor application boundaries

- Status: accepted
- Date: 2026-09-18

## Context

The repository contains both an upstream project generator and an already generated application. The user wants a branded, runnable AI application while retaining the generator.

## Decision

Use **AgentHarbor** as the product display name. Keep the `my_ai_app/` directory, Python package identifiers, and `my_ai_app` database name stable. Store credentials only in ignored environment files. Run FastAPI and Next.js natively against local PostgreSQL on port 5432; Docker remains optional.

The browser communicates with the backend through the frontend's existing API integration. The backend owns authorization, business rules, database access and provider credentials. PostgreSQL schema changes use Alembic.

## Alternatives

Renaming every package, command, directory and database would add migration risk without improving the visible product. Docker is useful for reproducibility but is not required to run this installation.

## Consequences

Branding and technical identifiers differ intentionally. Fixes to the generated application need separate template changes if they should affect future generated projects. AI responses require an API key and accessible model. RAG, billing, teams and external monitoring are not enabled in this build.

## Validation

Run the checks in [quality.md](../quality.md). Confirm website branding, database readiness and account flows. Brand selection is a product choice; domain or trademark availability has not been assessed.
