# Changelog

All notable changes to this project are documented here.

## [1.0.0] - 2026-06-16

(Entry corrected on 2026-11-16: the original wording claimed diagram-type support, edge routing, label placement and
"no logging" that the code does not provide. See the README's Limitations section.)

### Added
- MCP server (stdio) exposing a single tool, `generate_diagram`, that converts a free-text system description into an
  Excalidraw diagram, plus a REST API (`POST /generate`) over the same generator
- One Anthropic Messages API call per request that returns a node/edge spec; layout, colors and Excalidraw
  serialization are deterministic local code
- Column-by-layer layout and straight arrows between node edges (no edge routing; arrows are not bound to nodes, and
  labels may need re-typing after import)
- Claude Desktop integration via MCP config

### Changed
- CI runs lint, mypy, tests with a 95% coverage gate, and a Docker build

### Security
- The description is sent to the Anthropic API for every request. The service stores nothing, but the REST server logs
  the first 80 characters of each description at INFO level
