# Zoo Tour Guide Project Instructions

## Architecture

- This workspace is a three-service Zoo Tour Guide deployed to Cloud Run:
  - `zoo_chat_ui/` is the public Flask browser UI and Firebase Authentication boundary.
  - `multi_tool_agent/` is the ADK and Vertex AI orchestration package.
  - `zoo_mcp_server/` is the internal FastMCP Zoo Animal Directory service.
- Preserve the request flow: browser -> Flask UI -> private ADK API -> private MCP service.
- Keep service ownership explicit. Do not move UI authentication, agent orchestration, or MCP directory behavior across service boundaries without updating deployment and integration documentation.

## Security And Identity

- Keep configuration environment-driven. Do not hard-code URLs, project IDs, API keys, credentials, or service-account data.
- Never commit `.env` files, Firebase credentials, identity tokens, or other secrets. Keep required UI variables documented in `zoo_chat_ui/.env.example`.
- Verify Firebase ID tokens in Flask before serving UI API routes. Keep authorization and role checks on the server.
- The browser must never choose `USER_ROLE`. Flask derives the role from a verified Firebase claim and creates the ADK session with that server-owned state.
- ADK tools must obtain role-dependent behavior from `ToolContext.state`, not request text or client payloads.
- Use Google identity tokens for calls to private Cloud Run services. Preserve authenticated MCP calls when `MCP_SERVER_AUTHENTICATED=TRUE`.

## ADK And MCP Changes

- Follow the existing ADK composition in `multi_tool_agent/agent.py`: `Agent` for specialists, `SequentialAgent` for ordered workflows, explicit `sub_agents` for routing, and `ToolContext` for workflow state.
- Custom tools should use typed parameters, return structured dictionaries with a `status`, and return explicit error data for unavailable input.
- Preserve clear tool-routing prompts. When zoo-specific data is requested, retrieve authoritative MCP data before general research; present zoo-specific details before general facts.
- Keep ticket and Cafe calculations server-side. Apply employee or member discounts before the eligible full-day-pass Cafe credit.
- Treat the animal directory, ticket catalog, and Cafe menu as demonstration data. Do not represent sample values as production data without an approved source.

## Flask And Browser UI

- Retain server-side request validation, size limits, upstream timeouts, rate limiting, authenticated route decorators, and role checks for UI API changes.
- Keep ADK sessions scoped to the authenticated Firebase user and avoid exposing service-to-service credentials to the browser.
- `zoo_chat_ui/templates/index.html` is vanilla HTML, CSS, JavaScript, and Jinja configuration injection. Preserve the Firebase authentication lifecycle, accessible labels, responsive behavior, and safe DOM APIs such as `textContent` for chat content.

## Deployment And Documentation

- Each Cloud Run service must listen on `$PORT`; preserve the existing `Procfile` commands unless its service runtime changes deliberately.
- Supply production configuration through Cloud Run environment variables, not nested `.env` files.
- Update `README.md` whenever a public endpoint, role/pricing rule, configuration variable, local command, deployment step, or integration behavior changes.

## Validation

- Run focused tests for changed deterministic behavior. Mock Vertex AI, Cloud Run, Firebase, MCP network transport, and Wikipedia in unit tests; do not call live services from the test suite.
- Add or update pytest coverage for ticket/Cafe calculations, MCP lookup behavior, and Flask authentication, validation, authorization, or rate-limit behavior when those paths change.
- Run `ruff check .` and `pytest` after Python changes. Also run `python -m compileall multi_tool_agent zoo_chat_ui zoo_mcp_server` when changing Python packages.
- For integration or deployment changes, follow the README smoke tests for the browser, ADK REST API, and MCP service.
