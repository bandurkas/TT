"""TikTok Shop Open API client (read-only). Paths from Partner Center docv2 page slugs and
EcomPHP/tiktokshop-php resources; every path is `# UNVERIFIED` until Deliverable 5."""
import fcntl
import json
import logging
import random
import time
from collections.abc import Callable, Iterator, Mapping
from typing import Any, Protocol

import httpx

from src.integrations.tiktok_shop.auth import TokenStore, refresh_token
from src.integrations.tiktok_shop.signing import compute_sign, normalise_query

log = logging.getLogger("tt.shop")
BASE_URL = "https://open-api.tiktokglobalshop.com"
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
RETRY_AFTER_CAP = 30.0
MAX_PAGES = 500
RawSink = Callable[[str, dict[str, Any], dict[str, Any]], None]
Redactor = Callable[[str, dict[str, Any]], dict[str, Any]]

# Buyer PII keys stripped from raw order payloads before raw_sink  # UNVERIFIED field names
ORDER_PII_KEYS = frozenset({"recipient_address", "buyer_email", "phone", "phone_number",
                            "name", "buyer_message", "user_id"})


def _strip_keys(obj: Any, keys: frozenset[str]) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_keys(v, keys) for k, v in obj.items() if k not in keys}
    if isinstance(obj, list):
        return [_strip_keys(x, keys) for x in obj]
    return obj


def default_redactor(resource: str, payload: dict[str, Any]) -> dict[str, Any]:
    if resource in ("orders", "order_detail"):
        return _strip_keys(payload, ORDER_PII_KEYS)
    return payload


def retry_after_seconds(resp: httpx.Response, fallback: float) -> float:
    try:
        ra = float(resp.headers.get("retry-after", ""))
    except ValueError:
        return fallback
    return min(max(ra, 0.0), RETRY_AFTER_CAP)


def safe_json(resp: httpx.Response) -> dict[str, Any]:
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return {"_non_json": True, "status": resp.status_code, "text": resp.text[:4000]}
    return payload


class ShopApiError(RuntimeError):
    def __init__(self, code: object, message: object, request_id: object = None,
                 status: int | None = None):
        super().__init__(f"code={code} message={message} request_id={request_id} status={status}")
        self.code, self.message, self.request_id, self.status = code, message, request_id, status


class TokenProvider(Protocol):
    def get_access_token(self) -> str: ...
    def refresh(self) -> None: ...


class StaticTokenProvider:
    def __init__(self, token: str):
        self._token = token

    def get_access_token(self) -> str:
        return self._token

    def refresh(self) -> None:
        pass


class FileTokenProvider:
    """Wraps TokenStore; refreshes when access_token_expire_in (unix seconds,
    # UNVERIFIED unit) is within `margin` of now. Missing/0 expiry => refresh now.
    Refresh is serialised across processes via flock on a sidecar lock file."""

    def __init__(self, store: TokenStore, app_key: str, app_secret: str, *,
                 margin: int = 3600, http: httpx.Client | None = None,
                 now: Callable[[], float] = time.time):
        self.store, self.app_key, self.app_secret = store, app_key, app_secret
        self.margin, self.http, self.now = margin, http, now
        self.lock_path = store.path.with_name(store.path.name + ".lock")

    def _needs_refresh(self, d: dict) -> bool:
        exp = int(d.get("access_token_expire_in") or 0)
        if not exp:
            log.warning("tiktok-shop token has no expiry; refreshing now")
            return True
        return exp - self.now() < self.margin

    def get_access_token(self) -> str:
        d = self.store.load()
        if not d or not d.get("access_token"):
            raise ShopApiError("no_token", "token store empty; authorize first")
        if self._needs_refresh(d):
            self.refresh()
            d = self.store.load() or d
        return d["access_token"]

    def refresh(self, force: bool = False) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                d = self.store.load() or {}  # re-read under lock
                if not force and d.get("access_token") and not self._needs_refresh(d):
                    return  # another process already refreshed
                if not d.get("refresh_token"):
                    raise ShopApiError("no_refresh_token", "cannot refresh")
                data = refresh_token(self.app_key, self.app_secret, d["refresh_token"], self.http)
                self.store.save({**d, **data})
                log.info("tiktok-shop access token refreshed")
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


