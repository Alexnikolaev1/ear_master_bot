"""
Работа с временными медиафайлами: скачивание голоса, отправка voice/photo, очистка.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from aiogram import Bot
from aiogram.types import BufferedInputFile, Message

import config


def cleanup_file(path: Optional[str]) -> None:
    """Удаляет временный файл, не бросая исключений."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def temp_path(prefix: str, suffix: str = "") -> str:
    """Путь к уникальному временному файлу в TMP_DIR."""
    os.makedirs(config.TMP_DIR, exist_ok=True)
    return os.path.join(config.TMP_DIR, f"{prefix}_{uuid.uuid4().hex}{suffix}")


@asynccontextmanager
async def download_voice(bot: Bot, file_id: str, prefix: str = "voice") -> AsyncIterator[str]:
    """Скачивает голосовое сообщение во временный файл и удаляет его после использования."""
    local_path = temp_path(prefix, ".oga")
    try:
        file_info = await bot.get_file(file_id)
        await bot.download_file(file_info.file_path, destination=local_path)
        yield local_path
    finally:
        cleanup_file(local_path)


async def send_voice_file(
    message: Message,
    path: str,
    *,
    caption: Optional[str] = None,
    reply_markup=None,
    filename: str = "audio.ogg",
) -> Message:
    """Отправляет локальный OGG как voice note и удаляет файл."""
    try:
        with open(path, "rb") as f:
            return await message.answer_voice(
                BufferedInputFile(f.read(), filename=filename),
                caption=caption,
                reply_markup=reply_markup,
            )
    finally:
        cleanup_file(path)


async def send_photo_file(
    message: Message,
    path: str,
    *,
    caption: Optional[str] = None,
    reply_markup=None,
    filename: str = "image.png",
) -> Message:
    """Отправляет локальный PNG как фото и удаляет файл."""
    try:
        with open(path, "rb") as f:
            return await message.answer_photo(
                BufferedInputFile(f.read(), filename=filename),
                caption=caption,
                reply_markup=reply_markup,
            )
    finally:
        cleanup_file(path)


async def send_audio_file(
    message: Message,
    path: str,
    *,
    title: str = "Аудио",
    filename: str = "audio.mp3",
) -> Message:
    """Отправляет локальный аудиофайл и удаляет его."""
    try:
        with open(path, "rb") as f:
            return await message.answer_audio(
                BufferedInputFile(f.read(), filename=filename),
                title=title,
            )
    finally:
        cleanup_file(path)
