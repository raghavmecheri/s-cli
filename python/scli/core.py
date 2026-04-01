"""
scli.core — Stateless functions for injecting drafts into Superhuman via CDP.

Every function connects, does one thing, and disconnects. No persistent state.

Requires Superhuman running with:
    --remote-debugging-port=9222 --remote-allow-origins=*
"""

import base64
import http.client
import json
import os
import subprocess
import time

import websocket

CDP_PORT = 9222

# ---------------------------------------------------------------------------
# JS payloads — injected into the Superhuman renderer via CDP Runtime.evaluate
# ---------------------------------------------------------------------------

_JS_FIND_MAIN = """\
(() => {
    const el = document.getElementById('superhuman');
    if (!el) return { error: 'No #superhuman element' };
    const key = Object.keys(el).find(k => k.startsWith('__reactContainer'));
    if (!key) return { error: 'No React container' };
    let fiber = el[key];
    const seen = new Set();
    function walk(f, depth) {
        if (!f || depth > 60 || seen.has(f)) return null;
        seen.add(f);
        const name = f.type?.displayName || f.type?.name || '';
        if (name === 'Main' && f.memoizedProps?.account) return f;
        return walk(f.child, depth + 1) || walk(f.sibling, depth);
    }
    const main = walk(fiber, 0);
    if (!main) return { error: 'Main component not found in React tree' };
    window.__scli_account = main.memoizedProps.account;
    return { ok: true };
})()
"""

_JS_LIST_DRAFTS = """\
(() => {
    try {
        const account = window.__scli_account;
        if (!account) return { error: 'No account. Run find_main first.' };
        const tree = account.di.get('viewState').tree;
        const drafts = tree.get('drafts') || {};
        return { drafts: Object.keys(drafts).map(id => {
            const d = drafts[id]?.draft;
            if (!d) return null;
            return {
                id,
                subject: (typeof d.getSubject === 'function' ? d.getSubject() : d.subject) || '',
                to: (typeof d.getTo === 'function' ? d.getTo() : d.to || []).map(c => c.email || c),
                action: typeof d.getAction === 'function' ? d.getAction() : d.action,
            };
        }).filter(Boolean) };
    } catch(e) {
        return { error: e.message };
    }
})()
"""

_JS_LIST_THREADS = """\
(async () => {{
    try {{
        const account = window.__scli_account;
        if (!account) return {{ error: 'No account. Run find_main first.' }};
        const disk = account.di.get('disk');
        const label = '{label}';
        const limit = {limit};
        const result = await disk.thread.listAsync(label, {{ limit }});
        const threads = result.threads || [];
        return {{ threads: threads.map(t => {{
            const lastMsg = t.messages?.[t.messages.length - 1];
            const firstMsg = t.messages?.[0];
            return {{
                id: t.id,
                subject: t.subject || '',
                snippet: lastMsg?.snippet || '',
                from: firstMsg?.from?.email || '',
                from_name: firstMsg?.from?.name || '',
                date: lastMsg?.date?.toISOString?.() || '',
                message_count: t.messages?.length || 0,
                labels: t.labelIds || [],
                is_unread: (t.labelIds || []).includes('UNREAD'),
            }};
        }}) }};
    }} catch(e) {{
        return {{ error: e.message }};
    }}
}})()
"""

