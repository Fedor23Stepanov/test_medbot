import time
import uuid
import requests
from urllib.parse import unquote

from seleniumwire import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from config import (
    USERNAME_BASE,
    PASSWORD,
    PROXY_DNS,
    IP_API_URL,
    CHECK_INTERVAL,
    REDIRECT_TIMEOUT,
    MAX_PROXY_ATTEMPTS,
)


class ProxyAcquireError(Exception):
    """
    Выбрасывается, когда не удалось получить «московский» прокси
    за MAX_PROXY_ATTEMPTS попыток.
    Атрибут .attempts — список всех попыток вида:
      {"attempt": int, "ip": str|None, "city": str|None}
    """
    def __init__(self, attempts):
        super().__init__(
            f"Не удалось получить московский прокси за {len(attempts)} попыток"
        )
        self.attempts = attempts


def _acquire_moscow_proxy():
    """
    Пытаемся получить прокси с IP из Москвы, не более MAX_PROXY_ATTEMPTS раз.
    Возвращает кортеж (proxy_auth: str, info: dict, attempts: list).
    Если не удаётся — бросает ProxyAcquireError(attempts).
    """
    attempts = []

    for attempt in range(1, MAX_PROXY_ATTEMPTS + 1):
        # Формируем credentials для ротации сессии
        session_id = uuid.uuid4().hex
        user = f"{USERNAME_BASE}-session-{session_id}"
        proxy_auth = f"http://{user}:{PASSWORD}@{PROXY_DNS}"

        ip = city = None
        info = {}
        try:
            resp = requests.get(
                IP_API_URL,
                proxies={"http": proxy_auth, "https": proxy_auth},
                timeout=5
            )
            info = resp.json()
            ip = info.get("query")
            city = info.get("city")
        except Exception:
            # в случае ошибки оставляем ip, city = None
            pass

        # Собираем данные попытки
        attempts.append({"attempt": attempt, "ip": ip, "city": city})

        # Если IP в Москве — возвращаем результат
        if city == "Moscow":
            return proxy_auth, info, attempts

        # Иначе ждём перед следующей попыткой
        time.sleep(CHECK_INTERVAL)

    # Лимит попыток исчерпан — поднимаем ошибку с полным списком попыток
    raise ProxyAcquireError(attempts)


def fetch_redirect(raw_url: str, device: dict):
    """
    Синхронно обходит ссылку через «московский» прокси+эмуляцию устройства.

    Параметры:
      raw_url — строка, может не начинаться с http://|https://
      device  — dict с ключами:
        {
          "ua": str,
          "css_size": [width:int, height:int],
          "platform": str,
          "dpr": int,
          "mobile": bool,
          "model": str|None
        }

    Возвращает кортеж:
      (
        initial_url: str,
        final_url:   str,
        ip:          str|None,
        isp:         str|None,
        device:      dict,       # тот же, что передан
        proxy_attempts: list     # список всех попыток из _acquire_moscow_proxy
      )

    Если не удалось получить московский прокси — бросает ProxyAcquireError.
    """
    # 1) Нормализуем URL
    url = raw_url if raw_url.startswith(("http://", "https://")) else f"http://{raw_url}"
    initial_url = unquote(url)

    # 2) Подбираем московский прокси (или получаем ошибку)
    proxy_auth, ip_info, proxy_attempts = _acquire_moscow_proxy()

    # 3) Собираем опции для Selenium
    ua = device["ua"]
    css_w, css_h = device["css_size"]
    platform = device["platform"]
    dpr = device["dpr"]
    mobile = device["mobile"]

    chrome_opts = webdriver.ChromeOptions()
    chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--disable-blink-features=AutomationControlled")
    chrome_opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_opts.add_experimental_option("useAutomationExtension", False)
    chrome_opts.add_argument(f"--user-agent={ua}")
    chrome_opts.add_argument(f"--window-size={css_w},{css_h}")
    chrome_opts.set_capability("pageLoadStrategy", "none")

    seleniumwire_opts = {
        "proxy": {
            "http": proxy_auth,
            "https": proxy_auth,
            "no_proxy": "localhost,127.0.0.1"
        },
        "request_storage": "memory",
        "connection_timeout": 10,
        "request_timeout": 30,
    }

    driver = webdriver.Chrome(options=chrome_opts, seleniumwire_options=seleniumwire_opts)

    # stealth: прячем webdriver и эмулируем параметры устройства
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"}
    )
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": css_w, "height": css_h, "deviceScaleFactor": dpr, "mobile": mobile}
    )
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": f"""
            Object.defineProperty(navigator, 'platform', {{ get: () => '{platform}' }});
            Object.defineProperty(navigator, 'languages', {{ get: () => ['ru-RU','ru'] }});
            Object.defineProperty(navigator, 'language', {{ get: () => 'ru-RU' }});
            Object.defineProperty(navigator, 'plugins', {{ get: () => [1,2,3,4,5] }});
            Object.defineProperty(navigator, 'deviceMemory', {{ get: () => 8 }});
            Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => 8 }});
            Object.defineProperty(navigator, 'connection', {{
                get: () => {{ rtt:50, downlink:10, effectiveType:'4g' }}
            }});
        """}
    )

    # 4) Переходим по URL и ждём первого редиректа
    try:
        driver.get(url)
    except (TimeoutException, WebDriverException):
        # можно залогировать, но продолжаем
        pass

    try:
        WebDriverWait(driver, REDIRECT_TIMEOUT).until(EC.url_changes(url))
        final_url = driver.current_url
    except TimeoutException:
        final_url = driver.current_url

    # 5) Останавливаем загрузку и закрываем драйвер
    try:
        driver.execute_script("window.stop();")
    except Exception:
        pass
    driver.quit()

    return (
        initial_url,
        unquote(final_url),
        ip_info.get("query"),
        ip_info.get("isp"),
        device,
        proxy_attempts
    )
