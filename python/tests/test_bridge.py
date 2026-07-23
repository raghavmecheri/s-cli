"""Tests for the draft-only bridge adapter (sdraft.bridge)."""

import json

import pytest

from sdraft import bridge


def _write(tmp_path, payload):
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_markdown_to_html_converts_markdown():
    html = bridge._markdown_to_html("**bold** and _italic_")
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html


def test_markdown_to_html_passes_through_existing_html():
    assert bridge._markdown_to_html("<p>hi</p>") == "<p>hi</p>"


def test_markdown_to_html_empty():
    assert bridge._markdown_to_html("") == ""


def test_happy_path_injects_and_prints_json(tmp_path, monkeypatch, capsys):
    captured = {}

    def fake_inject(account, *, to, subject, body, cc, bcc):
        captured.update(account=account, to=to, subject=subject, body=body, cc=cc, bcc=bcc)
        return {"draft_id": "draft123", "thread_id": "t1", "subject": subject, "to": to}

    monkeypatch.setattr(bridge, "inject_draft", fake_inject)
    json_file = _write(
        tmp_path,
        {
            "idempotency_key": "abc",
            "to": ["a@x.com"],
            "cc": ["c@x.com"],
            "bcc": [],
            "subject": "Hello",
            "body_markdown": "line one\n\nline two",
            "reply_to": None,
        },
    )

    rc = bridge.main(["draft", "--json-file", json_file, "--account", "me@x.com"])
    assert rc == 0

    out = json.loads(capsys.readouterr().out)
    assert out["draft_id"] == "draft123"
    assert captured["account"] == "me@x.com"
    assert captured["to"] == ["a@x.com"]
    assert captured["cc"] == ["c@x.com"]
    assert "<p>" in captured["body"]  # markdown -> html


@pytest.mark.parametrize(
    "payload",
    [
        {"to": ["a@x.com"], "send": True},
        {"to": ["a@x.com"], "scheduled_send": "2026-01-01"},
        {"to": ["a@x.com"], "reply_to": "thread123"},
        {"to": [], "subject": "no recipients"},
        {"to": ["not-an-email"]},
        {"subject": "missing to entirely"},
    ],
)
def test_rejected_payloads_exit_nonzero(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(bridge, "inject_draft", lambda *a, **k: pytest.fail("should not inject"))
    json_file = _write(tmp_path, payload)
    with pytest.raises(SystemExit) as exc:
        bridge.main(["draft", "--json-file", json_file])
    assert exc.value.code == 4


def test_oversize_body_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "inject_draft", lambda *a, **k: pytest.fail("should not inject"))
    payload = {"to": ["a@x.com"], "body_markdown": "x" * (bridge.MAX_BODY_BYTES + 1)}
    json_file = _write(tmp_path, payload)
    with pytest.raises(SystemExit) as exc:
        bridge.main(["draft", "--json-file", json_file])
    assert exc.value.code == 4
