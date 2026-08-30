import httpx
import pytest

from src.integrations.telegram.client import TelegramClient, TelegramError, chunk_text


def test_chunk_short():
    assert chunk_text("hello") == ["hello"]
    assert chunk_text("") == [""]


def test_chunk_splits_on_lines():
    lines = ["x" * 1000] * 9
    chunks = chunk_text("\n".join(lines))
    assert len(chunks) == 3 and all(len(c) <= 4096 for c in chunks)
    assert "\n".join(chunks) == "\n".join(lines)


def test_chunk_hard_splits_long_line():
    chunks = chunk_text("y" * 9000)
    assert [len(c) for c in chunks] == [4096, 4096, 808]


def test_send_message_posts_chunks():
    sent = []

    def handler(req):
        sent.append(req)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent)}})

    c = TelegramClient("T", "42", http=httpx.Client(transport=httpx.MockTransport(handler)))
    ids = c.send_message("a" * 5000, parse_mode="HTML")
    assert ids == [1, 2] and sent[0].url.path == "/botT/sendMessage"
    import json
    body = json.loads(sent[0].content)
    assert body["chat_id"] == "42" and body["parse_mode"] == "HTML" and len(body["text"]) == 4096


def test_send_message_error():
    def handler(req):
        return httpx.Response(400, json={"ok": False, "description": "bad"})

    c = TelegramClient("T", "42", http=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(TelegramError):
        c.send_message("x")