class TikTokShopClient:
    def __init__(self, app_key: str, app_secret: str, token_provider: TokenProvider,
                 shop_cipher: str | None = None, base_url: str = BASE_URL,
                 raw_sink: RawSink | None = None, http: httpx.Client | None = None,
                 max_retries: int = 4, backoff_base: float = 0.5,
                 sleep: Callable[[float], None] = time.sleep,
                 now_ms: Callable[[], int] = lambda: int(time.time() * 1000),
                 redact: Redactor | None = default_redactor, max_pages: int = MAX_PAGES):
        self.app_key, self.app_secret, self.tokens = app_key, app_secret, token_provider
        self.shop_cipher, self.base_url, self.raw_sink = shop_cipher, base_url.rstrip("/"), raw_sink
        self.http = http or httpx.Client(timeout=30)
        self.max_retries, self.backoff_base, self.sleep, self.now_ms = (
            max_retries, backoff_base, sleep, now_ms)
        self.redact, self.max_pages = redact, max_pages

    # --- core -------------------------------------------------------------------------
    def _send(self, method: str, url: str, path: str, q: dict[str, str], raw_body: bytes | None,
              headers: dict[str, str]) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            delay = self.backoff_base * 2 ** attempt * (1 + random.random() * 0.1)
            try:
                resp = self.http.request(method, url, params=q, content=raw_body, headers=headers)
            except httpx.TransportError as e:
                if attempt >= self.max_retries:
                    raise ShopApiError("transport", f"{type(e).__name__}: {e}") from e
                log.warning("shop %s %s transport error %s, retry in %.2fs", method, path,
                            type(e).__name__, delay)
                self.sleep(delay)
                continue
            if resp.status_code in RETRY_STATUS and attempt < self.max_retries:
                if resp.status_code == 429:
                    delay = retry_after_seconds(resp, delay)
                log.warning("shop %s %s -> %s, retry in %.2fs", method, path,
                            resp.status_code, delay)
                self.sleep(delay)
                continue
            return resp
        raise AssertionError("unreachable")

    def request(self, method: str, path: str, *, query: Mapping[str, Any] | None = None,
                body: Mapping[str, Any] | None = None, resource: str = "",
                with_shop_cipher: bool = True) -> dict[str, Any]:
        q: dict[str, Any] = {"app_key": self.app_key, "timestamp": self.now_ms() // 1000}
        if with_shop_cipher and self.shop_cipher:
            q["shop_cipher"] = self.shop_cipher
        q.update(query or {})
        qs = normalise_query(q)  # signed and sent as the same dict
        raw_body = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        qs["sign"] = compute_sign(self.app_secret, path, qs, None if method == "GET" else raw_body)
        headers = {"x-tts-access-token": self.tokens.get_access_token(),
                   "content-type": "application/json"}
        resp = self._send(method, self.base_url + path, path, qs, raw_body, headers)
        payload = safe_json(resp)
        meta = {"method": method, "path": path, "query": {k: v for k, v in qs.items()
                if k != "sign"}, "status": resp.status_code, "request_id": payload.get("request_id")}
        res = resource or path
        if self.raw_sink:
            self.raw_sink(res, meta, self.redact(res, payload) if self.redact else payload)
        if resp.status_code != 200 or payload.get("code") != 0:
            raise ShopApiError(payload.get("code", resp.status_code),
                               payload.get("message") or payload.get("text"),
                               payload.get("request_id"), status=resp.status_code)
        return payload.get("data") or {}

    def paginate(self, method: str, path: str, items_key: str, *,
                 query: Mapping[str, Any] | None = None, body: Mapping[str, Any] | None = None,
                 resource: str = "", page_size: int = 50) -> Iterator[dict[str, Any]]:
        q = dict(query or {})
        q["page_size"] = page_size
        seen: set[str] = set()
        for _ in range(self.max_pages):
            data = self.request(method, path, query=q, body=body, resource=resource)
            yield from data.get(items_key) or []
            token = data.get("next_page_token")
            if not token:
                return
            if token in seen:
                raise ShopApiError("pagination_loop", f"repeated next_page_token on {path}")
            seen.add(token)
            q["page_token"] = token
        raise ShopApiError("max_pages", f"exceeded {self.max_pages} pages on {path}")
    # --- authorization ------------------------------------------------------------------
    def get_authorized_shops(self) -> list[dict[str, Any]]:
        # docv2/page/authorization-guide-202309  # UNVERIFIED
        data = self.request("GET", "/authorization/202309/shops", resource="shops",
                            with_shop_cipher=False)
        return data.get("shops") or []

    # --- orders ---------------------------------------------------------------------------
    def get_orders(self, *, create_time_ge: int | None = None, create_time_lt: int | None = None,
                   update_time_ge: int | None = None, update_time_lt: int | None = None,
                   order_status: str | None = None, page_size: int = 50) -> Iterator[dict[str, Any]]:
        # docv2/page/get-order-list-202309; filter field names  # UNVERIFIED
        body = {k: v for k, v in {"create_time_ge": create_time_ge, "create_time_lt": create_time_lt,
                                  "update_time_ge": update_time_ge, "update_time_lt": update_time_lt,
                                  "order_status": order_status}.items() if v is not None}
        return self.paginate("POST", "/order/202309/orders/search", "orders", body=body,
                             query={"sort_field": "create_time", "sort_order": "ASC"},
                             resource="orders", page_size=page_size)

    def get_order_detail(self, order_ids: list[str]) -> list[dict[str, Any]]:
        # docv2 "Get Order Detail" order/202309/orders?ids=  # UNVERIFIED
        data = self.request("GET", "/order/202309/orders", query={"ids": ",".join(order_ids)},
                            resource="order_detail")
        return data.get("orders") or []

    # --- products -------------------------------------------------------------------------
    def get_products(self, *, status: str | None = None, page_size: int = 100
                     ) -> Iterator[dict[str, Any]]:
        # docv2/page/search-products-202309  # UNVERIFIED
        body = {"status": status} if status else {}
        return self.paginate("POST", "/product/202309/products/search", "products", body=body,
                             resource="products", page_size=page_size)

    def get_product(self, product_id: str) -> dict[str, Any]:
        # product/202309/products/{id}  # UNVERIFIED
        return self.request("GET", f"/product/202309/products/{product_id}", resource="product")

    # --- analytics (Data Insights) ------------------------------------------------------
    # Paths from EcomPHP Analytics.php (min version 202405); Partner Center now lists
    # 202409/202509 revisions of the video pages. Version  # UNVERIFIED
    ANALYTICS_VERSION = "202509"  # verified live 2026-08-30 (video/sku/shop perf); 202405 also OK for product perf

    def _analytics(self, path: str, resource: str, start_date: str, end_date: str,
                   items_key: str | None, extra: Mapping[str, Any] | None = None,
                   page_size: int = 50) -> Any:
        q = {"start_date_ge": start_date, "end_date_lt": end_date, **(extra or {})}
        full = f"/analytics/{self.ANALYTICS_VERSION}{path}"
        if items_key is None:
            return self.request("GET", full, query=q, resource=resource)
        return self.paginate("GET", full, items_key, query=q, resource=resource,
                             page_size=page_size)

    def get_shop_performance(self, start_date: str, end_date: str) -> dict[str, Any]:
        return self._analytics("/shop/performance", "shop_performance", start_date, end_date, None)

    def get_video_performance(self, start_date: str, end_date: str) -> Iterator[dict[str, Any]]:
        # docv2/page/get-shop-video-performance-list-202509; items_key  # UNVERIFIED
        return self._analytics("/shop_videos/performance", "video_performance",
                               start_date, end_date, "videos")

    def get_video_performance_overview(self, start_date: str, end_date: str) -> dict[str, Any]:
        return self._analytics("/shop_videos/overview_performance", "video_overview",
                               start_date, end_date, None)

    def get_video_performance_detail(self, video_id: str, start_date: str,
                                     end_date: str) -> dict[str, Any]:
        return self._analytics(f"/shop_videos/{video_id}/performance", "video_detail",
                               start_date, end_date, None)

    def get_video_product_performance(self, video_id: str, start_date: str,
                                      end_date: str) -> Iterator[dict[str, Any]]:
        return self._analytics(f"/shop_videos/{video_id}/products/performance",
                               "video_products", start_date, end_date, "products")

    def get_product_performance(self, start_date: str, end_date: str) -> Iterator[dict[str, Any]]:
        return self._analytics("/shop_products/performance", "product_performance",
                               start_date, end_date, "products")

    def get_product_performance_detail(self, product_id: str, start_date: str,
                                       end_date: str) -> dict[str, Any]:
        return self._analytics(f"/shop_products/{product_id}/performance",
                               "product_detail", start_date, end_date, None)

    def get_sku_performance(self, start_date: str, end_date: str) -> Iterator[dict[str, Any]]:
        return self._analytics("/shop_skus/performance", "sku_performance",
                               start_date, end_date, "skus")

    def get_live_performance(self, start_date: str, end_date: str) -> dict[str, Any]:
        # docv2/page/get-shop-live-performance-overview-202508 shows
        # analytics/202508/shop_lives/overview_performance  # UNVERIFIED
        q = {"start_date_ge": start_date, "end_date_lt": end_date}
        return self.request("GET", "/analytics/202508/shop_lives/overview_performance",
                            query=q, resource="live_overview")

    # --- finance ----------------------------------------------------------------------
    def get_finance_statements(self, *, statement_time_ge: int | None = None,
                               statement_time_lt: int | None = None,
                               payment_status: str | None = None,
                               page_size: int = 50) -> Iterator[dict[str, Any]]:
        # docv2/page/get-statements-202309  # UNVERIFIED
        q = {"statement_time_ge": statement_time_ge, "statement_time_lt": statement_time_lt,
             "payment_status": payment_status, "sort_field": "statement_time",
             "sort_order": "ASC"}
        return self.paginate("GET", "/finance/202309/statements", "statements", query=q,
                             resource="statements", page_size=page_size)

    get_settlements = get_finance_statements  # TikTok "statement" == settlement batch

    def get_statement_transactions(self, statement_id: str,
                                   page_size: int = 50) -> Iterator[dict[str, Any]]:
        # finance/202309/statements/{id}/statement_transactions (202501 revision exists)
        # UNVERIFIED
        q = {"sort_field": "order_create_time", "sort_order": "ASC"}
        return self.paginate("GET", f"/finance/202309/statements/{statement_id}/"
                             "statement_transactions", "transactions", query=q,
                             resource="statement_transactions", page_size=page_size)

    get_finance_transactions = get_statement_transactions

    def get_order_statement_transactions(self, order_id: str) -> dict[str, Any]:
        # docv2/page/get-transactions-by-order-202309  # UNVERIFIED
        return self.request("GET", f"/finance/202309/orders/{order_id}/statement_transactions",
                            resource="order_transactions")

    def get_payouts(self, *, create_time_ge: int | None = None, create_time_lt: int | None = None,
                    page_size: int = 50) -> Iterator[dict[str, Any]]:
        # finance/202309/payments (Finance API overview: "payment details")  # UNVERIFIED
        q = {"create_time_ge": create_time_ge, "create_time_lt": create_time_lt,
             "sort_field": "create_time", "sort_order": "ASC"}
        return self.paginate("GET", "/finance/202309/payments", "payments", query=q,
                             resource="payments", page_size=page_size)

    def get_withdrawals(self, types: str = "WITHDRAW,SETTLE,TRANSFER,REVERSE",
                        page_size: int = 50) -> Iterator[dict[str, Any]]:
        # docv2/page/get-withdrawals-202309  # UNVERIFIED
        return self.paginate("GET", "/finance/202309/withdrawals", "withdrawals",
                             query={"types": types}, resource="withdrawals", page_size=page_size)

    # --- returns / affiliate ------------------------------------------------------------
    def get_returns(self, *, create_time_ge: int | None = None, create_time_lt: int | None = None,
                    page_size: int = 50) -> Iterator[dict[str, Any]]:
        # return_refund/202309/returns/search; category slug  # UNVERIFIED
        body = {k: v for k, v in {"create_time_ge": create_time_ge,
                                  "create_time_lt": create_time_lt}.items() if v is not None}
        return self.paginate("POST", "/return_refund/202309/returns/search", "return_orders",
                             body=body, resource="returns", page_size=page_size)

    def get_affiliate_orders(self, **_: Any) -> Iterator[dict[str, Any]]:
        # affiliate_seller/202309/orders/search exists in EcomPHP but body/scope unknown.
        raise NotImplementedError("UNVERIFIED: Affiliate Seller orders/search "
                                  "(docv2 Affiliate Seller API) — needs doc + scope check")
