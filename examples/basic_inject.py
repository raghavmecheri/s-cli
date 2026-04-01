#!/usr/bin/env python3
"""Basic example: inject a single draft into Superhuman."""

from scli import inject_draft

result = inject_draft(
    to=["colleague@company.com"],
    subject="Quick question",
    body="<p>Hey, do you have 5 minutes to chat today?</p>",
)

print(f"Created draft {result['draft_id']}: {result['subject']}")
