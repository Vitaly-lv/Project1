import json
import logging
import os
import socket
import sys
import warnings
from pathlib import Path

import httpx
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()

warnings.filterwarnings(
    "ignore",
    message=".*per_message=False.*",
    category=UserWarning,
    module="telegram.ext._conversationhandler",
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MANAGER_ID = os.getenv("YOUR_USER_ID")


def get_system_proxy() -> str | None:
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            if not enabled:
                return None
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
            if "://" in server:
                return server
            if "=" in server:
                for part in server.split(";"):
                    if part.startswith("http="):
                        return f"http://{part[5:]}"
            return f"http://{server}"
    except OSError:
        return None


def resolve_proxy() -> str | None:
    return (
        os.getenv("TELEGRAM_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("ALL_PROXY")
        or get_system_proxy()
    )


def dns_resolves_telegram() -> bool:
    try:
        socket.getaddrinfo("api.telegram.org", 443, proto=socket.IPPROTO_TCP)
        return True
    except socket.gaierror:
        return False


def print_connection_help(dns_ok: bool, proxy: str | None) -> None:
    logger.error("Не удалось подключиться к Telegram API.")
    if not dns_ok and not proxy:
        logger.error(
            "DNS не находит api.telegram.org — VPN не применяется к Python.\n"
            "Сделайте одно из следующего:\n"
            "  1. В VPN-клиенте включите «TUN» / «режим для всей системы»\n"
            "  2. В настройках VPN найдите порт SOCKS5 и добавьте в .env:\n"
            "     TELEGRAM_PROXY=socks5://127.0.0.1:ПОРТ\n"
            "  3. Добавьте в файл hosts (от имени администратора):\n"
            "     149.154.167.220 api.telegram.org"
        )
    elif not dns_ok and proxy:
        logger.error(
            "DNS не работает, а прокси %s не помог. Проверьте VPN и порт прокси.",
            proxy,
        )
    else:
        logger.error(
            "Сервер недоступен. Проверьте VPN или укажите прокси в .env:\n"
            "  TELEGRAM_PROXY=socks5://127.0.0.1:10808"
        )


def verify_connection(token: str, proxy: str | None) -> None:
    url = f"https://api.telegram.org/bot{token}/getMe"
    with httpx.Client(proxy=proxy, timeout=20.0) as client:
        response = client.get(url)
        response.raise_for_status()
        username = response.json()["result"]["username"]
    logger.info("Подключение к Telegram OK: @%s", username)

LEVEL, CUISINE, CUSTOM_CUISINE, FORMAT = range(4)
NAME, CONVENIENT_TIME, CONTACT_FORMAT, CONTACT = range(4, 8)

LEVEL_MAP = {
    "новичок": "Новичок",
    "любитель": "Любитель",
    "опытный": "Профессионал",
}
CUISINE_MAP = {
    "итальянская": "Итальянская",
    "французская": "Французская",
    "японская": "Японская",
    "индийская": "Индийская",
}
FORMAT_MAP = {
    "видеоуроки": "Видеоуроки",
    "живые мастер-классы": "Живой мастер-класс",
    "индивидуальные занятия": "Индивидуально",
}

COURSES_PATH = Path(__file__).parent / "courses.json"


def load_courses() -> list[dict]:
    with open(COURSES_PATH, encoding="utf-8") as f:
        return json.load(f)["courses"]


def find_course(level: str, cuisine: str, course_format: str) -> dict | None:
    for course in load_courses():
        if (
            course["level"] == level
            and course["cuisine"] == cuisine
            and course["format"] == course_format
        ):
            return course
    return None


def level_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("новичок", callback_data="level:новичок")],
        [InlineKeyboardButton("любитель", callback_data="level:любитель")],
        [InlineKeyboardButton("опытный", callback_data="level:опытный")],
    ]
    return InlineKeyboardMarkup(buttons)