# Template — caller must .format(query=..., max_results=...)
_JS_SEARCH = """\
(async () => {{
    try {{
        const account = window.__scli_account;
        if (!account) return {{ error: 'No account. Run find_main first.' }};
        const gmail = account.di.get('gmail');
        const disk = account.di.get('disk');
        const result = await gmail.getThreadList({{ q: '{query}', maxResults: {max_results} }});
        const threadStubs = result.threads || [];

        // For each thread ID, try to get details from local disk first
        const threads = [];
        for (const stub of threadStubs) {{
            try {{
                const t = await disk.thread.get(stub.id);
                if (t) {{
                    const lastMsg = t.messages?.[t.messages.length - 1];
                    const firstMsg = t.messages?.[0];
                    threads.push({{
                        id: t.id,
                        subject: t.subject || '',
                        snippet: lastMsg?.snippet || stub.snippet || '',
                        from: firstMsg?.from?.email || '',
                        from_name: firstMsg?.from?.name || '',
                        date: lastMsg?.date?.toISOString?.() || '',
                        message_count: t.messages?.length || 0,
                        labels: t.labelIds || [],
                        is_unread: (t.labelIds || []).includes('UNREAD'),
                    }});
                    continue;
                }}
            }} catch(e) {{}}
            // Fallback to stub data from Gmail API
            threads.push({{ id: stub.id, snippet: stub.snippet || '', subject: '', from: '', from_name: '', date: '', message_count: 0, labels: [], is_unread: false }});
        }}
        return {{ threads, result_size_estimate: result.resultSizeEstimate, next_page_token: result.nextPageToken || null }};
    }} catch(e) {{
        return {{ error: e.message }};
    }}
}})()
"""

# Template — caller must .format(thread_id=...)
_JS_READ_THREAD = """\
(async () => {{
    try {{
        const account = window.__scli_account;
        if (!account) return {{ error: 'No account. Run find_main first.' }};
        const disk = account.di.get('disk');
        const t = await disk.thread.get('{thread_id}');
        if (!t) return {{ error: 'Thread not found: {thread_id}' }};
        return {{
            id: t.id,
            subject: t.subject || '',
            message_count: t.messages?.length || 0,
            labels: t.labelIds || [],
            messages: (t.messages || []).map(m => ({{
                id: m.id,
                from: m.from?.email || '',
                from_name: m.from?.name || '',
                to: (m.to || []).map(c => c.email),
                cc: (m.cc || []).map(c => c.email),
                date: m.date?.toISOString?.() || '',
                subject: m.subject || '',
                snippet: m.snippet || '',
                body: (m.body || '').substring(0, 50000),
                attachments: (m.nonInlineAttachments || []).map(a => ({{ name: a.name, type: a.type, size: a.size }})),
                labels: m.labelIds || [],
            }})),
        }};
    }} catch(e) {{
        return {{ error: e.message }};
    }}
}})()
"""

_JS_READ_DRAFT = """\
(() => {{
    try {{
        const account = window.__scli_account;
        if (!account) return {{ error: 'No account. Run find_main first.' }};
        const tree = account.di.get('viewState').tree;
        const drafts = tree.get('drafts') || {{}};
        const draftId = '{draft_id}';
        const entry = drafts[draftId];
        if (!entry?.draft) return {{ error: 'Draft not found: ' + draftId }};
        const d = entry.draft;
        return {{
            id: d.id,
            thread_id: d.threadId,
            subject: typeof d.getSubject === 'function' ? d.getSubject() : d.subject || '',
            body: typeof d.getBody === 'function' ? d.getBody() : d.body || '',
            to: (typeof d.getTo === 'function' ? d.getTo() : d.to || []).map(c => ({{ email: c.email, name: c.name }})),
            cc: (typeof d.getCc === 'function' ? d.getCc() : d.cc || []).map(c => ({{ email: c.email, name: c.name }})),
            bcc: (typeof d.getBcc === 'function' ? d.getBcc() : d.bcc || []).map(c => ({{ email: c.email, name: c.name }})),
            from: d.from ? {{ email: d.from.email, name: d.from.name }} : null,
            action: typeof d.getAction === 'function' ? d.getAction() : d.action,
            quoted_content: typeof d.getQuotedContent === 'function' ? d.getQuotedContent() : d.attributes?.quotedContent || '',
            attachments: (typeof d.getAttachments === 'function' ? d.getAttachments() : d._attachments || []).map(a => ({{ name: a.name, type: a.type, size: a.size, uuid: a.uuid }})),
            dirty: d.dirty,
        }};
    }} catch(e) {{
        return {{ error: e.message }};
    }}
}})()
"""

