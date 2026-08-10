from __future__ import annotations

import os


class Settings:
    app_password: str = os.environ.get("APP_PASSWORD", "")
    secret_key: str = os.environ.get("SECRET_KEY", "")
    # Railway serve tudo em https; desliga só se você estiver testando local em http puro.
    cookie_secure: bool = os.environ.get("COOKIE_SECURE", "true").lower() not in ("false", "0", "")
    session_max_age_days: int = int(os.environ.get("SESSION_MAX_AGE_DAYS", "30"))


settings = Settings()
