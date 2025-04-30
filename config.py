# config.py

import os

# ======================
# Telegram Bot Settings
# ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7552510473:AAEYfF7I2d8v48kl_XtqNT1J7QbuI-rNpBQ")

# Список админов (никнеймы через запятую, без @)
# Например: "AdminOne,AdminTwo"
_raw_admins = os.getenv("INITIAL_ADMINS", "F_Stepanov")
INITIAL_ADMINS = [
    name.strip().lstrip("@").lower()
    for name in _raw_admins.split(",")
    if name.strip()
]

# ======================
# Database Settings
# ======================
# Например, для SQLite:
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db")

# ======================
# Proxy / IP-API Settings
# ======================
PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME",
    "ubce43f8555ef05b2-zone-custom-region-ru-st-moscow-city-moscow"
)
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "ubce43f8555ef05b2")
PROXY_DNS      = os.getenv("PROXY_DNS", "165.154.179.147:2334")

# URL для определения ISP/IP по IP-адресу
IP_API_URL = os.getenv("IP_API_URL", "http://ip-api.com/json")

# ======================
# Timing & Retry Limits
# ======================
CHECK_INTERVAL     = int(os.getenv("CHECK_INTERVAL", "1"))
REDIRECT_TIMEOUT   = int(os.getenv("REDIRECT_TIMEOUT", "20"))
MAX_PROXY_ATTEMPTS = int(os.getenv("MAX_PROXY_ATTEMPTS", "5"))
