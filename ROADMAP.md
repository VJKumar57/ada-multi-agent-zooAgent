# Zoo Tour Guide Roadmap

## 1. Evaluation And Observability

- Maintain deterministic evaluation cases for animal data, research, admission,
  Cafe credits, travel, authentication, and provider failures.
- Keep evaluations offline with mocked Cloud Run, Firebase, MCP, Vertex AI, and
  Wikipedia boundaries; do not call live services from the test suite.
- Record privacy-safe structured Cloud Run logs for cache outcomes, sanitized
  activity names, upstream status, and request latency.
- Establish dashboards and alerts for agent errors, upstream provider failures,
  cache effectiveness, and latency.

## 2. Managed Zoo Data Catalog

- Replace demonstration animal, ticket, Cafe, and location data with approved,
  versioned Zoo data sources.
- Define ownership, update workflows, validation, and audit history for catalog
  changes.

## 3. Curated RAG

- Index approved Zoo documents and policies with source attribution.
- Retrieve Zoo sources before general knowledge, with evaluation coverage for
  grounding and stale content.

## 4. Tour Planner Agent

- Create an itinerary specialist for selected locations, visitor preferences,
  accessibility needs, opening hours, and approved events.
- Keep itinerary state authenticated and scoped to a visitor session.

## 5. Events And Real-Time Updates

- Integrate approved event, exhibit, and operating-status feeds.
- Apply source-specific freshness rules and show the effective update time.

## 6. Production Hardening

- Use dedicated least-privilege service accounts, shared cache infrastructure,
  secret management, load testing, disaster recovery, and cost controls.
- Review security, privacy, accessibility, and operational runbooks before each
  production release.