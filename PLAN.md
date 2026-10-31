# Agent Bazaar — Remediation & Growth Plan

> Status: **PLAN ONLY.** No code changes until you reply "go".
> Scope: frontend UX/copy/formatting + backend/provider expansion + platform features.

---

## 1. Diagnosis (what is wrong today)

### Frontend
- **Math jargon leaks into the UI**: Beta scoring formula `(s+1)/(s+f+2)`, posterior means, circuit-breaker states, ontology types, SHACL, RDF, GraphRAG, etc. are shown verbatim with no plain-language explanation. Users see formulas, not meaning.
- **Poor visual hierarchy**: dense 10–13px text, tight cards, many abbreviations, mixed metaphors (window bars, terminal routes, "quiet instrument" skin).
- **Not user-friendly**: six routes but no clear "what do I do first"; empty states are technical; errors are raw; controls like *Verify now / Monitor only / Simulate drift / Reset demo* are expert-oriented; no onboarding.
- **Accessibility gaps**: keyboard flows, focus management, ARIA live regions, color-only status, small touch targets on mobile.
- **Inconsistent formatting**: code blocks, tables, citations, traces, monitor feed all use different densities; long text overflows; no responsive polish for new pages beyond basic stacking.

### Backend
- **Limited providers (8)**: weather, currency, geocoding, countries, holidays, arXiv, university SQL, document QA + mock. No news, finance, crypto, sports, movies, books, recipes, translation, IP/timezone, astronomy, etc.
- **Limited task capabilities**: geocoding/weather/currency/holidays/documents. No search, comparison, summarization over multiple sources, scheduling, saved workflows.
- **Thin platform features**: no user accounts/sessions, no saved tasks/favorites, no webhooks, no rate limiting, no caching policy controls, no provider health dashboard beyond monitor, no analytics/usage, no multi-tenant.
- **Operational gaps**: no structured logging/metrics, no graceful degradation UI, no admin surface, no data export beyond JSON trace.

---

## 2. Goals

1. **Plain language first**: every screen explains what happened and what to do next in one sentence. Formulas live behind an optional "How this is calculated" disclosure.
2. **One obvious next action** on every page (primary CTA), with secondary actions visually de-emphasized.
3. **Provider breadth**: ≥ 25 free/keyless providers across ≥ 10 capability categories, with consistent quality profiles.
4. **Feature depth**: saved tasks, favorites, scheduled runs, multi-source answers, provider health, usage analytics, exports.
5. **Accessibility**: WCAG 2.1 AA for core flows; keyboard-only usable; screen-reader friendly.
6. **No regression**: keep 261+ tests green; add tests for new providers/features.

---

## 3. Frontend plan

### 3.1 Information architecture (simplify)
- **Home (Dashboard)** becomes a guided "Ask anything" page with 3 starter prompts and a one-line explanation of what the app does.
- **Marketplace** → "Find tools" (search-first, filters as chips, plain capability labels).
- **Monitor** → "System health" (plain status: Healthy / Degraded / Recovering; hide breaker internals behind details).
- **Documents** → "Your files" (upload + ask; preview; citations).
- **Trust Center** → "Why trust this tool?" (plain score: "X of Y recent checks passed", not posterior mean).
- **Docs** → "Help" (quickstart, FAQ, API).

### 3.2 Copy & jargon removal
- Replace formula strings with labels: "Trust score (based on recent checks)" + disclosure "How calculated".
- Rename technical controls: *Verify now* → *Run a check*, *Monitor only* → *Check health*, *Simulate drift* → *Simulate a problem*, *Trip breaker* → *Pause this tool*, *Reset demo* → *Reset demo data*.
- Empty states: "No documents yet — upload a file to start" instead of "No documents yet".
- Error messages: human sentence + suggested fix; never raw exception text.

### 3.3 Visual system
- Raise body type floor to 15–16px for prose; keep 12–13px only for metadata.
- Consistent spacing scale (4/8/12/16/24/32), card radius, shadow tokens.
- One accent color for primary actions; status colors only for status.
- Tables → responsive cards on mobile; code blocks with copy button; citations as quoted cards.
- Dark/light theme parity check.

### 3.4 Usability & accessibility
- Onboarding tour (3 steps) on first visit; dismissible.
- Command palette kept but with plain labels + recent items.
- Focus trap in modals; Esc closes; focus returns to trigger.
- ARIA live regions for async results; screen-reader announcements.
- Touch targets ≥ 44px; mobile bottom nav instead of hamburger where possible.
- Skeleton loaders → spinners with text; no bare "Loading…".

### 3.5 New frontend features
- Saved tasks & favorites (star a tool/result).
- Task history search + filter + export (CSV/JSON).
- Shareable task link (copy URL with task_id).
- Provider comparison view (side-by-side capabilities/trust).
- Notifications center (drift/breaker events) with mark-read.
- User preferences (theme, density, default page) persisted.

---

## 4. Backend plan

