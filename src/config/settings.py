from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    api_port: int = 8400
    database_url: str = "postgresql+psycopg://tt:tt@localhost:5432/tt"
    redis_url: str = "redis://localhost:6379/0"
    shop_timezone: str = "Asia/Jakarta"
    shop_currency: str = "IDR"

    tiktok_shop_app_key: str = ""
    tiktok_shop_app_secret: str = ""
    tiktok_shop_shop_cipher: str = ""
    token_store_dir: str = "data"
    tiktok_ads_app_id: str = ""
    tiktok_ads_secret: str = ""

    # Windsor.ai TikTok connector (interim GMV Max Cost until the Ads app is approved).
    # Empty key = the ingest job is skipped, so dev and CI never reach the network.
    windsor_api_key: str = ""
    windsor_backfill_days: int = 7

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


settings = Settings()
