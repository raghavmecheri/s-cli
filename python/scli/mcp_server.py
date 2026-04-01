"""scli MCP server — exposes Superhuman email operations as tools for Claude Desktop."""

from mcp.server.fastmcp import FastMCP

from scli.core import (
    attach_file,
    delete_draft,
    get_accounts,
    inject_draft,
    list_drafts,
    list_threads,
    read_draft,
    read_thread,
    reply_to_thread,
    search,
    update_draft,
)

mcp = FastMCP("s-cli")


# --- Account ---


@mcp.tool()
def superhuman_list_accounts() -> list[dict]:
    """List available Superhuman email accounts."""
    return get_accounts()


# --- Email reading ---


@mcp.tool()
def superhuman_inbox(limit: int = 20, account: str | None = None) -> list[dict]:
    """List inbox threads with subject, sender, snippet, and unread status.

    Args:
        limit: Max threads to return (default 20).
        account: Email account (auto-detects if omitted).
    """
    return list_threads("INBOX", limit=limit, account=account)


@mcp.tool()
def superhuman_list_threads(label: str, limit: int = 20, account: str | None = None) -> list[dict]:
    """List threads for a Gmail label (INBOX, SENT, STARRED, IMPORTANT, SPAM, TRASH, or custom).

    Args:
        label: Gmail label name.
        limit: Max threads to return.
        account: Email account (auto-detects if omitted).
    """
    return list_threads(label, limit=limit, account=account)


@mcp.tool()
def superhuman_search(query: str, max_results: int = 20, account: str | None = None) -> dict:
    """Search emails using Gmail search syntax.

    Supports: from:, to:, subject:, is:unread, has:attachment, after:, before:, and more.

    Args:
        query: Search query (same syntax as Gmail/Superhuman search bar).
        max_results: Max results to return.
        account: Email account (auto-detects if omitted).
    """
    return search(query, max_results=max_results, account=account)


@mcp.tool()
def superhuman_read_thread(thread_id: str, account: str | None = None) -> dict:
    """Read a thread's full content — all messages with sender, recipients, body, and attachments.

    Args:
        thread_id: The thread ID (from inbox, search, or list results).
        account: Email account (auto-detects if omitted).
    """
    return read_thread(thread_id, account=account)


# --- Drafts ---


@mcp.tool()
def superhuman_list_drafts(account: str | None = None) -> list[dict]:
    """List all drafts for a Superhuman account.

    Args:
        account: Email account (auto-detects if omitted).
    """
    return list_drafts(account)


@mcp.tool()
def superhuman_read_draft(draft_id: str, account: str | None = None) -> dict:
    """Read a draft's full content including body, recipients, and attachments.

    Args:
        draft_id: The draft ID.
        account: Email account (auto-detects if omitted).
    """
    return read_draft(draft_id, account=account)


@mcp.tool()
def superhuman_inject_draft(
    to: list[str],
    subject: str = "",
    body: str = "",
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    account: str | None = None,
) -> dict:
    """Create a new draft in Superhuman that appears in the Drafts folder.

    Args:
        to: Recipient email addresses.
        subject: Email subject line.
        body: Email body (HTML supported).
        cc: CC email addresses.
        bcc: BCC email addresses.
        account: Superhuman account email (auto-detects if omitted).
    """
    return inject_draft(account, to=to, subject=subject, body=body, cc=cc, bcc=bcc)


@mcp.tool()
def superhuman_reply_thread(
    thread_id: str,
    body: str = "",
    account: str | None = None,
) -> dict:
    """Reply-all to an existing email thread in Superhuman.

    Creates a reply-all draft in the thread, auto-populating To and CC
    from the thread context.

    Args:
        thread_id: The thread ID to reply to.
        body: Reply body (HTML supported).
        account: Superhuman account email (auto-detects if omitted).
    """
    return reply_to_thread(thread_id, body=body, account=account)


@mcp.tool()
def superhuman_update_draft(
    draft_id: str,
    subject: str | None = None,
    body: str | None = None,
    to: list[str] | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    account: str | None = None,
) -> dict:
    """Update fields on an existing draft without sending it.

    Args:
        draft_id: The draft ID to update.
        subject: New subject line.
        body: New body (HTML supported).
        to: New recipient email addresses.
        cc: New CC email addresses.
        bcc: New BCC email addresses.
        account: Superhuman account email (auto-detects if omitted).
    """
    return update_draft(draft_id, subject=subject, body=body, to=to, cc=cc, bcc=bcc, account=account)


@mcp.tool()
def superhuman_delete_draft(draft_id: str, account: str | None = None) -> dict:
    """Delete a draft from Superhuman.

    Args:
        draft_id: The draft ID to delete.
        account: Superhuman account email (auto-detects if omitted).
    """
    return delete_draft(draft_id, account=account)


@mcp.tool()
def superhuman_attach_file(draft_id: str, file_path: str, account: str | None = None) -> dict:
    """Attach a file (PDF, image, etc.) to an existing draft.

    Args:
        draft_id: The draft ID to attach to.
        file_path: Absolute path to the file on disk.
        account: Superhuman account email (auto-detects if omitted).
    """
    return attach_file(draft_id, file_path, account=account)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
