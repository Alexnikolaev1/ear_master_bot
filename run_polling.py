"""
run_polling.py
Локальный запуск через long polling (без вебхука).
На Railway используется bot.py.
"""
import asyncio
import logging
import os

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
from bot import create_dispatcher
from database import init_db
from services.reminders import start_reminder_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def main() -> None:
    config.validate_config()
    os.makedirs(config.TMP_DIR, exist_ok=True)
    await init_db()

    bot = Bot(
        token=config.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher()

    start_reminder_loop(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
