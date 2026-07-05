"""
bot.py
Точка входа EAR MASTER AI.

На Railway по умолчанию — long polling (+ health-сервер для проверок).
Webhook: USE_POLLING=false и задан WEBHOOK_HOST / RAILWAY_PUBLIC_DOMAIN.
"""
import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import config
from database import init_db
from handlers import (
    chords,
    common,
    degrees,
    dictation,
    harmony,
    intervals,
    intonation,
    lesson,
    melodies,
    notation,
    rhythm,
    settings,
    singing,
    start,
    stats,
    theory,
    weakspots,
)
from middlewares import ErrorMiddleware, UpdateLoggingMiddleware, UserMiddleware
from services.reminders import start_reminder_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ear_master_bot")

ALLOWED_UPDATES = ["message", "callback_query"]


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(UpdateLoggingMiddleware())
    dp.update.middleware(ErrorMiddleware())
    dp.update.middleware(UserMiddleware())

    dp.include_router(common.router)
    dp.include_router(start.router)
    dp.include_router(lesson.router)
    dp.include_router(weakspots.router)
    dp.include_router(intervals.router)
    dp.include_router(degrees.router)
    dp.include_router(chords.router)
    dp.include_router(harmony.router)
    dp.include_router(rhythm.router)
    dp.include_router(singing.router)
    dp.include_router(intonation.router)
    dp.include_router(notation.router)
    dp.include_router(melodies.router)
    dp.include_router(dictation.router)
    dp.include_router(theory.router)
    dp.include_router(stats.router)
    dp.include_router(settings.router)

    return dp


async def _init_runtime() -> None:
    os.makedirs(config.TMP_DIR, exist_ok=True)
    await init_db()
    logger.info("База данных инициализирована.")


@web.middleware
async def _webhook_access_log(request: web.Request, handler):
    if request.method == "POST" and request.path == config.WEBHOOK_PATH:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        logger.info(
            "Webhook POST from %s secret=%s",
            request.remote,
            "ok" if secret else "missing",
        )
    try:
        response = await handler(request)
        if request.method == "POST" and request.path == config.WEBHOOK_PATH:
            logger.info("Webhook response status=%s", response.status)
        return response
    except Exception:
        logger.exception("Webhook handler error")
        raise


def _health_routes(app: web.Application) -> None:
    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "EAR MASTER AI"})

    app.router.add_get("/", health)
    app.router.add_get("/health", health)


async def on_startup_webhook(bot: Bot) -> None:
    await _init_runtime()
    start_reminder_loop(bot)
    logger.info("Фоновые напоминания запущены.")

    if not config.WEBHOOK_URL:
        logger.warning(
            "WEBHOOK_HOST не задан — вебхук не установлен. "
            "Задайте USE_POLLING=true или публичный домен."
        )
        return
    if "railway.internal" in config.WEBHOOK_URL:
        logger.error(
            "Вебхук указывает на внутренний адрес Railway: %s",
            config.WEBHOOK_URL,
        )
        return

    await bot.set_webhook(
        url=config.WEBHOOK_URL,
        drop_pending_updates=True,
        allowed_updates=ALLOWED_UPDATES,
        secret_token=config.WEBHOOK_SECRET,
    )
    logger.info("Вебхук установлен: %s", config.WEBHOOK_URL)
    info = await bot.get_webhook_info()
    if info.last_error_message:
        logger.error(
            "Telegram webhook error: %s (date=%s)",
            info.last_error_message,
            info.last_error_date,
        )
    else:
        logger.info(
            "Webhook OK: pending_updates=%s ip=%s",
            info.pending_update_count,
            info.ip_address,
        )


async def on_shutdown_webhook(bot: Bot) -> None:
    await bot.delete_webhook()
    logger.info("Вебхук удалён, бот остановлен.")


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    await _init_runtime()
    start_reminder_loop(bot)
    logger.info("Фоновые напоминания запущены.")

    me = await bot.get_me()
    logger.info("Polling для @%s (id=%s)", me.username, me.id)

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Режим polling: вебхук снят, бот сам забирает обновления у Telegram")

    app = web.Application()
    _health_routes(app)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.HOST, config.PORT)
    await site.start()
    logger.info("Health-сервер на %s:%s", config.HOST, config.PORT)

    await dp.start_polling(bot, allowed_updates=ALLOWED_UPDATES)


def run_webhook(bot: Bot, dp: Dispatcher) -> None:
    dp.startup.register(on_startup_webhook)
    dp.shutdown.register(on_shutdown_webhook)

    app = web.Application(middlewares=[_webhook_access_log])
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=config.WEBHOOK_SECRET,
    )
    webhook_handler.register(app, path=config.WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    _health_routes(app)

    logger.info("Запуск webhook-сервера на %s:%s", config.HOST, config.PORT)
    web.run_app(app, host=config.HOST, port=config.PORT)


def main() -> None:
    config.validate_config()

    bot = Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher()

    if config.USE_POLLING:
        logger.info("USE_POLLING=true — webhook отключён")
        asyncio.run(run_polling(bot, dp))
    else:
        logger.info("USE_POLLING=false — режим webhook")
        run_webhook(bot, dp)


if __name__ == "__main__":
    main()
