/**
 * Draft operations — stub.
 *
 * TODO: Implement these functions matching python/scli/core.py.
 * The JS payloads to inject are identical — copy them from core.py constants:
 *   _JS_FIND_MAIN, _JS_LIST_DRAFTS, _JS_INJECT_DRAFT
 */

export interface Account {
  email: string;
  title: string;
  wsUrl: string;
}

export interface Draft {
  id: string;
  subject: string;
  to: string[];
  action: string;
}

export interface InjectResult {
  draft_id: string;
  thread_id: string;
  subject: string;
  to: string[];
}

export interface InjectOptions {
  to: string[];
  subject?: string;
  body?: string;
  cc?: string[];
  bcc?: string[];
  account?: string;
  port?: number;
}

export async function listAccounts(port = 9222): Promise<Account[]> {
  // TODO: GET http://127.0.0.1:{port}/json/list, parse mail.superhuman.com targets
  throw new Error("Not implemented — see python/scli/core.py get_accounts()");
}

export async function listDrafts(account?: string, port = 9222): Promise<Draft[]> {
  // TODO: Connect to account target, eval _JS_FIND_MAIN then _JS_LIST_DRAFTS
  throw new Error("Not implemented — see python/scli/core.py list_drafts()");
}

export async function injectDraft(options: InjectOptions): Promise<InjectResult> {
  // TODO: Connect to account target, eval _JS_FIND_MAIN then _JS_INJECT_DRAFT
  throw new Error("Not implemented — see python/scli/core.py inject_draft()");
}
