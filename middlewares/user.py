"""Автоматическая регистрация пользователя при любом входящем событии."""
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

import database


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user: Optional[User] = data.get("event_from_user")
        if user is not None and not user.is_bot:
            db_user = await database.get_or_create_user(
                user.id,
                user.full_name or user.username or "Музыкант",
            )
            data["db_user"] = db_user
        return await handler(event, data)
