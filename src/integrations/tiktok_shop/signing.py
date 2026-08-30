"""TikTok Shop Open API request signature.

Algorithm (Partner Center "Sign your API request" is JS-rendered; reproduced from the
open-source SDK EcomPHP/tiktokshop-php src/Client.php, which mirrors the official doc
https://partner.tiktokshop.com/docv2/page/create-hash-to-sign-your-test-api-call):

    sign = hex(HMAC_SHA256(key=app_secret,
        msg=app_secret + path + "".join(f"{k}{v}" for sorted query without sign/access_token)
            + body (non-GET, non-multipart only) + app_secret))

Query param name: ``sign``; token header: ``x-tts-access-token``.
# UNVERIFIED against a live call (hex case: lowercase per PHP hash_hmac default).
"""
import hashlib
import hmac
from collections.abc import Mapping

EXCLUDED = frozenset({"sign", "access_token", "x-tts-access-token"})


def normalise_query(query: Mapping[str, object]) -> dict[str, str]:
    """Canonical string form used for BOTH signing and sending (never sign one, send another).
    bool -> "true"/"false"; list/tuple -> comma-joined  # UNVERIFIED: list serialisation."""
    out: dict[str, str] = {}
    for k, v in query.items():
        if v is None:
            continue
        if isinstance(v, bool):
            out[k] = "true" if v else "false"
        elif isinstance(v, (list, tuple)):
            out[k] = ",".join(str(x) for x in v)
        else:
            out[k] = str(v)
    return out


def sign_string(app_secret: str, path: str, query: Mapping[str, object],
                body: bytes | None) -> str:
    params = "".join(f"{k}{query[k]}" for k in sorted(query) if k not in EXCLUDED)
    s = f"{app_secret}{path}{params}"
    if body:
        s += body.decode("utf-8")
    return s + app_secret


def compute_sign(app_secret: str, path: str, query: Mapping[str, object],
                 body: bytes | None = None) -> str:
    msg = sign_string(app_secret, path, query, body).encode("utf-8")
    return hmac.new(app_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
