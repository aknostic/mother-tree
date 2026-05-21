# Changelog

## v0.1.0 — 2026-05-21

First open-source release.

- Personas renamed to Saga (positioning strategist) and Lena (consultative
  diagnostician). Inspirations credited in `docs/inspirations.md`.
- Content layer is bring-your-own — no customer-specific content shipped.
- Docker-compose dev path; GitHub Actions CI; Apache 2.0 license.
- Production manifests in `deploy/` (target: Kubernetes with CloudNativePG +
  pgvector + PostGraphile; adapt as needed).
