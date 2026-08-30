import logging

from fastapi import APIRouter, Request

from src.config.settings import settings
from src.integrations.tiktok_shop.auth import ShopAuthError, TokenStore, exchange_code

log = logging.getLogger("tt.oauth")
router = APIRouter(prefix="/oauth")
shop_store = TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json")


@router.get("/tiktok-shop/callback")
async def tiktok_shop_callback(request: Request) -> dict:
    params = dict(request.query_params)
    code = params.get("code")
    log.info("tiktok-shop callback keys=%s", sorted(params))
    if not code:
        return {"ok": False, "error": "no code in query", "params": sorted(params)}
    if not settings.tiktok_shop_app_key:
        return {"ok": False, "error": "app key not configured"}
    try:
        data = exchange_code(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, code)
    except (ShopAuthError, Exception) as e:  # noqa: BLE001
        log.error("token exchange failed: %s", e)
        return {"ok": False, "error": str(e)}
    shop_store.save(data)
    log.info("tiktok-shop tokens stored for seller=%s", data.get("seller_name"))
    return {"ok": True, "seller_name": data.get("seller_name"),
            "access_token_expire_in": data.get("access_token_expire_in"),
            "note": "tokens stored; you can close this tab"}


@router.get("/tiktok-shop/status")
async def tiktok_shop_status() -> dict:
    return {"configured": bool(settings.tiktok_shop_app_key), "tokens": shop_store.public_view()}


@router.get("/tiktok-ads/callback")
async def tiktok_ads_callback(request: Request) -> dict:
    params = dict(request.query_params)
    code = params.get("auth_code")
    log.info("tiktok-ads callback auth_code=%s... keys=%s", (code or "")[:6], sorted(params))
    return {"received": bool(code), "params": sorted(params), "note": "auth_code logged; exchange not implemented yet"}
