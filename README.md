# s-cli

A programmatic CLI to interact with [Superhuman](https://superhuman.com). Connects to Superhuman's Electron app via Chrome DevTools Protocol and calls its internal React APIs.

```
CLI / MCP Server / your code
        |
    core.py (CDP -> React fiber -> Superhuman internals)
        |
    Superhuman (Electron + SQLite)
```

## Quickstart

```bash
cd python
pip install -e .
s-cli --accounts
s-cli --to user@example.com --subject "Hello from CLI"
```

## CLI Usage

```bash
# Inject a draft
s-cli --to user@example.com --subject "Hello" --body "<p>Hi there</p>"

# Multiple recipients
s-cli --to a@x.com b@x.com --cc c@x.com --subject "Team sync"

# Body from stdin
echo "<p>piped content</p>" | s-cli --to user@example.com --subject "Piped"

# List drafts
s-cli --list

# List accounts
s-cli --accounts

# JSON output (for scripting)
s-cli --to user@example.com --subject "Hello" --json

# Specific account
s-cli --to user@example.com --subject "Hello" --account you@company.com
```

Auto-detects account when only one is logged in, or set `SCLI_ACCOUNT` env var.

## Claude Desktop (MCP)

Add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "s-cli": {
      "command": "python3",
      "args": ["-m", "scli.mcp_server"]
    }
  }
}
```

See `examples/claude_desktop_config.json` for a ready-to-use config.

This gives Claude tools for the full email lifecycle:

| Tool | Description |
|------|-------------|
| `superhuman_list_accounts` | List available accounts |
| `superhuman_inbox` | List inbox threads |
| `superhuman_list_threads` | List threads by label |
| `superhuman_search` | Search emails (Gmail syntax) |
| `superhuman_read_thread` | Read a thread's messages |
| `superhuman_list_drafts` | List drafts |
| `superhuman_read_draft` | Read a draft's content |
| `superhuman_inject_draft` | Create a new draft |
| `superhuman_update_draft` | Edit an existing draft |
| `superhuman_attach_file` | Attach a file to a draft |

## How It Works

Superhuman is an Electron app. When launched with `--remote-debugging-port=9222`, we can connect via CDP and execute JavaScript in the renderer. The tool:

1. Walks the React fiber tree to find the `Main` component
2. Extracts the `account` object (which holds the thread store, DI container, etc.)
3. Creates a `ThreadPresenter` via `getNewDraftPresenter()`
4. Calls `initializeDraft({subject, body, to, ...})` to build a `DraftModel`
5. Calls `saveDraft()` which persists via the modifier queue to SQLite

s-cli auto-launches Superhuman with the debug port if it's not already running.

## Draft bridge adapter

`sdraft.bridge` is a draft-only adapter for an external HTTP draft bridge (e.g.
the owner-gated Superhuman draft bridge on the Architect VM). It reads a bridge
JSON payload from a file, converts the markdown body to HTML, and injects a
**compose** draft via `scli.core.inject_draft`. It never sends and rejects any
send-shaped field.

```bash
sdraft-bridge draft --json-file /path/to/input.json --account you@company.com
# or: python3 -m sdraft.bridge draft --json-file input.json --account you@company.com
```

Input JSON (subset the bridge produces):

```json
{
  "to": ["recipient@example.com"],
  "cc": [], "bcc": [],
  "subject": "Follow-up",
  "body_markdown": "Hi ...",
  "reply_to": null
}
```

Success prints a single JSON object (`{draft_id, thread_id, subject, to}`) to
stdout; any failure prints a JSON error to stderr and exits non-zero. `reply_to`
is compose-only (v1) and must be null/absent.

## Project Structure

```
python/scli/
  core.py          # Stateless CDP functions — the engine
  cli.py           # CLI wrapper
  mcp_server.py    # MCP server for Claude Desktop
python/sdraft/
  bridge.py        # Draft-only adapter for an external HTTP draft bridge
typescript/        # SDK stub (contributions welcome)
examples/          # Usage examples + Claude Desktop config
```

## Disclaimer

This was reverse-engineered with Claude Code for research purposes and is meant for academic and non-commercial use only.

## Prior Art

- [edwinhu/superhuman-cli](https://github.com/edwinhu/superhuman-cli) — Full TypeScript CLI/MCP using Superhuman's backend API
- [Superhuman's official MCP server](https://help.superhuman.com/hc/en-us/articles/49810745762067) — Requires Business plan + Chrome web app
