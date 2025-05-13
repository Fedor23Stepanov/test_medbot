# bot/handlers.py

import re
import asyncio
from functools import partial

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    CommandHandler,
    Application
)

from db.crud import (
    get_user_by_tg,
    get_user_by_id,
    activate_user,
    invite_user,
    list_active_users,
    block_user,
    get_user_stats,
    get_user_events,
    get_random_device,
    create_event,
    create_proxy_log,
    set_transition_mode,
    set_notification_mode,
)
from db.models import UserStatus, TransitionMode, NotificationMode
from crawler.redirector import fetch_redirect, ProxyAcquireError
from config import ROLE_ADMIN, ROLE_MODERATOR

URL_PATTERN = re.compile(r'https?://[^\s)]+')

# Ролевые уровни для сравнения при удалении
ROLE_LEVELS = {
    ROLE_ADMIN: 3,
    ROLE_MODERATOR: 2,
    "User": 1,
}


# ——— Меню-клавиатуры —————————————————————————————————

def build_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["📊 Статистика", "⚙️ Настройки"]],
        resize_keyboard=True
    )


def build_stats_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["Назад", "Все запросы"]],
        resize_keyboard=True
    )


def build_settings_menu(role: str) -> ReplyKeyboardMarkup:
    rows = [
        ["Назад", "Уведомления"],
        ["Режим перехода"]
    ]
    if role in (ROLE_ADMIN, ROLE_MODERATOR):
        rows[1].append("Пользователи")
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def build_transition_menu(role: str) -> ReplyKeyboardMarkup:
    rows = [
        ["Сразу", "В течение дня"],
    ]
    for row in build_settings_menu(role).keyboard:
        rows.append(row)
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def build_notification_menu(role: str) -> ReplyKeyboardMarkup:
    rows = [
        ["Каждый переход", "По окончании очереди", "Отключены"],
    ]
    for row in build_settings_menu(role).keyboard:
        rows.append(row)
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def build_user_mgmt_menu(role: str) -> ReplyKeyboardMarkup:
    first = ["Добавить пользователя"]
    if role == ROLE_ADMIN:
        first.append("Добавить модератора")
    rows = [first]
    for row in build_settings_menu(role).keyboard:
        rows.append(row)
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


# ——— Показываем Главное меню —————————————————————————

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, role: str):
    context.user_data["current_menu"] = "main"
    await update.message.reply_text("🧾 Главное меню", reply_markup=build_main_menu())


# ——— Статистика ——————————————————————————————————

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status != UserStatus.active:
        return
    stats = await get_user_stats(user.id)
    text = (
        f"📊 Твоя статистика:\n"
        f"• За всё время: {stats['all_time']}\n"
        f"• За месяц: {stats['last_month']}\n"
        f"• За неделю: {stats['last_week']}"
    )
    context.user_data["current_menu"] = "stats"
    await update.message.reply_text(text, reply_markup=build_stats_menu())


# ——— Все запросы пользователя —————————————————————————

async def user_events_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status != UserStatus.active:
        return
    events = await get_user_events(user.id)
    if not events:
        text = "У тебя ещё нет запросов."
    else:
        lines = []
        for ev in events:
            ts = ev.timestamp.strftime("%Y-%m-%d %H:%M")
            lines.append(f"{ts}  {ev.initial_url}")
        text = "\n".join(lines)
    context.user_data["current_menu"] = "events"
    await update.message.reply_text(text, reply_markup=build_stats_menu())


# ——— Настройки ———————————————————————————————————

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status != UserStatus.active:
        return
    context.user_data["current_menu"] = "settings"
    await update.message.reply_text("⚙️ Настройки", reply_markup=build_settings_menu(user.role))


# ——— Режим перехода —————————————————————————————————

async def transition_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status != UserStatus.active:
        return
    cur = user.transition_mode
    display = "Сразу" if cur == TransitionMode.immediate else "В течение дня"
    context.user_data["current_menu"] = "transition"
    await update.message.reply_text(
        f"Текущий режим перехода: {display}\nВыберите режим:",
        reply_markup=build_transition_menu(user.role)
    )


# ——— Режим уведомлений —————————————————————————————