# Template — caller must .format(draft_id=..., updates_json=...) before eval
_JS_UPDATE_DRAFT = """\
(async () => {{
    try {{
        const account = window.__scli_account;
        if (!account) return {{ error: 'No account. Run find_main first.' }};
        const tree = account.di.get('viewState').tree;
        const threads = account.threads;
        const drafts = tree.get('drafts') || {{}};
        const draftId = '{draft_id}';
        const entry = drafts[draftId];
        if (!entry?.draft) return {{ error: 'Draft not found: ' + draftId }};
        const d = entry.draft;
        if (typeof d.set !== 'function') return {{ error: 'Draft has no set() method' }};

        const updates = {updates_json};

        // Convert email strings to contact objects for to/cc/bcc/from
        const toContact = (e) => ({{ email: e.email || e, raw: (e.name || e.email || e) + ' <' + (e.email || e) + '>', name: e.name || (e.email || e).split('@')[0].replace('.', ' '), rawName: e.name || '' }});
        if (updates.to) updates.to = updates.to.map(toContact);
        if (updates.cc) updates.cc = updates.cc.map(toContact);
        if (updates.bcc) updates.bcc = updates.bcc.map(toContact);
        if (updates.from) updates.from = toContact(updates.from);

        d.set(updates);

        // Save via presenter
        const mockOp = {{ watching: true, uniqueCallback: () => {{}}, onUnwatch: () => {{}} }};
        const presenter = threads.getPresenter(mockOp, d.threadId);
        await presenter.saveDraft(d, {{ saveAttachments: true, updateOutputs: true }});

        return {{
            draft_id: d.id,
            thread_id: d.threadId,
            subject: typeof d.getSubject === 'function' ? d.getSubject() : d.subject,
            to: (typeof d.getTo === 'function' ? d.getTo() : d.to || []).map(c => c.email || c),
            dirty: d.dirty,
        }};
    }} catch(e) {{
        return {{ error: e.message }};
    }}
}})()
"""

# Template — caller must .format(draft_id=..., file_name=..., file_type=..., file_b64=...)
_JS_ATTACH_FILE = """\
(async () => {{
    try {{
        const account = window.__scli_account;
        if (!account) return {{ error: 'No account. Run find_main first.' }};
        const tree = account.di.get('viewState').tree;
        const threads = account.threads;
        const drafts = tree.get('drafts') || {{}};
        const draftId = '{draft_id}';
        const entry = drafts[draftId];
        if (!entry?.draft) return {{ error: 'Draft not found: ' + draftId }};
        const d = entry.draft;

        // Decode base64 file data into a File object
        const b64 = '{file_b64}';
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const blob = new Blob([bytes], {{ type: '{file_type}' }});
        const file = new File([blob], '{file_name}', {{ type: '{file_type}' }});

        // Find the AttachmentModel constructor from any existing draft's attachments
        let AttachmentModelCtor = null;
        for (const id of Object.keys(drafts)) {{
            const att = drafts[id]?.draft?._attachments;
            if (att?.length > 0) {{ AttachmentModelCtor = att[0].constructor; break; }}
        }}

        const uuid = crypto.randomUUID();
        const attachmentRaw = {{
            uuid, messageId: d.id, threadId: d.threadId,
            cid: crypto.randomUUID(),
            name: '{file_name}', type: '{file_type}', size: file.size,
            inline: false, discardedAt: null, createdAt: Date.now(),
            fixedPartId: '0',
            source: {{ type: 'upload-firebase', threadId: d.threadId, messageId: d.id, uuid }}
        }};

        // Store file blob in the attachment uploads CacheStorage
        const emailAddr = d.from?.email || account.credential?.emailAddress;
        const cacheName = emailAddr + ':attachmentUploads:1';
        const cache = await caches.open(cacheName);
        const path = d.threadId + '/' + d.id + '/' + uuid;
        await cache.put(new Request('/' + path), new Response(blob));

        // Create proper AttachmentModel if constructor found, else use raw object
        let attachment;
        if (AttachmentModelCtor) {{
            attachment = new AttachmentModelCtor(attachmentRaw);
        }} else {{
            attachment = attachmentRaw;
            attachment.metadataJson = () => attachmentRaw;
            attachment.getSource = () => attachmentRaw.source;
        }}

        // Push to draft's _attachments and attributes.attachments
        if (!d._attachments) d._attachments = [];
        d._attachments.push(attachment);
        if (!d.attributes.attachments) d.attributes.attachments = [];
        d.attributes.attachments.push(attachmentRaw);
        d.dirty = true;

        // Save via presenter with saveAttachments flag
        const mockOp = {{ watching: true, uniqueCallback: () => {{}}, onUnwatch: () => {{}} }};
        const presenter = threads.getPresenter(mockOp, d.threadId);
        await presenter.saveDraft(d, {{ saveAttachments: true, updateOutputs: true }});

        return {{
            draft_id: d.id, attached: '{file_name}',
            uuid, size: file.size,
            used_attachment_model: !!AttachmentModelCtor,
        }};
    }} catch(e) {{
        return {{ error: e.message }};
    }}
}})()
"""

