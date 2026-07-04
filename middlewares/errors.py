"""Глобальная обработка необработанных исключений в хендлерах."""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger("ear_master_bot.errors")


class ErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            logger.exception("Необработанная ошибка в хендлере")
            text = "😔 Что-то пошло не так. Попробуй ещё раз или выбери раздел в меню."
            try:
                if isinstance(event, Message):
                    await event.answer(text)
                elif isinstance(event, CallbackQuery):
                    if event.message:
                        await event.message.answer(text)
                    await event.answer()
            except Exception:
                logger.exception("Не удалось отправить сообщение об ошибке")
            return None