async def notification_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status != UserStatus.active:
        return
    cur = user.notification_mode
    display = {
        NotificationMode.per_transition: "Каждый переход",
        NotificationMode.after_queue:   "По окончании очереди",
        NotificationMode.disabled:      "Отключены"
    }[cur]
    context.user_data["current_menu"] = "notifications"
    await update.message.reply_text(
        f"Текущий режим уведомлений: {display}\nВыберите режим:",
        reply_markup=build_notification_menu(user.role)
    )


# ——— Управление пользователями —————————————————————————

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status != UserStatus.active or user.role not in (ROLE_ADMIN, ROLE_MODERATOR):
        return
    context.user_data["current_menu"] = "users"

    actives = await list_active_users()
    rows = []
    for u in actives:
        if u.id == user.id:
            continue  # не показываем себя
        # только выше стоящие могут удалить
        if ROLE_LEVELS[user.role] > ROLE_LEVELS[u.role]:
            rows.append([
                InlineKeyboardButton(f"Удалить @{u.username}", callback_data=f"delete_{u.id}")
            ])
        else:
            rows.append([
                InlineKeyboardButton(f"@{u.username} ({u.role})", callback_data="noop")
            ])

    if rows:
        await update.message.reply_text(
            "👥 Активные пользователи:",
            reply_markup=InlineKeyboardMarkup(rows)
        )
    else:
        await update.message.reply_text("Нет других активных пользователей.")

    await update.message.reply_text(
        "Управление пользователями",
        reply_markup=build_user_mgmt_menu(user.role)
    )


async def delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    actor = await get_user_by_tg(q.from_user.id)
    if not actor or actor.status != UserStatus.active:
        return
    _, uid = q.data.split("_", 1)
    target = await get_user_by_id(int(uid))
    if not target:
        return await q.edit_message_text("Пользователь не найден.")
    if ROLE_LEVELS[actor.role] <= ROLE_LEVELS[target.role]:
        return await q.answer("Недостаточно прав.", show_alert=True)
    ok = await block_user(target.id)
    await q.edit_message_text(
        f"{'✅' if ok else '❌'} @{target.username} {'заблокирован' if ok else 'не удалён'}."
    )


async def noop_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # заглушка для неактивных inline-кнопок
    await update.callback_query.answer()


# ——— Приглашение нового пользователя/модератора ———————————

async def start_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if not user or user.status != UserStatus.active or user.role not in (ROLE_ADMIN, ROLE_MODERATOR):
        return

    text = update.message.text
    if text == "Добавить пользователя":
        context.user_data["invite_role"] = "User"
    elif text == "Добавить модератора" and user.role == ROLE_ADMIN:
        context.user_data["invite_role"] = ROLE_MODERATOR
    else:
        return

    context.user_data["awaiting_new_username"] = True
    await update.message.reply_text(
        "Введите ник нового пользователя (без @):",
        reply_markup=ReplyKeyboardRemove()
    )


