import os

# ======================
# Telegram Bot Settings
# ======================

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
    "7552510473:AAEYfF7I2d8v48kl_XtqNT1J7QbuI-rNpBQ"
)

# ======================
# Database Settings
# ======================

# Например, для SQLite:
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db")

# ======================
# Proxy / IP-API Settings
# ======================

# Логин и пароль вашего прокси 
PROXY_USERNAME = os.getenv(
    "PROXY_USERNAME",
    "ubce43f8555ef05b2-zone-custom-region-ru-st-moscow-city-moscow"
)
PROXY_PASSWORD = os.getenv(
    "PROXY_PASSWORD",
    "ubce43f8555ef05b2"
)

# Адрес прокси-сервера (хост:порт)
PROXY_DNS = os.getenv("PROXY_DNS", "165.154.179.147:2334")

# URL для определения ISP/IP по IP-адресу 
IP_API_URL = os.getenv("IP_API_URL", "http://ip-api.com/json")

# ======================
# Timing & Retry Limits
# ======================

# Сколько секунд ждать между попытками подобрать московский прокси 
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "1"))

# Таймаут на driver.get (ожидание редиректа)
REDIRECT_TIMEOUT = int(os.getenv("REDIRECT_TIMEOUT", "20"))

# Максимальное число попыток подобрать московский прокси 
MAX_PROXY_ATTEMPTS = int(os.getenv("MAX_PROXY_ATTEMPTS", "5"))


# ======================
# User Management Settings
# ======================

# Никнейм администратора, который при первом старте попадёт в БД со статусом 'waiting'.
# Задаётся в ENV, например:
# ADMIN_USERNAME=alice
ADMIN_USERNAME = os.getenv("F_Stepanov")
if not ADMIN_USERNAME:
    raise RuntimeError("Не задан ADMIN_USERNAME (никнейм администратора)")

# Константы ролей
ROLE_ADMIN = "admin"
ROLE_MODERATOR = "moderator"
ROLE_USER = "user"

# Константы статусов
STATUS_WAITING = "waiting"
STATUS_ACTIVE = "active"

# Режим уведомлений: "immediate" или "random_day"
DEFAULT_NOTIFICATION_MODE = os.getenv("DEFAULT_NOTIFICATION_MODE", "immediate")

# Режим перехода: "every" / "end_of_queue" / "disabled"
DEFAULT_TRANSITION_MODE = os.getenv("DEFAULT_TRANSITION_MODE", "every")
