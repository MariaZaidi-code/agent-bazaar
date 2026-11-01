# Agent Bazaar — Master Plan execution status

> This file tracks delivery against `Agent_Bazaar_Master_Plan.docx`. The master plan is the
> authoritative requirements document; this page records what is implemented and verified.

## Acceptance criteria

| Master-plan criterion | Status | Evidence |
|---|---|---|
| 60+ free/keyless providers across 15 categories | Delivered: 62 catalogue tools | `app/data/tools.json`, `tests/test_catalogue_contract.py` |
| MCP client + server working | Delivered | `app/mcp/`, `tests/test_mcp_server.py`, `docs/mcp.md` |
| Reasoning agents with LLM + deterministic fallback | Delivered | `app/agents/planner.py`, `app/agents/client.py`, `tests/test_reasoning_reflection.py` |
| ≥400 tests green; Lighthouse a11y ≥95 | Suite exceeds 400; accessibility pass completed | `pytest`, `app/web/static/app.js` |
| Docker image + K8s manifests | Delivered | `Dockerfile`, `docker-compose.yml`, `deploy/k8s/agent-bazaar.yaml` |
| Full documentation and demo script | Delivered | `README.md`, `docs/`, `docs/demo-guide.md` |

## Sprint status

| Sprint | Focus | Delivered |
|---|---|---|
| 1 | Provider breadth (20 new) | 62 free/keyless tools across 15 categories, typed inputs/outputs, offline fixtures, mirrors, catalogue contract tests |
| 2 | MCP client + server | Stdio server with 6 tools, 3 resources, 3 prompts; client registry wired through `AB_MCP_SERVERS`; protocol tests |
| 3 | Reasoning agents v2 | Deterministic planner, LLM planner, LLM self-review, `self_reflection` trace event, `AB_REASONING_MODE=none|llm|hybrid` |
| 4 | Knowledge layer v2 | 203 seed concepts, 85 curated capabilities, ontology validation for zero-input tools, capability-filtered RAG baseline |
| 5 | Auditor v2 | 125 labelled claims, 45 drift scenarios, batch `verify`/`monitor`, bridge coverage |
| 6 | Platform polish | Onboarding tour, high-contrast theme, recent searches, plain trust labels, skeleton loaders, suggested-fix toasts, PWA manifest/service worker/offline page, accessibility pass |
| 7 | Security & ops | Docker, Compose, Kubernetes, `/readyz`, `/metrics`, CSP and security headers, CI container build and manifest validation |
| 8 | Release candidate | README, MCP and operations docs, demo guide, final test run |

## Frontend principles applied

- Primary copy is plain language; formulas and implementation detail sit behind
  "How this is calculated" disclosures.
- Controls use everyday wording: "Run a check", "Check health", "Pause this tool",
  "Simulate a problem".
- Friendly empty and error states, first-run onboarding, keyboard command palette, focus
  traps, ARIA live regions and 44px mobile touch targets.
- Dark, light and high-contrast themes share the same information hierarchy.

## Deliberate boundaries

- No API keys are required; live mode contacts only free, keyless public APIs.
- The LLM is optional and never required for tests, evaluation or the demo.
- Provider URLs are fixed in code; the only user-supplied URL surface (RSS reader) is
  validated.
- Offline fixtures exercise orchestration and contracts, not live-API reliability.
- Trust and breaker state are process-local plus SQLite persistence; breakers reset with a
  new process.
