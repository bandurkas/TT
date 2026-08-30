import logging

from fastapi import APIRouter, Request

log = logging.getLogger("tt.oauth")
router = APIRouter(prefix="/oauth")


@router.get("/tiktok-shop/callback")
async def tiktok_shop_callback(request: Request) -> dict:
    # Phase 0: capture the auth code only; token exchange comes with the Shop adapter.
    params = dict(request.query_params)
    code = params.get("code")
    log.info("tiktok-shop callback received code=%s... keys=%s", (code or "")[:6], sorted(params))
    return {"received": bool(code), "params": sorted(params), "note": "code logged; exchange not implemented yet"}


@router.get("/tiktok-ads/callback")
async def tiktok_ads_callback(request: Request) -> dict:
    params = dict(request.query_params)
    code = params.get("auth_code")
    log.info("tiktok-ads callback received auth_code=%s... keys=%s", (code or "")[:6], sorted(params))
    return {"received": bool(code), "params": sorted(params), "note": "auth_code logged; exchange not implemented yet"}
