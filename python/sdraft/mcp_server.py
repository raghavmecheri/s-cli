"""sdraft MCP server — backward-compatible alias for scli.mcp_server."""

from scli.mcp_server import main, mcp  # noqa: F401

if __name__ == "__main__":
    main()