# ——— /start и /menu ——————————————————————————————————

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    username = (update.effective_user.username or "").strip().lstrip("@").lower()

    user = await get_user_by_tg(tg_id)
    # активный → главное меню
    if user and user.status is UserStatus.active:
        return await show_main_menu(update, context, user.role)

    # заблокированный → игнор
    if user and user.status is UserStatus.blocked:
        return

    # пытаемся активировать (pending → active)
    activated = await activate_user(tg_id, username)
    if activated:
        return await show_main_menu(update, context, activated.role)

    # нет записи → отказ
    await update.message.reply_text(
        "❌ У тебя нет доступа. Обратись к администратору.",
        reply_markup=ReplyKeyboardRemove()
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user_by_tg(update.effective_user.id)
    if user and user.status is UserStatus.active:
        await show_main_menu(update, context, user.role)


# ——— Общий хендлер текстовых сообщений ——————————————————

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    text = update.message.text or ""
    username = (update.effective_user.username or "").strip().lstrip("@").lower()

    # авто-активация
    user = await get_user_by_tg(tg_id)
    if not user:
        user = await activate_user(tg_id, username)
        if user:
            return await show_main_menu(update, context, user.role)
        return await update.message.reply_text(
            "❌ У тебя нет доступа. Обратись к администратору.",
            reply_markup=ReplyKeyboardRemove()
        )
    if user.status is UserStatus.blocked:
        return  # игнор

    # ввод ника для приглашения
    if context.user_data.pop("awaiting_new_username", False):
        uname = text.lstrip("@").lower()
        role_to = context.user_data.pop("invite_role")
        new = await invite_user(username=uname, role=role_to, invited_by=user.tg_id)
        context.user_data["current_menu"] = "users"
        return await update.message.reply_text(
            f"@{new.username} приглашён как {new.role}. Статус: ⏳",
            reply_markup=build_user_mgmt_menu(user.role)
        )

    # навигация по меню
    if text == "📊 Статистика":
        return await stats_cmd(update, context)
    if text == "Все запросы":
        return await user_events_cmd(update, context)
    if text == "⚙️ Настройки":
        return await settings_cmd(update, context)

    if text == "Назад":
        cm = context.user_data.get("current_menu")
        # из статистики → главное
        if cm in ("stats", "events"):
            return await show_main_menu(update, context, user.role)
        # из подменю настроек → настройки
        return await settings_cmd(update, context)

    if text == "Режим перехода":
        return await transition_cmd(update, context)
    if text in ("Сразу", "В течение дня"):
        mode = TransitionMode.immediate if text == "Сразу" else TransitionMode.daily_random
        await set_transition_mode(user.id, mode)
        return await settings_cmd(update, context)

    if text == "Уведомления":
        return await notification_cmd(update, context)
    if text in ("Каждый переход", "По окончании очереди", "Отключены"):
        mapping = {
            "Каждый переход":   NotificationMode.per_transition,
            "По окончании очереди": NotificationMode.after_queue,
            "Отключены":        NotificationMode.disabled,
        }
        await set_notification_mode(user.id, mapping[text])
        return await settings_cmd(update, context)

    if text == "Пользователи":
        return await users_cmd(update, context)
    if text in ("Добавить пользователя", "Добавить модератора"):
        return await start_invite(update, context)

    # далее — обработка ссылок (для active only)
    if user.status is not UserStatus.active:
        return

    urls = URL_PATTERN.findall(text)
    if not urls:
        await create_event(user_id=user.id, state="no link",
                           device_option_id=0, initial_url="", final_url="",
                           ip=None, isp=None)
        return await update.message.reply_text(
            "❗ Пожалуйста, пришли одну ссылку.",
            reply_to_message_id=update.message.message_id
        )
    if len(urls) > 1:
        await create_event(user_id=user.id, state="many links",
                           device_option_id=0, initial_url="", final_url="",
                           ip=None, isp=None)
        return await update.message.reply_text(
            "❗ Одну ссылку за раз, пожалуйста.",
            reply_to_message_id=update.message.message_id
        )

    raw_url = urls[0]
    try:
        device = await get_random_device()
    except ValueError as e:
        return await update.message.reply_text(
            str(e),
            reply_to_message_id=update.message.message_id
        )

    loop = asyncio.get_running_loop()
    try:
        initial_url, final_url, ip, isp, _, proxy_attempts = await loop.run_in_executor(
            None, partial(fetch_redirect, raw_url, device)
        )
    except ProxyAcquireError as e:
        for at in e.attempts:
            await create_proxy_log(at["attempt"], at["ip"], at["city"])
        await create_event(user_id=user.id, state="proxy error",
                           device_option_id=device["id"], initial_url=raw_url,
                           final_url="", ip=None, isp=None)
        return await update.message.reply_text(
            f"⚠️ Не удалось подобрать прокси за {len(e.attempts)} попыток.",
            reply_to_message_id=update.message.message_id
        )

    for at in proxy_attempts:
        await create_proxy_log(at["attempt"], at["ip"], at["city"])

    await create_event(user_id=user.id, state="success",
                       device_option_id=device["id"],
                       initial_url=initial_url, final_url=final_url,
                       ip=ip, isp=isp)

    report = (
        f"📱 Профиль: {device['model']}\n"
        f"   • UA: {device['ua']}\n"
        f"🔗 Начальный URL:\n{initial_url}\n"
        f"✅ Итоговый URL:\n{final_url}\n"
        f"🌐 IP: {ip}\n"
        f"📡 ISP: {isp}"
    )
    await update.message.reply_text(
        report,
        disable_web_page_preview=True,
        reply_to_message_id=update.message.message_id
    )


def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))

    # callbacks для удаления активных пользователей
    app.add_handler(CallbackQueryHandler(delete_cb, pattern=r"^delete_\d+$"))
    app.add_handler(CallbackQueryHandler(noop_cb,   pattern=r"^noop$"))

    # текстовые сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
