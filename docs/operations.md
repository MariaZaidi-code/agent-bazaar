# Agent Bazaar operations

## Local run

```powershell
python -m pip install -r requirements-dev.txt
$env:PYTHONPATH = "src;."
python run.py
```

Open <http://127.0.0.1:8000>. Set `AB_OFFLINE_MODE=true` to use deterministic fixtures
without contacting any provider.

## Docker

```powershell
docker compose up --build
```

The container exposes port `8000`, writes runtime data to the `agent_bazaar_runtime`
volume and exposes a `/readyz` health check.

## Kubernetes

```powershell
docker build -t agent-bazaar:local .
kubectl apply -f deploy/k8s/agent-bazaar.yaml
```

The manifest creates a namespace, config map, persistent volume claim, deployment,
service and ingress. Update the ingress host and image reference for your cluster.

## Health and metrics

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Version, mode, tool count and LLM status |
| `GET /readyz` | Readiness probe; 503 until providers are loaded |
| `GET /metrics` | Prometheus text metrics (requests, errors, tools, trust) |

## MCP server

Agent Bazaar can expose itself as an MCP server:

```powershell
$env:PYTHONPATH = "src;."
python -m app.mcp.server
```

Or install the console script with `pip install -e .` and run `agent-bazaar-mcp`.

Connect an MCP client with a stdio command such as
`python -m app.mcp.server`. Configure the app to consume other MCP servers with a JSON
array such as `AB_MCP_SERVERS=["name|command arg1 arg2"]` (one entry per server).
See [mcp.md](mcp.md) for tools, resources, prompts and reasoning modes.

## Security defaults

- CSP, `X-Frame-Options: DENY`, `nosniff` and a strict referrer policy are set on every response.
- Mutating `/api/*` requests are rate limited per client and route.
- Session cookies are `HttpOnly` and `SameSite=Lax`; set `AB_SESSION_COOKIE_SECURE=true` behind HTTPS.
- Provider URLs are fixed in code; user-supplied URLs are validated for the RSS reader.
