# s-cli — AI Agent Instructions

## What This Is

A programmatic CLI (`s-cli`) to interact with the Superhuman email client. Works by connecting to Superhuman's Electron app via Chrome DevTools Protocol (CDP) and calling its internal React APIs. The Python package is `scli`.

## How It Works

1. Superhuman runs as an Electron app with `--remote-debugging-port=9222`
2. We connect via CDP WebSocket to the `mail.superhuman.com` renderer page
3. Walk the React fiber tree from `#superhuman` to find the `Main` component
4. Store the `account` object on `window.__scli_account` (from `Main.memoizedProps.account`)
5. Call `account.threads.getNewDraftPresenter(mockOp)` with a mock operation context
6. Call `presenter.initializeDraft({subject, body, to, ...})` to create a `DraftModel`
7. Call `presenter.saveDraft(draft)` which enqueues a modifier (persists to SQLite)

The mock operation context is: `{watching: true, uniqueCallback: () => {}, onUnwatch: () => {}}`

Account resolution priority: explicit `--account` arg > `SCLI_ACCOUNT` env var > auto-detect (when only one account logged in).

## Architecture

```
python/scli/
  core.py       — Stateless functions: ensure_connection, inject_draft, list_drafts, get_accounts, search, etc.
  cli.py        — Flat CLI wrapping core.py
  mcp_server.py — MCP server wrapping core.py (for Claude Desktop)
python/sdraft/  — Backward-compatible alias (re-exports from scli)
```

**Core rule**: `core.py` functions are stateless. Each call connects, operates, disconnects. No persistent connections or background processes.

## Working on This Codebase

### Prerequisites
- Superhuman desktop app installed
- Python 3.10+
- `pip install -e python/` to install in dev mode (provides `s-cli` command)

### Testing
```bash
s-cli --accounts                    # verify CDP connection
s-cli --to test@example.com -s "Test"  # inject a draft
s-cli --list                        # verify it appears
```

### Known Fragility
- The React fiber walk looks for a component named `Main` with an `account` prop. If Superhuman renames this component, the walk breaks. Fix by updating `_JS_FIND_MAIN` in `scli/core.py`.
- The `getNewDraftPresenter` and `initializeDraft` APIs are internal to Superhuman and may change across versions.
- CDP requires Superhuman launched with `--remote-debugging-port=9222 --remote-allow-origins=*`. The `ensure_connection()` function in `scli/core.py` handles auto-launching.

### Adding New Operations
1. Add JS payload as a module-level constant in `scli/core.py` (see `_JS_INJECT_DRAFT` for pattern)
2. Add a public function in `scli/core.py` that calls `_cdp_eval` with the payload
3. Export it from `scli/__init__.py`
4. Add CLI flag in `scli/cli.py`
5. Add MCP tool in `scli/mcp_server.py`
6. Add example in `examples/`

### Style
- Python: PEP 8, ruff-compatible
- No unnecessary abstractions — three similar lines > one premature helper
- JS payloads are strings with `{placeholder}` for `.format()` — escape literal braces as `{{`
