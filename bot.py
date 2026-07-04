"""
bot.py
Точка входа EAR MASTER AI (webhook-режим для Railway).

Порядок роутеров:
1. common — «Стоп» / «Повторить»
2. разделы с FSM для голоса — до settings
3. settings — общий F.voice для голосовых команд навигации
"""
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
from middlewares import ErrorMiddleware, UserMiddleware
from services.reminders import start_reminder_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ear_master_bot")


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(ErrorMiddleware())
    dp.update.middleware(UserMiddleware())

    # Порядок важен: common и голосовые FSM — до settings.router
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


async def on_startup(bot: Bot) -> None:
    os.makedirs(config.TMP_DIR, exist_ok=True)
    await init_db()
    logger.info("База данных инициализирована.")
    start_reminder_loop(bot)
    logger.info("Фоновые напоминания запущены.")

    if config.WEBHOOK_URL:
        await bot.set_webhook(
            url=config.WEBHOOK_URL,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"],
        )
        logger.info("Вебхук установлен: %s", config.WEBHOOK_URL)
    else:
        logger.warning(
            "WEBHOOK_HOST не задан — вебхук не установлен. "
            "Для локальной разработки используйте run_polling.py."
        )


async def on_shutdown(bot: Bot) -> None:
    await bot.delete_webhook()
    logger.info("Вебхук удалён, бот остановлен.")


def main() -> None:
    config.validate_config()

    bot = Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher()

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=config.WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "EAR MASTER AI"})

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    logger.info("Запуск веб-сервера на %s:%s", config.HOST, config.PORT)
    web.run_app(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