### 4.1 Provider expansion (target ≥ 25, free/keyless)
Categories and candidate providers:
- **Weather/geo**: Open-Meteo (done), NWS, wttr.in, IP geolocation.
- **Currency/finance**: Frankfurter (done), CoinGecko, exchangerate.host, Yahoo Finance (keyless endpoints).
- **Knowledge/reference**: Wikipedia, Wikidata, REST Countries (done), Open Library, Google Books (keyless), arXiv (done), PubMed (keyless), Crossref.
- **Travel/transport**: Nager.Date (done), aviationstack (keyless tier), OpenSky (keyless).
- **Food/recipes**: TheMealDB, TheCocktailDB (free).
- **Entertainment**: TMDB (keyless v3), OMDb (keyless demo), PokeAPI, Jikan (anime), RAWG (keyless).
- **Science/space**: NASA APOD (DEMO_KEY), SpaceX API, USGS earthquakes.
- **Utilities**: QR code, URL shortener, email validation, timezone (timezonedb keyless), UUID, hashing.
- **News**: Hacker News API, Reddit JSON (keyless), GNews (keyless tier).
- **Data**: university DB (done), SQL sandbox, CSV upload analysis.

Each new provider: `BaseProvider` subclass, `ToolSpec` in tools file, Auditor claims, mirror (backup-eligible), tests with fixtures.

### 4.2 Backend features
- **Accounts & sessions**: lightweight local user (name/avatar) persisted; no passwords initially (single-user sandbox) → optional simple auth later.
- **Saved tasks & favorites**: SQLite tables; endpoints CRUD.
- **Scheduled runs**: simple cron-like scheduler (APScheduler) for recurring tasks; results stored.
- **Multi-source answers**: Client composes across ≥ 2 providers and synthesizes; currently mostly single-chain.
- **Provider health dashboard**: uptime, latency percentiles, error rates, last success; endpoint + UI.
- **Usage analytics**: counts by capability/provider/day; export.
- **Caching policy**: TTL controls, cache invalidation endpoints, cache stats.
- **Rate limiting**: per-IP/per-route limits (slowapi) to protect free APIs.
- **Data export**: CSV/JSON for tasks, trust, monitoring, documents.
- **Webhooks (optional)**: notify on drift/breaker events.
- **Admin surface**: reset, seed, reindex, recompute trust (already partial).
- **Observability**: structured JSON logs, request IDs, `/metrics` (Prometheus) optional.

### 4.3 API improvements
- Pagination (`limit`/`offset`) on list endpoints; consistent envelope `{data, meta}`.
- Filtering/sorting query params on tools/tasks.
- Standard error shape `{error: {code, message, details}}`.
- API versioning prefix `/api/v1` (keep `/api` alias).
- OpenAPI examples for every endpoint.

### 4.4 Data model
- New tables: `users`, `saved_tasks`, `favorites`, `schedules`, `usage_events`, `provider_health`, `notifications`.
- Migrations (Alembic) instead of ad-hoc SQLite.
- Backup/export of runtime DB.

---

## 5. Quality & testing
- Unit tests per new provider (fixture-based, offline).
- Contract tests for API envelope/error shape.
- Frontend smoke tests (Playwright) for core flows + a11y checks (axe).
- Performance budget: dashboard first paint < 2s on mid-tier laptop.
- Keep Ruff + CI green; add frontend lint (eslint) optional.

---

## 6. Phased roadmap

| Phase | Scope | Est. effort |
|---|---|---|
| 0 | Decisions + design tokens + copy glossary | 2–3 days |
| 1 | Frontend IA + copy rewrite + a11y pass (no new features) | 1 week |
| 2 | Frontend visual system + responsive + onboarding | 1 week |
| 3 | Provider expansion batch 1 (10 providers) + tests | 1 week |
| 4 | Provider expansion batch 2 (15 providers) + mirror/auditor claims | 1 week |
| 5 | Backend features: saved tasks, favorites, health dashboard, exports | 1 week |
| 6 | Scheduling, analytics, rate limiting, migrations | 1 week |
| 7 | Polish, performance, docs, final QA | 3–4 days |

Total ≈ 6–7 weeks. Can be parallelized across frontend/backend.

---

## 7. Decisions needed from you (before "go")

1. **Auth**: keep single-user sandbox (no login) or add simple local accounts? (Recommend: single-user now, accounts later.)
2. **Provider priority**: which categories matter most? (Recommend: finance/crypto + reference + entertainment first.)
3. **LLM**: keep optional/offline-first or make LLM planner default when key present? (Recommend: keep optional.)
4. **Deployment target**: local-only or deployable (Docker)? (Recommend: add Dockerfile + compose.)
5. **Branding**: keep "Agent Bazaar" + "Quiet Instrument" visual direction or full rebrand? (Recommend: keep name, soften visuals.)
6. **Scope cut**: if time-boxed to 2 weeks, do only Phase 1–3 (frontend IA/copy + 10 providers). Confirm.

---

## 8. What I will NOT do without explicit approval
- No destructive data resets, no provider key requirements, no breaking API changes without versioning, no removal of existing tests.

---

Reply **"go"** (optionally with decisions 1–6) and I will start with Phase 0 + Phase 1.
