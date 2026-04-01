#!/usr/bin/env python3
"""s-cli — Manage Superhuman email from the command line."""

import argparse
import json
import sys

from scli.core import (
    attach_file,
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


def main():
    parser = argparse.ArgumentParser(
        prog="s-cli",
        description="Manage Superhuman email client via CDP.",
    )
    # Draft creation
    parser.add_argument("--to", nargs="+", help="Recipient email(s) — creates a new draft")
    parser.add_argument("--cc", nargs="+", help="CC email(s)")
    parser.add_argument("--bcc", nargs="+", help="BCC email(s)")
    parser.add_argument("--subject", "-s", default="", help="Email subject")
    parser.add_argument("--body", "-b", help="Email body (HTML). Reads stdin if piped.")

    # Draft management
    parser.add_argument("--list", "-l", action="store_true", help="List drafts")
    parser.add_argument("--read", "-r", metavar="DRAFT_ID", help="Read a draft's full content")
    parser.add_argument("--edit", "-e", metavar="DRAFT_ID", help="Edit an existing draft")
    parser.add_argument("--attach", nargs=2, metavar=("DRAFT_ID", "FILE"), help="Attach a file to a draft")
    parser.add_argument("--reply", metavar="THREAD_ID", help="Reply-all in a thread (provide thread ID)")

    # Email reading
    parser.add_argument("--inbox", action="store_true", help="List inbox threads")
    parser.add_argument("--threads", metavar="LABEL", help="List threads for a label (INBOX, SENT, STARRED, etc.)")
    parser.add_argument("--search", metavar="QUERY", help="Search emails (Gmail search syntax)")
    parser.add_argument("--thread", metavar="THREAD_ID", help="Read a thread's messages")
    parser.add_argument("--limit", "-n", type=int, default=20, help="Max results (default: 20)")

    # General
    parser.add_argument("--accounts", action="store_true", help="List available accounts")
    parser.add_argument("--account", "-a", help="Superhuman account email")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output as JSON")
    parser.add_argument("--port", type=int, default=9222, help=argparse.SUPPRESS)

    args = parser.parse_args()

    try:
        if args.accounts:
            _cmd_accounts(args)
        elif args.inbox:
            _cmd_threads(args, "INBOX")
        elif args.threads:
            _cmd_threads(args, args.threads)
        elif args.search:
            _cmd_search(args)
        elif args.thread:
            _cmd_thread(args)
        elif args.list:
            _cmd_list(args)
        elif args.read:
            _cmd_read(args)
        elif args.edit:
            _cmd_edit(args)
        elif args.attach:
            _cmd_attach(args)
        elif args.reply:
            _cmd_reply(args)
        elif args.to:
            _cmd_inject(args)
        else:
            parser.print_help()
            sys.exit(1)
    except RuntimeError as e:
        if args.json_output:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_accounts(args):
    accounts = get_accounts(args.port)
    if args.json_output:
        print(json.dumps(accounts))
        return
    if not accounts:
        print("No accounts found.", file=sys.stderr)
        sys.exit(1)
    for a in accounts:
        print(f"  {a['email']}")


def _cmd_threads(args, label):
    threads = list_threads(label, limit=args.limit, account=args.account, port=args.port)
    if args.json_output:
        print(json.dumps(threads))
        return
    if not threads:
        print(f"No threads in {label}.")
        return
    for t in threads:
        unread = "*" if t.get("is_unread") else " "
        msgs = f"[{t.get('message_count', 0)}]"
        subj = t.get("subject") or "(no subject)"
        frm = t.get("from_name") or t.get("from") or ""
        snippet = t.get("snippet", "")[:60]
        print(f" {unread} {t['id']}  {msgs:<4} {frm[:20]:<20}  {subj[:40]}")
        if snippet:
            print(f"                                            {snippet}")


def _cmd_search(args):
    result = search(args.search, max_results=args.limit, account=args.account, port=args.port)
    threads = result.get("threads", [])
    if args.json_output:
        print(json.dumps(result))
        return
    est = result.get("result_size_estimate", "?")
    print(f"~{est} results:\n")
    for t in threads:
        subj = t.get("subject") or t.get("snippet", "")[:50] or "(no subject)"
        frm = t.get("from_name") or t.get("from") or ""
        msgs = f"[{t.get('message_count', 0)}]" if t.get("message_count") else ""
        print(f"  {t['id']}  {msgs:<4} {frm[:20]:<20}  {subj[:50]}")


def _cmd_thread(args):
    result = read_thread(args.thread, account=args.account, port=args.port)
    if args.json_output:
        print(json.dumps(result))
        return
    print(f"Thread: {result.get('subject') or '(no subject)'}")
    print(f"  ID: {result.get('id')}  Messages: {result.get('message_count', 0)}")
    print()
    for m in result.get("messages", []):
        frm = m.get("from_name") or m.get("from", "")
        to_str = ", ".join(m.get("to", []))
        date = m.get("date", "")[:19].replace("T", " ")
        print(f"  --- {frm} -> {to_str}  ({date}) ---")
        snippet = m.get("snippet", "")
        body = m.get("body", "")
        if body:
            print(f"  {body[:500]}")
        elif snippet:
            print(f"  {snippet}")
        atts = m.get("attachments", [])
        if atts:
            print(f"  Attachments: {', '.join(a.get('name', '?') for a in atts)}")
        print()


def _cmd_list(args):
    drafts = list_drafts(args.account, port=args.port)
    if args.json_output:
        print(json.dumps(drafts))
        return
    if not drafts:
        print("No drafts.")
        return
    for d in drafts:
        to_str = ", ".join(d.get("to", []))
        print(f"  {d['id']}  {d.get('subject') or '(no subject)'}  -> {to_str or '(none)'}")


def _cmd_read(args):
    result = read_draft(args.read, account=args.account, port=args.port)
    if args.json_output:
        print(json.dumps(result))
        return
    print(f"  ID:      {result.get('id')}")
    print(f"  Thread:  {result.get('thread_id')}")
    print(f"  Subject: {result.get('subject') or '(no subject)'}")
    to_str = ", ".join(c.get("email", "") for c in result.get("to", []))
    print(f"  To:      {to_str or '(none)'}")
    cc_str = ", ".join(c.get("email", "") for c in result.get("cc", []))
    if cc_str:
        print(f"  CC:      {cc_str}")
    if result.get("from"):
        print(f"  From:    {result['from'].get('email', '')}")
    attachments = result.get("attachments", [])
    if attachments:
        print(f"  Attach:  {len(attachments)} file(s)")
        for att in attachments:
            print(f"           - {att.get('name')} ({att.get('type')})")
    body = result.get("body", "")
    if body:
        print(f"  Body:\n{body}")


def _cmd_edit(args):
    body = args.body
    if body is None and not sys.stdin.isatty():
        body = sys.stdin.read()

    result = update_draft(
        args.edit,
        subject=args.subject if args.subject else None,
        body=body,
        to=args.to,
        cc=args.cc,
        bcc=args.bcc,
        account=args.account,
        port=args.port,
    )

    if args.json_output:
        print(json.dumps(result))
        return

    print(f"Draft updated: {result.get('draft_id')}")
    print(f"  Subject: {result.get('subject')}")
    print(f"  To:      {', '.join(result.get('to', []))}")


def _cmd_inject(args):
    body = args.body
    if body is None and not sys.stdin.isatty():
        body = sys.stdin.read()

    result = inject_draft(
        args.account,
        to=args.to,
        subject=args.subject,
        body=body or "",
        cc=args.cc,
        bcc=args.bcc,
        port=args.port,
    )

    if args.json_output:
        print(json.dumps(result))
        return

    print(f"Draft created: {result.get('draft_id')}")
    print(f"  Subject: {result.get('subject')}")
    print(f"  To:      {', '.join(result.get('to', []))}")


def _cmd_reply(args):
    body = args.body
    if body is None and not sys.stdin.isatty():
        body = sys.stdin.read()
    result = reply_to_thread(
        args.reply, body=body or "", account=args.account, port=args.port,
    )
    if args.json_output:
        print(json.dumps(result))
        return
    print(f"Reply draft created: {result.get('draft_id')}")
    print(f"  Thread:  {result.get('thread_id')}")
    print(f"  Subject: {result.get('subject')}")
    print(f"  To:      {', '.join(result.get('to', []))}")
    cc = result.get('cc', [])
    if cc:
        print(f"  CC:      {', '.join(cc)}")


def _cmd_attach(args):
    draft_id, file_path = args.attach
    result = attach_file(draft_id, file_path, account=args.account, port=args.port)

    if args.json_output:
        print(json.dumps(result))
        return

    print(f"Attached to {result.get('draft_id')}: {result.get('attached')} ({result.get('size', 0)} bytes)")


if __name__ == "__main__":
    main()