# Template — caller must .format(fields_json=...) before eval
_JS_INJECT_DRAFT = """\
(async () => {{
    try {{
        const account = window.__scli_account;
        if (!account) return {{ error: 'No account. Run find_main first.' }};
        const threads = account.threads;
        const mockOp = {{ watching: true, uniqueCallback: () => {{}}, onUnwatch: () => {{}} }};
        const presenter = threads.getNewDraftPresenter(mockOp);
        const fields = {fields_json};
        const draft = presenter.initializeDraft(fields, {{ saveAttachments: true }});
        await presenter.saveDraft(draft, {{ saveAttachments: true, updateOutputs: true }});
        return {{
            draft_id: draft.id,
            thread_id: draft.threadId,
            subject: typeof draft.getSubject === 'function' ? draft.getSubject() : draft.subject,
            to: (typeof draft.getTo === 'function' ? draft.getTo() : draft.to || []).map(c => c.email || c),
        }};
    }} catch(e) {{
        return {{ error: e.message }};
    }}
}})()
"""

# ---------------------------------------------------------------------------
# CDP helpers
# ---------------------------------------------------------------------------


def _cdp_targets(port=CDP_PORT):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    conn.request("GET", "/json/list")
    return json.loads(conn.getresponse().read())


def _cdp_eval(ws_url, expression, await_promise=True):
    ws = websocket.create_connection(ws_url, timeout=15)
    ws.send(
        json.dumps(
            {
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expression,
                    "awaitPromise": await_promise,
                    "returnByValue": True,
                },
            }
        )
    )
    while True:
        result = json.loads(ws.recv())
        if result.get("id") == 1:
            ws.close()
            val = result.get("result", {}).get("result", {}).get("value")
            if isinstance(val, dict) and "error" in val:
                raise RuntimeError(val["error"])
            return val


def _find_account_target(targets, email):
    for t in targets:
        if t.get("type") == "page" and t.get("url", "").startswith(f"https://mail.superhuman.com/{email}"):
            return t
    return None


def _parse_accounts(targets):
    accounts = []
    for t in targets:
        url = t.get("url", "")
        if t.get("type") == "page" and url.startswith("https://mail.superhuman.com/") and "@" in url:
            email = url.split("https://mail.superhuman.com/")[1].split("?")[0].split("/")[0]
            if "@" in email:
                accounts.append(
                    {
                        "email": email,
                        "title": t.get("title", ""),
                        "ws_url": t["webSocketDebuggerUrl"],
                    }
                )
    return accounts


