"""Telegram Bot API sendMessage (https://core.telegram.org/bots/api#sendmessage)."""
import httpx

MAX_LEN = 4096


class TelegramError(RuntimeError):
    pass


def chunk_text(text: str, limit: int = MAX_LEN) -> list[str]:
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
    if cur or not chunks:
        chunks.append(cur)
    return chunks


class TelegramClient:
    def __init__(self, token: str, chat_id: str, http: httpx.Client | None = None,
                 base_url: str = "https://api.telegram.org"):
        self.token, self.chat_id = token, chat_id
        self.http = http or httpx.Client(timeout=20)
        self.base_url = base_url.rstrip("/")

    def send_message(self, text: str, parse_mode: str | None = None) -> list[int]:
        ids: list[int] = []
        for chunk in chunk_text(text):
            payload = {"chat_id": self.chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            r = self.http.post(f"{self.base_url}/bot{self.token}/sendMessage", json=payload)
            body = r.json()
            if r.status_code != 200 or not body.get("ok"):
                raise TelegramError(f"{r.status_code}: {body.get('description')}")
            ids.append(int(body["result"]["message_id"]))
        return ids
