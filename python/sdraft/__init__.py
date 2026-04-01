"""sdraft — backward-compatible alias for scli."""

from scli.core import (
    attach_file,
    ensure_connection,
    get_accounts,
    inject_draft,
    list_drafts,
    list_threads,
    read_draft,
    read_thread,
    search,
    update_draft,
)

__all__ = [
    "attach_file",
    "ensure_connection",
    "get_accounts",
    "inject_draft",
    "list_drafts",
    "list_threads",
    "read_draft",
    "read_thread",
    "search",
    "update_draft",
]
