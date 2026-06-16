# MCP Diagram Agent

[![CI](https://github.com/shaikn6/mcp-diagram-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/shaikn6/mcp-diagram-agent/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

> **Turn a paragraph of text into a visual architecture diagram — in seconds.**

MCP Diagram Agent is a [Model Context Protocol](https://modelcontextprotocol.io/) server that accepts a natural language description of a software system and returns an [Excalidraw](https://excalidraw.com/)-compatible JSON diagram you can import and edit immediately.

It also ships a **REST API** (`/generate`) so any HTTP client can use it without MCP tooling.

---

## Architecture

```mermaid
graph LR
    subgraph Clients
        A[Claude Desktop / MCP Client]
        B[curl / HTTP Client]
    end

    subgraph mcp-diagram-agent
        C[MCP Server\nstdio transport]
        D[FastAPI REST\n:8000 /generate]
        E[DiagramGenerator]
    end

    F[Claude API\nclaude-3-5-sonnet]
    G[Excalidraw JSON]

    A -- MCP stdio --> C
    B -- HTTP POST --> D
    C --> E
    D --> E
    E -- Anthropic SDK --> F
    F -- diagram spec JSON --> E
    E --> G
```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/shaikn6/mcp-diagram-agent.git && cd mcp-diagram-agent

# 2. Set your API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# 3. Start with Docker
docker-compose up --build

# 4. Generate a diagram
curl -s -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"description": "Microservices app: API gateway, auth service, user service, PostgreSQL"}' \
  | python -m json.tool

# 5. Paste the "diagram" field contents into https://excalidraw.com/
```

---

## MCP Usage

Add this server to your MCP client (e.g. Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "diagram-agent": {
      "command": "python",
      "args": ["-m", "src.server", "--mcp"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

Then in Claude Desktop, use the `generate_diagram` tool:

```
Generate a diagram for: "Event-driven e-commerce platform with Kafka,
order service, inventory service, payment service, and Redis cache."
```

Claude will call `generate_diagram` and return Excalidraw JSON you can paste directly into [excalidraw.com](https://excalidraw.com/).

---

## REST API Usage

### `POST /generate`

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Three-tier web app: React SPA, Node.js REST API, MongoDB Atlas",
    "style": "technical",
    "max_elements": 20
  }'
```

**Response:**

```json
{
  "diagram": {
    "type": "excalidraw",
    "version": 2,
    "elements": [ ... ],
    "appState": { "viewBackgroundColor": "#ffffff" },
    "files": {}
  },
  "element_count": 9,
  "description_summary": "Three-tier web architecture with React frontend, Node.js API, and MongoDB.",
  "model_used": "claude-3-5-sonnet-20241022"
}
```

### `GET /health`

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0","service":"mcp-diagram-agent"}
```

Interactive docs are available at `http://localhost:8000/docs`.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | **Yes** | — | Your Anthropic API key |
| `CLAUDE_MODEL` | No | `claude-3-5-sonnet-20241022` | Claude model to use |
| `HOST` | No | `0.0.0.0` | Bind host for the REST server |
| `PORT` | No | `8000` | Bind port for the REST server |
| `LOG_LEVEL` | No | `info` | Logging level (`debug`, `info`, `warning`, `error`) |
| `RELOAD` | No | `false` | Enable hot-reload (development only) |
| `CORS_ORIGINS` | No | `*` | Comma-separated allowed CORS origins |

Copy `.env.example` to `.env` to get started.

---

## Local Development

```bash
# Install with dev extras
pip install -e ".[dev]"

# Run all tests
pytest

# Lint + format
ruff check src/ tests/ && ruff format src/ tests/

# Type check
mypy src/

# Run the API server with auto-reload
RELOAD=true python -m src.server
```

---

## Supported Diagram Elements

| Shape | Excalidraw type | Semantic layer |
|-------|----------------|----------------|
| Rectangle | `rectangle` | services, gateways, data stores |
| Ellipse | `ellipse` | clients, external systems |
| Diamond | `diamond` | decision points |
| Arrow | `arrow` | data flow, API calls |

Layer colors follow the [Catppuccin Mocha](https://github.com/catppuccin/catppuccin) palette for a cohesive look:

| Layer | Color |
|-------|-------|
| `client` | Sky blue |
| `gateway` | Red |
| `service` | Green |
| `data` | Peach |
| `queue` | Yellow |
| `external` | Mauve |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All contributions are welcome — bug reports, feature requests, and pull requests.

---

## Security

See [SECURITY.md](SECURITY.md) for the vulnerability disclosure policy.

---

## License

MIT — see [LICENSE](LICENSE).
