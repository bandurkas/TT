import httpx
import pytest

from src.integrations.telegram.client import TelegramClient, TelegramError, chunk_text


def test_chunk_short():
    assert chunk_text("hello") == ["hello"]


def test_chunk_never_empty():
    assert chunk_text("") == []
    assert chunk_text("\n\n\n") == []
    assert chunk_text("   \n  ") == []
    assert chunk_text("\n\na\n\n") == ["a\n\n"]  # leading blanks dropped, chunk non-empty


def _client(handler, **kw):
    return TelegramClient("T", "42", http=httpx.Client(transport=httpx.MockTransport(handler)),
                          sleep=lambda _s: None, **kw)


def test_send_empty_raises():
    c = _client(lambda r: pytest.fail("must not post"))
    with pytest.raises(ValueError):
        c.send_message("")
    with pytest.raises(ValueError):
        c.send_message("\n \n")


def test_parse_mode_refused_over_limit():
    c = _client(lambda r: pytest.fail("must not post"))
    with pytest.raises(ValueError, match="parse_mode"):
        c.send_message("a" * 5000, parse_mode="HTML")


def test_retry_once_on_429_with_retry_after():
    calls, slept = [], []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"ok": False, "description": "flood",
                                             "parameters": {"retry_after": 120}})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    c = TelegramClient("T", "42", http=httpx.Client(transport=httpx.MockTransport(handler)),
                       sleep=slept.append)
    assert c.send_message("hi") == [7]
    assert len(calls) == 2 and slept == [30.0]  # capped


def test_429_twice_raises():
    def handler(req):
        return httpx.Response(429, json={"ok": False, "description": "flood",
                                         "parameters": {"retry_after": 1}})

    with pytest.raises(TelegramError, match="429"):
        _client(handler).send_message("hi")


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
    ids = c.send_message("a" * 5000)
    assert ids == [1, 2] and sent[0].url.path == "/botT/sendMessage"
    import json
    body = json.loads(sent[0].content)
    assert body["chat_id"] == "42" and "parse_mode" not in body and len(body["text"]) == 4096
    assert c.send_message("<b>x</b>", parse_mode="HTML") == [3]
    assert json.loads(sent[2].content)["parse_mode"] == "HTML"


def test_send_message_error():
    def handler(req):
        return httpx.Response(400, json={"ok": False, "description": "bad"})

    c = TelegramClient("T", "42", http=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(TelegramError):
        c.send_message("x")