def cuisine_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("итальянская", callback_data="cuisine:итальянская")],
        [InlineKeyboardButton("французская", callback_data="cuisine:французская")],
        [InlineKeyboardButton("японская", callback_data="cuisine:японская")],
        [InlineKeyboardButton("индийская", callback_data="cuisine:индийская")],
        [InlineKeyboardButton("другая", callback_data="cuisine:другая")],
    ]
    return InlineKeyboardMarkup(buttons)


def format_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("видеоуроки", callback_data="format:видеоуроки")],
        [InlineKeyboardButton("живые мастер-классы", callback_data="format:живые мастер-классы")],
        [InlineKeyboardButton("индивидуальные занятия", callback_data="format:индивидуальные занятия")],
    ]
    return InlineKeyboardMarkup(buttons)


def application_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Оформит заявку на курс", callback_data="apply")]]
    )


def contact_format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Telegram", callback_data="contact_format:Telegram")],
            [InlineKeyboardButton("WhatsApp", callback_data="contact_format:WhatsApp")],
        ]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Начать подбор курса", callback_data="begin_survey")]]
    )
    await update.message.reply_text(
        "Привет, мы поможем Вам подобрать подходящий курс по кулинарии "
        "с помощью небольшого опроса и примем заявку на курс. Начнем?",
        reply_markup=keyboard,
    )
    return ConversationHandler.END


