# LearnGraph for Cursor

This plugin connects Cursor to the production LearnGraph MCP door:

`https://app.learngraph.org/service-mcp/v1/public/mcp`

It is a local bridge. Cursor starts `bridge.py`, and that process forwards MCP to
the public door. The access token comes from the
[learngraph CLI](https://github.com/learngraph/learngraph-cli). The bridge does
not refresh the Keycloak grant itself.

## Install

1. Install the CLI and log in for production:

```bash
learngraph --environment prod auth login
```

2. Copy this directory to `~/.cursor/plugins/local/learngraph`. Copy the files.
   A symlink whose target sits outside that folder is ignored.
3. Reload the window.

`learngraph auth token` must be on `PATH`. That command prints the current
access token and refreshes it when needed.

## Another server

Set `LEARNGRAPH_MCP_URL` to that server's public MCP URL before starting
Cursor. The bridge then runs `learngraph auth token` with the CLI login you
already have, and that login must be the user for that server. Do not point
the URL at `/service-mcp/v1/mcp`.

## License

CC-BY-NC-4.0
