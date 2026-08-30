"""TikTok Marketing API v1.3 OAuth: auth_code -> long-lived access token.
Source: business-api.tiktok.com/portal/docs?id=1739965703387137 (Authentication); SDK
tiktok/tiktok-business-api-sdk AuthenticationApi.oauth2_access_token."""
import httpx

TOKEN_URL = "https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/"


class AdsAuthError(RuntimeError):
    def __init__(self, code: object, message: object, status: int | None = None):
        super().__init__(f"code={code} status={status} message={message}")
        self.code, self.message, self.status = code, message, status


def exchange_auth_code(app_id: str, secret: str, auth_code: str,
                       client: httpx.Client | None = None) -> dict:
    c = client or httpx.Client(timeout=20)
    r = c.post(TOKEN_URL, json={"app_id": app_id, "secret": secret, "auth_code": auth_code})
    try:
        body = r.json()
    except ValueError:
        raise AdsAuthError("non_json", r.text[:300], r.status_code) from None
    if r.status_code != 200 or body.get("code") != 0:
        raise AdsAuthError(body.get("code", r.status_code), body.get("message"), r.status_code)
    return body["data"]  # access_token, advertiser_ids[], scope[]