async def begin_survey(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    await query.edit_message_text(
        "Ответьте на несколько вопросов, чтобы мы подобрали для вас идеальный курс"
    )
    await query.message.reply_text("Ваш уровень?", reply_markup=level_keyboard())
    return LEVEL


async def handle_level(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    level_key = query.data.split(":", 1)[1]
    context.user_data["level"] = LEVEL_MAP[level_key]
    context.user_data["level_display"] = level_key

    await query.edit_message_text(f"Ваш уровень: {level_key}")
    await query.message.reply_text(
        "Какие кухни интересуют?", reply_markup=cuisine_keyboard()
    )
    return CUISINE


async def handle_cuisine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    cuisine_key = query.data.split(":", 1)[1]
    context.user_data["cuisine_key"] = cuisine_key

    await query.edit_message_text(f"Кухня: {cuisine_key}")

    if cuisine_key == "другая":
        context.user_data["is_other_cuisine"] = True
        await query.message.reply_text("Введите интересующую вас кухню:")
        return CUSTOM_CUISINE

    context.user_data["is_other_cuisine"] = False
    context.user_data["cuisine"] = CUISINE_MAP[cuisine_key]
    context.user_data["cuisine_display"] = cuisine_key
    await query.message.reply_text(
        "Предпочтительный формат:", reply_markup=format_keyboard()
    )
    return FORMAT


async def handle_custom_cuisine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    custom = update.message.text.strip()
    context.user_data["cuisine_display"] = custom
    context.user_data["cuisine"] = custom

    await update.message.reply_text(
        "Предпочтительный формат:", reply_markup=format_keyboard()
    )
    return FORMAT


async def show_course_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    format_key = query.data.split(":", 1)[1]
    context.user_data["format"] = FORMAT_MAP[format_key]
    context.user_data["format_display"] = format_key

    await query.edit_message_text(f"Формат: {format_key}")

    is_other = context.user_data.get("is_other_cuisine", False)
    course = None

    if not is_other:
        course = find_course(
            context.user_data["level"],
            context.user_data["cuisine"],
            context.user_data["format"],
        )

    if course:
        context.user_data["course_description"] = course["description"]
        await query.message.reply_text(course["description"])
    elif is_other:
        context.user_data["course_description"] = None
        await query.message.reply_text(
            "К сожалению, такого курса пока нет в нашей базе"
        )
    else:
        context.user_data["course_description"] = None
        await query.message.reply_text(
            "К сожалению, такого курса пока нет в нашей базе"
        )
        return ConversationHandler.END

    await query.message.reply_text(
        "Хотите записаться на курс?",
        reply_markup=application_keyboard(),
    )
    return ConversationHandler.END


async def start_application(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text("Введите ваше имя:")
    return NAME


async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Укажите удобное время для связи:")
    return CONVENIENT_TIME


async def handle_convenient_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["convenient_time"] = update.message.text.strip()
    await update.message.reply_text(
        "Выберите удобный формат связи:",
        reply_markup=contact_format_keyboard(),
    )
    return CONTACT_FORMAT


async def handle_contact_format(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    contact_format = query.data.split(":", 1)[1]
    context.user_data["contact_format"] = contact_format
    await query.edit_message_text(f"Формат связи: {contact_format}")
    await query.message.reply_text("Введите контакт (телефон или username):")
    return CONTACT


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["contact"] = update.message.text.strip()

    if not MANAGER_ID:
        await update.message.reply_text(
            "Ошибка: не задан YOUR_USER_ID в .env. Заявка не отправлена."
        )
        context.user_data.clear()
        return ConversationHandler.END

    user = update.effective_user
    data = context.user_data
    course_text = data.get("course_description") or "Курс не найден в базе"
    telegram_line = (
        f"Telegram: @{user.username} (ID: {user.id})"
        if user.username
        else f"Telegram ID: {user.id}"
    )

    manager_message = (
        "📋 Новая заявка на курс\n\n"
        f"👤 Имя: {data['name']}\n"
        f"🕐 Удобное время: {data['convenient_time']}\n"
        f"📱 Формат связи: {data['contact_format']}\n"
        f"📞 Контакт: {data['contact']}\n\n"
        "——— Данные опроса ———\n"
        f"Уровень: {data.get('level_display', data.get('level', '—'))}\n"
        f"Кухня: {data.get('cuisine_display', data.get('cuisine', '—'))}\n"
        f"Формат: {data.get('format_display', data.get('format', '—'))}\n\n"
        f"Курс:\n{course_text}\n\n"
        f"{telegram_line}"
    )

    await context.bot.send_message(chat_id=int(MANAGER_ID), text=manager_message)
    await update.message.reply_text(
        "Спасибо! Наш менеджер свяжется с вами для записи и уточнения деталей."
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Опрос отменён. Введите /start, чтобы начать заново.")
    return ConversationHandler.END


def main() -> None:
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")

    proxy = resolve_proxy()
    dns_ok = dns_resolves_telegram()

    if proxy:
        logger.info("Используется прокси: %s", proxy)
    elif not dns_ok:
        logger.warning(
            "DNS не находит api.telegram.org. Включите VPN (режим для всей системы) "
            "или укажите TELEGRAM_PROXY в .env"
        )

    try:
        verify_connection(TOKEN, proxy)
    except Exception as exc:
        print_connection_help(dns_ok, proxy)
        raise SystemExit(1) from exc

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
        proxy=proxy,
    )
    builder = Application.builder().token(TOKEN).request(request)
    if proxy:
        builder = builder.proxy(proxy).get_updates_proxy(proxy)
    application = builder.build()

    survey_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(begin_survey, pattern="^begin_survey$")],
        states={
            LEVEL: [CallbackQueryHandler(handle_level, pattern="^level:")],
            CUISINE: [CallbackQueryHandler(handle_cuisine, pattern="^cuisine:")],
            CUSTOM_CUISINE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_cuisine)
            ],
            FORMAT: [CallbackQueryHandler(show_course_result, pattern="^format:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        name="survey",
    )

    application_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_application, pattern="^apply$")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            CONVENIENT_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_convenient_time)
            ],
            CONTACT_FORMAT: [
                CallbackQueryHandler(handle_contact_format, pattern="^contact_format:")
            ],
            CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contact)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        name="application",
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(survey_handler)
    application.add_handler(application_handler)

    logger.info("Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()
