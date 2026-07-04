"""
Ежедневные напоминания о тренировке с учётом часового пояса пользователя.
Фоновый цикл раз в минуту; не чаще одного сообщения в день.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database

logger = logging.getLogger("ear_master_bot.reminders")

REMINDER_TEXT = (
    "🔔 <b>Время тренировки!</b>\n\n"
    "10 минут «🧠 План на сегодня» — и слух снова на шаг ближе к музыкальному.\n"
    "Ритуал сильнее марафона раз в неделю."
)


def validate_timezone(tz_name: str) -> bool:
    try:
        ZoneInfo(tz_name)
        return True
    except Exception:
        return False


async def send_due_reminders(bot: Bot) -> int:
    """Отправляет напоминания тем, кому сейчас локальный час = reminder_hour."""
    users = await database.get_users_for_reminders()
    sent = 0
    now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))

    for user in users:
        hour = user.get("reminder_hour")
        if hour is None:
            continue
        tz_name = user.get("timezone") or "Europe/Moscow"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        local = now_utc.astimezone(tz)
        local_day = local.strftime("%Y-%m-%d")

        # окно: нужный час, первые 2 минуты — чтобы не пропустить при sleep(60)
        if local.hour != int(hour) or local.minute > 1:
            continue
        if user.get("last_reminder_date") == local_day:
            continue
        # уже тренировался сегодня (streak/plan пишутся в UTC-дате)
        today_utc = now_utc.strftime("%Y-%m-%d")
        if user.get("last_training_date") == today_utc:
            continue
        if await database.plan_done_today(user["user_id"]):
            continue

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧠 Открыть план", callback_data="remind_plan")],
            [InlineKeyboardButton(text="🔕 Отключить напоминания", callback_data="remind_off")],
        ])
        try:
            await bot.send_message(
                user["user_id"],
                REMINDER_TEXT,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            await database.mark_reminder_sent(user["user_id"], local_day)
            sent += 1
        except Exception:
            logger.exception("Не удалось отправить напоминание user_id=%s", user["user_id"])

    return sent


async def reminder_loop(bot: Bot) -> None:
    """Бесконечный фон: проверка каждую минуту."""
    logger.info("Цикл напоминаний запущен")
    while True:
        try:
            n = await send_due_reminders(bot)
            if n:
                logger.info("Отправлено напоминаний: %s", n)
        except Exception:
            logger.exception("Ошибка в цикле напоминаний")
        await asyncio.sleep(60)


def start_reminder_loop(bot: Bot) -> asyncio.Task:
    return asyncio.create_task(reminder_loop(bot), name="reminder_loop")
