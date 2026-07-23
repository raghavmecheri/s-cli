#!/usr/bin/env python3
"""sdraft.bridge — draft-only adapter for the Superhuman draft HTTP bridge.

Reads the draft-bridge JSON schema from a file and injects a *compose* draft
into Superhuman via :func:`scli.core.inject_draft`. This is the entry the Mac
HTTP bridge (``superhuman_draft_bridge.py``) invokes with a fixed argv, e.g.::

    python3 -m sdraft.bridge draft --json-file <tempfile> --account raghav@binit.ai

It is deliberately draft-only: there is no send path, and any send-shaped field
is rejected. Success prints a single JSON object to stdout; any failure prints a
JSON error to stderr and exits non-zero so the bridge records a not-created
result.

Input schema (produced by the bridge):

    {
      "idempotency_key": "...",   # ignored here; the bridge owns idempotency
      "to":  ["a@x.com"],
      "cc":  [],
      "bcc": [],
      "subject": "...",
      "body_markdown": "...",
      "reply_to": null              # compose-only in v1; must be null/absent
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, NoReturn

from scli.core import inject_draft

MAX_BODY_BYTES = 256 * 1024
MAX_RECIPIENTS = 100
# Fields that would imply sending; rejected so this path can only ever draft.
FORBIDDEN_FIELDS = ("send", "send_at", "schedule", "scheduled_send", "sent")


def _fail(message: str) -> NoReturn:
    print(json.dumps({"error": message}), file=sys.stderr)
    raise SystemExit(4)


def _markdown_to_html(text: str) -> str:
    """Convert markdown to HTML for Superhuman's HTML body.

    Uses the ``markdown`` package when available; otherwise falls back to an
    escaped paragraph/line-break wrap. Text that already looks like HTML is
    passed through untouched.
    """
    if not text:
        return ""
    if text.lstrip().startswith("<"):
        return text
    try:
        import markdown as _md

        return _md.markdown(text, extensions=["extra", "nl2br"])
    except Exception:
        import html

        parts = []
        for para in text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            parts.append("<p>{}</p>".format(html.escape(para).replace("\n", "<br>\n")))
        return "\n".join(parts)


def _emails(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(e, str) and "@" in e for e in value):
        _fail(f"{field} must be a list of email strings")
    if len(value) > MAX_RECIPIENTS:
        _fail(f"too many recipients in {field}")
    return value


def _load_draft(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"cannot read draft json: {exc}")
    if not isinstance(data, dict):
        _fail("draft json must be an object")
    return data


def _cmd_draft(args: argparse.Namespace) -> int:
    data = _load_draft(args.json_file)

    for field in FORBIDDEN_FIELDS:
        if field in data:
            _fail(f"forbidden field: {field}")
    if data.get("reply_to"):
        _fail("reply_to is not supported (compose-only)")

    to = _emails(data.get("to"), "to")
    if not to:
        _fail("at least one 'to' recipient is required")
    cc = _emails(data.get("cc"), "cc")
    bcc = _emails(data.get("bcc"), "bcc")

    subject = data.get("subject", "")
    if not isinstance(subject, str):
        _fail("subject must be a string")

    body_md = data.get("body_markdown", "")
    if not isinstance(body_md, str):
        _fail("body_markdown must be a string")
    if len(body_md.encode("utf-8")) > MAX_BODY_BYTES:
        _fail("body exceeds size limit")
    body_html = _markdown_to_html(body_md)

    try:
        result = inject_draft(
            args.account,
            to=to,
            subject=subject,
            body=body_html,
            cc=cc,
            bcc=bcc,
        )
    except Exception as exc:  # CDP unreachable, account mismatch, inject failure
        _fail(f"draft injection failed: {exc}")

    print(json.dumps(result))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sdraft.bridge", description="Draft-only bridge adapter for Superhuman.")
    sub = parser.add_subparsers(dest="mode", required=True)
    draft = sub.add_parser("draft", help="Create a compose draft from a bridge JSON file")
    draft.add_argument("--json-file", required=True, help="Path to the bridge draft JSON")
    draft.add_argument("--account", "-a", default=None, help="Superhuman account email")
    # Accepted for argv compatibility; output is always JSON.
    draft.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    draft.set_defaults(func=_cmd_draft)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
