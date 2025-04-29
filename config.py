import os

# ======================
# Telegram Bot Settings
# ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7552510473:AAEYfF7I2d8v48kl_XtqNT1J7QbuI-rNpBQ")

# ======================
# Database Settings
# ======================
# Для SQLite: "sqlite+aiosqlite:///./app.db"
# Для другой СУБД замените на соответствующий URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db")

# ======================
# Proxy / IP-API Settings
# ======================
USERNAME_BASE = os.getenv(
    "USERNAME_BASE",
    "ubce43f8555ef05b2-zone-custom-region-ru-st-moscow-city-moscow"
)
PASSWORD    = os.getenv("PROXY_PASSWORD", "ubce43f8555ef05b2")
PROXY_DNS   = os.getenv("PROXY_DNS", "165.154.179.147:2334")
IP_API_URL  = os.getenv("IP_API_URL", "http://ip-api.com/json")

# ======================
# Timing & Retry Limits
# ======================
# Сколько секунд ждать между попытками подобрать московский прокси
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "1"))

# Сколько секунд ждать редиректа после driver.get()
REDIRECT_TIMEOUT = int(os.getenv("REDIRECT_TIMEOUT", "20"))

# Максимальное число попыток подобрать московский прокси
MAX_PROXY_ATTEMPTS = int(os.getenv("MAX_PROXY_ATTEMPTS", "5"))
