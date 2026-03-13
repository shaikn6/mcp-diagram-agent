# Changelog

All notable changes to this project are documented here.

## [1.0.0] - 2026-06-16

### Added
- MCP server exposing a single tool that converts free-text system descriptions into Excalidraw diagrams
- Claude AI backend interpreting architecture descriptions and generating production-ready diagram JSON
- Support for common diagram types: microservices, data pipelines, network topology, and entity-relationship
- Excalidraw export with proper node positioning, edge routing, and label placement
- Claude Desktop integration via MCP config with zero-dependency local installation
- Batch mode for generating diagram sets from structured architecture documentation files

### Changed
- Production-ready CI/CD with 95%+ test coverage enforcement

### Security
- System descriptions processed locally via Claude API; no diagram content is stored or logged server-side
