#config.py

import os

# ======================
# Telegram Bot Settings
# ======================

# Токен вашего бота
TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
    "7552510473:AAEYfF7I2d8v48kl_XtqNT1J7QbuI-rNpBQ"
)

# Список админов (никнеймы через запятую, без @), например "AdminOne,AdminTwo"
_raw_admins = os.getenv("INITIAL_ADMINS", "F_Stepanov")
# Приводим к нижнему регистру и убираем @
INITIAL_ADMINS = [
    name.strip().lstrip("@").lower()
    for name in _raw_admins.split(",")
    if name.strip()
]

# Роли в системе
ROLE_ADMIN     = "Admin"
ROLE_MODERATOR = "Maintainer"  # в коде это же название используют для модераторов
ROLE_USER      = "User"

# Значения по-умолчанию для пользовательских настроек
DEFAULT_TRANSITION_MODE   = "immediate"       # сразу
DEFAULT_NOTIFICATION_MODE = "per_transition"  # каждый переход

# ======================
# Database Settings
# ======================

# URL для подключения к БД (SQLite, Postgres и т.п.)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./app.db"
)

# ======================
# Proxy / IP-API Settings
# ======================

# Ваши креды для прокси-роторинга
PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME",
    "ubce43f8555ef05b2-zone-custom-region-ru-st-moscow-city-moscow"
)
PROXY_PASSWORD = os.getenv(
    "PROXY_PASSWORD",
    "ubce43f8555ef05b2"
)
PROXY_DNS      = os.getenv(
    "PROXY_DNS",
    "165.154.179.147:2334"
)

# URL для определения IP и ISP по IP-адресу
IP_API_URL = os.getenv(
    "IP_API_URL",
    "http://ip-api.com/json"
)

# ======================
# Timing & Retry Limits
# ======================

# Интервал между попытками подбора прокси (в секундах)
CHECK_INTERVAL     = int(os.getenv("CHECK_INTERVAL", "1"))
# Сколько ждать редиректа в браузере (в секундах)
REDIRECT_TIMEOUT   = int(os.getenv("REDIRECT_TIMEOUT", "20"))
# Максимум попыток получить московский прокси
MAX_PROXY_ATTEMPTS = int(os.getenv("MAX_PROXY_ATTEMPTS", "5"))
