# MCP client and server

Agent Bazaar speaks the [Model Context Protocol](https://modelcontextprotocol.io/) in both
directions:

- **MCP server**: Agent Bazaar exposes its task runner, catalogue search, traces, provider
  health, verification and monitoring as MCP tools, resources and prompts, so another agent
  (Claude Desktop, an IDE assistant, a custom client) can use the marketplace.
- **MCP client**: Agent Bazaar can launch and consume other stdio MCP servers and register
  their tools alongside the built-in providers.

## Server

Run the server over stdio:

```powershell
$env:PYTHONPATH = "src;."
python -m app.mcp.server
```

After `pip install -e .` the console script `agent-bazaar-mcp` does the same. The server uses
LSP-style `Content-Length` framing, as the MCP stdio transport specifies.

### Tools

| Tool | Arguments | Purpose |
|---|---|---|
| `run_task` | `task`, optional `document_id` | Plan, rank and execute a natural-language task with the Client agent |
| `search_tools` | `query`, optional `capability`, `limit` | Search the catalogue with GraphRAG and return ranked tools |
| `get_trace` | `task_id` | Read the persisted decision trace and final answer |
| `list_providers` | none | List every provider with mode, health and capability |
| `verify_tool` | `tool_id` | Run Auditor claim verification for one tool |
| `monitor_tool` | `tool_id` | Run the Auditor drift monitor for one tool |

### Resources

| URI | Content |
|---|---|
| `agent-bazaar://ontology` | Capabilities and concepts used for validation |
| `agent-bazaar://graph` | Every tool with its provider and capability |
| `agent-bazaar://trust` | Current trust scores and signal history |

### Prompts

`plan_task`, `verify_provider` and `explain_trust` are templates that a client can render with
its own arguments. `explain_trust` explicitly asks for plain language with no formulas.

### Client configuration

Claude Desktop and other MCP clients accept a command entry such as:

```json
{
  "mcpServers": {
    "agent-bazaar": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "env": {
        "PYTHONPATH": "C:/path/to/agent-bazaar/src;C:/path/to/agent-bazaar"
      }
    }
  }
}
```

Use `;` as the `PYTHONPATH` separator on Windows and `:` on macOS/Linux. Set
`AB_OFFLINE_MODE=true` for a deterministic demo that never contacts a provider.

## Client

The app starts configured MCP servers during its lifespan and exposes them through
`app.mcp.registry.MCPServerRegistry`. `AB_MCP_SERVERS` is a JSON array; each entry is
formatted as `name|command arg1 arg2`:

```dotenv
AB_MCP_SERVERS=["filesystem|npx -y @modelcontextprotocol/server-filesystem C:\\data"]
```

The command is split on spaces, so keep paths without spaces or wrap the server in a small
launcher script.

Each client performs the `initialize` handshake, lists tools and can call them by server
name. A failing server is isolated: discovery returns an empty tool list for that server
instead of breaking startup. The app also serves as its own MCP server, so a local
`agent-bazaar|python -m app.mcp.server` entry is a useful end-to-end check.

## Reasoning modes

The reasoning agents combine deterministic planning with an optional LLM. Set the mode with
`AB_REASONING_MODE`:

| Mode | Behaviour |
|---|---|
| `none` | Deterministic planner and answer synthesis only. No LLM calls. |
| `llm` | LLM planning and LLM self-review when `AB_LLM_PROVIDER` is configured. |
| `hybrid` (default) | Deterministic planning first, then LLM self-review when available. Falls back cleanly when no LLM is configured. |

Self-review records a `self_reflection` trace event with the completed steps, empty outputs,
fixture sources and an optional reviewer verdict. It never blocks a task; it adds plain-language
warnings to the result. The complete test suite and evaluation run in `none` mode.
