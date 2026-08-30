"""Telegram Bot API sendMessage (https://core.telegram.org/bots/api#sendmessage).

Plain text only by default: chunking splits on lines/length and is NOT tag-safe, so
`parse_mode` is refused for text > MAX_LEN unless the caller pre-chunks."""
import time
from collections.abc import Callable

import httpx

MAX_LEN = 4096
RETRY_AFTER_CAP = 30.0


class TelegramError(RuntimeError):
    pass


def chunk_text(text: str, limit: int = MAX_LEN) -> list[str]:
    """Never yields empty/whitespace-only chunks (Telegram rejects them)."""
    chunks: list[str] = []
    cur = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        cand = line if not cur else f"{cur}\n{line}"
        if len(cand) > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = cand
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c.strip()]


class TelegramClient:
    def __init__(self, token: str, chat_id: str, http: httpx.Client | None = None,
                 base_url: str = "https://api.telegram.org",
                 sleep: Callable[[float], None] = time.sleep):
        self.token, self.chat_id, self.sleep = token, chat_id, sleep
        self.http = http or httpx.Client(timeout=20)
        self.base_url = base_url.rstrip("/")

    def _post(self, payload: dict) -> dict:
        url = f"{self.base_url}/bot{self.token}/sendMessage"
        r = self.http.post(url, json=payload)
        if r.status_code == 429:  # retry once, per body retry_after
            body = self._json(r)
            ra = (body.get("parameters") or {}).get("retry_after", 1)
            self.sleep(min(max(float(ra), 0.0), RETRY_AFTER_CAP))
            r = self.http.post(url, json=payload)
        body = self._json(r)
        if r.status_code != 200 or not body.get("ok"):
            raise TelegramError(f"{r.status_code}: {body.get('description')}")
        return body

    @staticmethod
    def _json(r: httpx.Response) -> dict:
        try:
            body = r.json()
        except ValueError:
            body = None
        return body if isinstance(body, dict) else {"description": r.text[:500]}

    def send_message(self, text: str, parse_mode: str | None = None) -> list[int]:
        if not text.strip():
            raise ValueError("empty message")
        if parse_mode and len(text) > MAX_LEN:
            raise ValueError("parse_mode with text > MAX_LEN: chunking is not tag-safe")
        ids: list[int] = []
        for chunk in chunk_text(text):
            payload = {"chat_id": self.chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            body = self._post(payload)
            ids.append(int(body["result"]["message_id"]))
        return ids
