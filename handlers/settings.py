"""
Настройки: часовой пояс, напоминания, голосовые команды навигации.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
import database
from services.groq_service import route_command_text, transcribe_voice_command
from services.reminders import validate_timezone
from utils.keyboards import main_menu_keyboard
from utils.media import download_voice

router = Router(name="settings")

SECTION_NAMES = {
    "lesson": "🧠 План на сегодня",
    "plan": "🧠 План на сегодня",
    "weakspots": "💪 Слабые места",
    "intervals": "🎵 Интервалы",
    "degrees": "🎼 Ступени",
    "chords": "🎹 Аккорды",
    "harmony": "🏛 Гармония",
    "rhythm": "🥁 Ритм",
    "singing": "🎤 Пение",
    "intonation": "🎤 Интонация",
    "notation": "📖 Ноты",
    "melodies": "🎶 Мелодии",
    "dictation": "✍️ Диктант",
    "theory": "📚 Теория",
    "stats": "📊 Прогресс",
}


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    user = await database.get_user(message.from_user.id)
    tz = (user["timezone"] if user else None) or config.DEFAULT_TIMEZONE
    hour = user["reminder_hour"] if user else None
    if hour is None:
        remind_line = "выключены"
    else:
        remind_line = f"каждый день в <b>{int(hour):02d}:00</b> ({tz})"

    await message.answer(
        "⚙️ <b>Настройки</b>\n\n"
        f"🌍 Часовой пояс: <code>{tz}</code>\n"
        f"🔔 Напоминания: {remind_line}\n\n"
        "Команды:\n"
        "<code>/timezone Europe/Moscow</code>\n"
        "<code>/remind 19</code> — напоминать в 19:00 по твоему поясу\n"
        "<code>/remind off</code> — выключить",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("timezone"))
async def cmd_timezone(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Укажи часовой пояс, например: <code>/timezone Europe/Moscow</code>\n"
            "Или: <code>/timezone Asia/Bangkok</code>",
            parse_mode="HTML",
        )
        return
    tz = parts[1].strip()
    if not validate_timezone(tz):
        await message.answer(
            "Неизвестный часовой пояс. Пример: <code>Europe/Moscow</code>, "
            "<code>Asia/Bangkok</code>, <code>UTC</code>",
            parse_mode="HTML",
        )
        return
    await database.set_user_timezone(message.from_user.id, tz)
    await message.answer(f"✅ Часовой пояс обновлён: {tz}")


@router.message(Command("remind"))
async def cmd_remind(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Примеры:\n"
            "<code>/remind 19</code> — в 19:00 по твоему поясу\n"
            "<code>/remind off</code> — выключить",
            parse_mode="HTML",
        )
        return
    arg = parts[1].strip().lower()
    if arg in ("off", "stop", "выкл", "нет"):
        await database.set_reminder_hour(message.from_user.id, None)
        await message.answer("🔕 Напоминания выключены.")
        return
    try:
        hour = int(arg.split(":")[0])
    except ValueError:
        await message.answer("Укажи час от 0 до 23, например <code>/remind 19</code>", parse_mode="HTML")
        return
    if not 0 <= hour <= 23:
        await message.answer("Час должен быть от 0 до 23.")
        return

    user = await database.get_or_create_user(
        message.from_user.id,
        message.from_user.full_name or "Музыкант",
    )
    tz = user["timezone"] or config.DEFAULT_TIMEZONE
    await database.set_reminder_hour(message.from_user.id, hour)
    await message.answer(
        f"🔔 Готово! Буду напоминать каждый день в <b>{hour:02d}:00</b> ({tz}),\n"
        "если ты ещё не прошёл план.\n"
        "Выключить: <code>/remind off</code>",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "remind_plan")
async def remind_open_plan(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    from handlers.lesson import start_lesson
    await start_lesson(callback.message, state)


@router.callback_query(F.data == "remind_off")
async def remind_disable(callback: CallbackQuery) -> None:
    await database.set_reminder_hour(callback.from_user.id, None)
    await callback.answer("Напоминания выключены")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("🔕 Напоминания выключены. Включить: /remind 19")
    except Exception:
        pass


@router.message(F.voice)
async def handle_free_voice_command(message: Message, state: FSMContext, bot) -> None:
    if not config.GROQ_API_KEY:
        await message.answer(
            "🎙 Я получил голосовое сообщение, но сейчас не в разделе с тренировкой. "
            "Выбери раздел на клавиатуре ниже 👇",
            reply_markup=main_menu_keyboard(),
        )
        return

    async with download_voice(bot, message.voice.file_id, "cmd") as local_path:
        text = await transcribe_voice_command(local_path)

    if not text:
        await message.answer(
            "Не получилось распознать голосовую команду. Выбери раздел на клавиатуре 👇",
            reply_markup=main_menu_keyboard(),
        )
        return

    section = route_command_text(text)
    if section:
        await message.answer(f"🎙 Понял: «{text}». Открываю {SECTION_NAMES[section]}...")
        await _dispatch_section(section, message, state)
    else:
        await message.answer(
            f"🎙 Распознал: «{text}», но не понял раздел. Выбери на клавиатуре 👇",
            reply_markup=main_menu_keyboard(),
        )


async def _dispatch_section(section: str, message: Message, state: FSMContext) -> None:
    from handlers import (
        chords,
        degrees,
        dictation,
        harmony,
        intervals,
        intonation,
        lesson,
        melodies,
        notation,
        rhythm,
        singing,
        stats,
        theory,
        weakspots,
    )

    dispatch = {
        "lesson": lesson.start_lesson,
        "weakspots": weakspots.start_weakspots,
        "intervals": intervals.start_intervals,
        "degrees": degrees.start_degrees,
        "chords": chords.start_chords,
        "harmony": harmony.start_harmony,
        "rhythm": rhythm.start_rhythm,
        "singing": singing.start_singing,
        "intonation": intonation.start_intonation,
        "notation": notation.start_notation,
        "melodies": melodies.start_melodies,
        "dictation": dictation.start_dictation,
        "theory": theory.start_theory,
        "stats": stats.show_stats,
    }
    handler = dispatch.get(section)
    if handler:
        await handler(message, state)
