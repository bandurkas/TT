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

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


settings = Settings()
