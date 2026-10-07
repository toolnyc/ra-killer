from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

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
    sqlite_path: str = "/opt/ra-killer/hotline.db"


settings = Settings()
