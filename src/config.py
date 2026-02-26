from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Supabase
    supabase_url: str = ""
    supabase_key: str = Field(
        default="",
        validation_alias=AliasChoices("SUPABASE_KEY", "SUPABASE_SECRET_KEY"),
    )

    # Anthropic
    anthropic_api_key: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # App
    base_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    claude_model: str = "claude-sonnet-4-5-20250929"


settings = Settings()