def _build_recipients(emails):
    out = []
    for email in emails:
        name = email.split("@")[0].replace(".", " ").title()
        out.append({"email": email, "raw": f"{name} <{email}>", "name": name, "rawName": name})
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ensure_connection(port=CDP_PORT):
    """Connect to Superhuman's CDP. Auto-launch with debug flags if needed.

    Returns the list of CDP targets.
    """
    # Try existing connection
    try:
        return _cdp_targets(port)
    except (ConnectionRefusedError, OSError):
        pass

    # Check if Superhuman is running without CDP
    running = subprocess.run(["pgrep", "-f", "Superhuman"], capture_output=True).returncode == 0

    if running:
        # Kill and relaunch with CDP
        subprocess.run(["pkill", "-f", "Superhuman"], capture_output=True)
        time.sleep(2)

    # Launch with CDP flags
    subprocess.Popen(
        [
            "open",
            "-a",
            "Superhuman",
            "--args",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for CDP to become available
    for _ in range(20):
        time.sleep(0.5)
        try:
            targets = _cdp_targets(port)
            # Wait for at least one mail page to load
            if any("mail.superhuman.com" in t.get("url", "") and "@" in t.get("url", "") for t in targets):
                return targets
        except (ConnectionRefusedError, OSError):
            pass

    raise RuntimeError(f"Superhuman did not start with CDP on port {port} within 10 seconds.")


def get_accounts(port=CDP_PORT):
    """List available Superhuman accounts.

    Returns list of dicts: [{email, title, ws_url}, ...]
    """
    targets = ensure_connection(port)
    return _parse_accounts(targets)


def resolve_account(account=None, port=CDP_PORT):
    """Resolve which account to use.

    Priority: explicit arg > SCLI_ACCOUNT env > auto-detect single account.
    Returns (email, ws_url) tuple.
    """
    account = account or os.environ.get("SCLI_ACCOUNT")
    targets = ensure_connection(port)
    accounts = _parse_accounts(targets)

    if not accounts:
        raise RuntimeError("No Superhuman accounts found.")

    if account:
        match = next((a for a in accounts if a["email"] == account), None)
        if not match:
            available = ", ".join(a["email"] for a in accounts)
            raise RuntimeError(f"Account {account} not found. Available: {available}")
        return match["email"], match["ws_url"]

    if len(accounts) == 1:
        return accounts[0]["email"], accounts[0]["ws_url"]

    available = ", ".join(a["email"] for a in accounts)
    raise RuntimeError(f"Multiple accounts found: {available}\nUse --account or set SCLI_ACCOUNT env var.")


def inject_draft(account=None, *, to, subject="", body="", cc=None, bcc=None, port=CDP_PORT):
    """Inject a draft into Superhuman.

    Args:
        account: Email account. Auto-detected if omitted.
        to: List of recipient emails.
        subject: Email subject.
        body: Email body (HTML supported).
        cc: List of CC emails.
        bcc: List of BCC emails.

    Returns dict: {draft_id, thread_id, subject, to}
    """
    _, ws_url = resolve_account(account, port)
    _cdp_eval(ws_url, _JS_FIND_MAIN)

    fields = {
        "action": "compose",
        "subject": subject,
        "body": body,
        "to": _build_recipients(to),
        "cc": _build_recipients(cc or []),
        "bcc": _build_recipients(bcc or []),
    }
    js = _JS_INJECT_DRAFT.format(fields_json=json.dumps(fields))
    return _cdp_eval(ws_url, js)


def list_drafts(account=None, *, port=CDP_PORT):
    """List all drafts for an account.

    Returns list of dicts: [{id, subject, to, action}, ...]
    """
    _, ws_url = resolve_account(account, port)
    _cdp_eval(ws_url, _JS_FIND_MAIN)
    result = _cdp_eval(ws_url, _JS_LIST_DRAFTS, await_promise=False)
    return result.get("drafts", []) if isinstance(result, dict) else result


def list_threads(label="INBOX", *, limit=20, account=None, port=CDP_PORT):
    """List threads for a label (default: INBOX).

    Args:
        label: Gmail label (INBOX, SENT, STARRED, IMPORTANT, SPAM, TRASH, or custom).
        limit: Max threads to return.

    Returns list of dicts: [{id, subject, snippet, from, from_name, date, message_count, labels, is_unread}, ...]
    """
    _, ws_url = resolve_account(account, port)
    _cdp_eval(ws_url, _JS_FIND_MAIN)
    js = _JS_LIST_THREADS.format(label=label, limit=limit)
    result = _cdp_eval(ws_url, js)
    return result.get("threads", []) if isinstance(result, dict) else result


def search(query, *, max_results=20, account=None, port=CDP_PORT):
    """Search emails using Gmail search syntax.

    Supports the same query syntax as Superhuman/Gmail search bar:
        from:user@example.com
        to:me subject:invoice
        is:unread
        has:attachment
        after:2024/01/01

    Args:
        query: Search query string.
        max_results: Max results to return.

    Returns dict: {threads: [...], result_size_estimate, next_page_token}
    """
    _, ws_url = resolve_account(account, port)
    _cdp_eval(ws_url, _JS_FIND_MAIN)
    # Escape single quotes in query for JS string
    safe_query = query.replace("\\", "\\\\").replace("'", "\\'")
    js = _JS_SEARCH.format(query=safe_query, max_results=max_results)
    result = _cdp_eval(ws_url, js)
    return result


def read_thread(thread_id, *, account=None, port=CDP_PORT):
    """Read a thread's full content including all messages.

    Args:
        thread_id: The thread ID (e.g. '19cfec19f6e01cb6').

    Returns dict with: id, subject, message_count, labels, messages (each with
    id, from, to, cc, date, snippet, body, attachments).
    """
    _, ws_url = resolve_account(account, port)
    _cdp_eval(ws_url, _JS_FIND_MAIN)
    js = _JS_READ_THREAD.format(thread_id=thread_id)
    return _cdp_eval(ws_url, js)


def read_draft(draft_id, *, account=None, port=CDP_PORT):
    """Read a draft's full content.

    Args:
        draft_id: The draft ID (e.g. 'draft00a99078b2b2e5df').
        account: Email account. Auto-detected if omitted.

    Returns dict with: id, thread_id, subject, body, to, cc, bcc, from,
                       action, quoted_content, attachments, dirty.
    """
    _, ws_url = resolve_account(account, port)
    _cdp_eval(ws_url, _JS_FIND_MAIN)
    js = _JS_READ_DRAFT.format(draft_id=draft_id)
    return _cdp_eval(ws_url, js, await_promise=False)


def update_draft(draft_id, *, subject=None, body=None, to=None, cc=None, bcc=None, account=None, port=CDP_PORT):
    """Update fields on an existing draft (leaves it as a draft, does not send).

    Only provided fields are updated. Allowed fields: subject, body, to, cc, bcc.

    Args:
        draft_id: The draft ID to update.
        subject: New subject (or None to leave unchanged).
        body: New body HTML (or None to leave unchanged).
        to: New recipient emails (or None to leave unchanged).
        cc: New CC emails (or None to leave unchanged).
        bcc: New BCC emails (or None to leave unchanged).

    Returns dict: {draft_id, thread_id, subject, to, dirty}
    """
    _, ws_url = resolve_account(account, port)
    _cdp_eval(ws_url, _JS_FIND_MAIN)

    updates = {}
    if subject is not None:
        updates["subject"] = subject
    if body is not None:
        updates["body"] = body
    if to is not None:
        updates["to"] = [{"email": e} for e in to]
    if cc is not None:
        updates["cc"] = [{"email": e} for e in cc]
    if bcc is not None:
        updates["bcc"] = [{"email": e} for e in bcc]

    if not updates:
        raise RuntimeError("No fields to update. Provide at least one of: subject, body, to, cc, bcc.")

    js = _JS_UPDATE_DRAFT.format(draft_id=draft_id, updates_json=json.dumps(updates))
    return _cdp_eval(ws_url, js)


def attach_file(draft_id, file_path, *, account=None, port=CDP_PORT):
    """Attach a file to an existing draft.

    Args:
        draft_id: The draft ID to attach to.
        file_path: Path to the file to attach.

    Returns dict: {draft_id, attached, method, uuid, size}
    """
    import mimetypes

    file_path = os.path.expanduser(file_path)
    if not os.path.isfile(file_path):
        raise RuntimeError(f"File not found: {file_path}")

    file_name = os.path.basename(file_path)
    file_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    with open(file_path, "rb") as f:
        file_b64 = base64.b64encode(f.read()).decode("ascii")

    _, ws_url = resolve_account(account, port)
    _cdp_eval(ws_url, _JS_FIND_MAIN)

    js = _JS_ATTACH_FILE.format(
        draft_id=draft_id,
        file_name=file_name,
        file_type=file_type,
        file_b64=file_b64,
    )
    return _cdp_eval(ws_url, js, await_promise=True)
