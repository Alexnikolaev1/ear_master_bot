"""Логирование входящих апдейтов для отладки webhook."""
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

logger = logging.getLogger("ear_master_bot.updates")


class UpdateLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            if event.message:
                msg = event.message
                logger.info(
                    "update message user=%s chat=%s text=%r",
                    msg.from_user.id if msg.from_user else "?",
                    msg.chat.id,
                    msg.text,
                )
            elif event.callback_query:
                cb = event.callback_query
                logger.info(
                    "update callback user=%s data=%r",
                    cb.from_user.id if cb.from_user else "?",
                    cb.data,
                )
        elif isinstance(event, Message):
            logger.info(
                "message user=%s text=%r",
                event.from_user.id if event.from_user else "?",
                event.text,
            )
        elif isinstance(event, CallbackQuery):
            logger.info(
                "callback user=%s data=%r",
                event.from_user.id if event.from_user else "?",
                event.data,
            )
        return await handler(event, data)
