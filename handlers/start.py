"""
handlers/start.py
Команда /start, приветствие и профиль пользователя.
"""
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from utils.keyboards import main_menu_keyboard

router = Router(name="start")


WELCOME_TEXT = (
    "🎧 <b>Добро пожаловать в EAR MASTER AI!</b>\n\n"
    "Персональный тренер музыкального слуха: не только угадывание, "
    "но и функциональный слух, пение, диктант и работа над ошибками.\n\n"
    "<b>С чего начать:</b>\n"
    "🧠 <b>План на сегодня</b> — персональный ритуал (~10 мин) от AI-тренера\n"
    "💪 <b>Слабые места</b> — бьём точно в твои ошибки\n"
    "🎼 <b>Ступени</b> — FET + внутренний слух (метод Benbassat)\n\n"
    "<b>Тренировки:</b>\n"
    "🎵 Интервалы · 🎹 Аккорды · 🏛 Гармония\n"
    "🥁 Ритм · 🎤 Пение · 📖 Ноты · 🎶 Мелодии\n"
    "✍️ Диктант · 📚 Теория · 📊 Прогресс\n\n"
    "Во время тренировки: «⏹ Стоп» — итог, «🔁 Повторить» — звук ещё раз.\n"
    "Выбери раздел 👇"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard(), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "🧠 <b>План на сегодня</b> — умный ритуал под твои слабые места.\n"
        "💪 <b>Слабые места</b> — spaced repetition по ошибкам.\n"
        "🎼 <b>Ступени</b> — FET: обычный / внутренний / представь.\n"
        "🎶 <b>Мелодии</b> — угадай / 3 ступени / спой начало.\n"
        "🎤 <b>Пение</b> — спой интервал или ступень.\n"
        "✍️ <b>Диктант</b> — запомни мелодический контур.\n"
        "🏛 <b>Гармония</b> — обращения и каденции.\n"
        "🔔 <code>/remind 19</code> — ежедневное напоминание.\n\n"
        "При ошибках бот объясняет, почему легко перепутать (AI-тренер).\n"
        "В голосовых разделах отвечай 🎙.",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
