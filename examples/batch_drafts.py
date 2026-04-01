#!/usr/bin/env python3
"""Batch example: inject multiple drafts from a list."""

from scli import inject_draft

drafts = [
    {"to": ["alice@example.com"], "subject": "Follow up", "body": "<p>Following up on our conversation.</p>"},
    {"to": ["bob@example.com"], "subject": "Meeting notes", "body": "<p>Here are the notes from today.</p>"},
    {"to": ["carol@example.com"], "subject": "Introduction", "body": "<p>I'd like to introduce you to the team.</p>"},
]

for d in drafts:
    result = inject_draft(**d)
    print(f"  {result['draft_id']}  {result['subject']}  -> {', '.join(result['to'])}")
