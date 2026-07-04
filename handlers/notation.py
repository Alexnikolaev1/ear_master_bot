"""
Тренировка чтения нот с листа: нотный стан + варианты ответа + озвучка правильной ноты.
"""
import random

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from services import audio_gen
from services.exercise import format_result_message, record_answer, session_data_from_result
from services.notation_gen import NOTATION_RANGE, render_staff_with_note
from utils.helpers import note_freq
from utils.keyboards import notation_choice_keyboard, training_keyboard
from utils.media import send_photo_file, send_voice_file
from utils.states import NotationStates

router = Router(name="notation")


async def _new_notation_exercise(message: Message, state: FSMContext, user_id: int) -> None:
    note_name = random.choice(NOTATION_RANGE)
    image_path = await render_staff_with_note(note_name)

    await state.update_data(
        exercise_type="notation",
        expected=note_name,
        replay_freqs=[note_freq(note_name)],
        replay_mode="tone",
        user_id=user_id,
    )
    await state.set_state(NotationStates.waiting_for_answer)

    await send_photo_file(
        message,
        image_path,
        caption="📖 Какая это нота на нотном стане?",
        reply_markup=notation_choice_keyboard(note_name, NOTATION_RANGE),
    )


@router.message(F.text == "📖 Ноты")
async def start_notation(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    await state.set_data({
        "session_correct": 0,
        "session_total": 0,
        "exercise_type": "notation",
        "user_id": user_id,
    })
    await message.answer(
        "Режим чтения нот с листа! Скрипичный ключ, одна нота — назови её.",
        reply_markup=training_keyboard(with_replay=True),
    )
    await _new_notation_exercise(message, state, user_id)


@router.callback_query(NotationStates.waiting_for_answer, F.data.startswith("notation_ans:"))
async def check_notation_answer(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    expected = data.get("expected")
    user_id = callback.from_user.id
    if not expected:
        await callback.answer("Сессия устарела, начнём заново.")
        await state.set_data({
            "session_correct": 0,
            "session_total": 0,
            "exercise_type": "notation",
            "user_id": user_id,
        })
        await _new_notation_exercise(callback.message, state, user_id)
        return

    chosen = callback.data.split(":", 1)[1]
    is_correct = chosen == expected
    feedback = (
        f"✅ Верно! Это нота {expected}."
        if is_correct
        else f"❌ Неверно. Правильный ответ: {expected}."
    )

    result = await record_answer(
        user_id=user_id,
        exercise_type="notation",
        question="Нотный стан: определи ноту",
        expected=expected,
        user_answer=chosen,
        is_correct=is_correct,
        feedback=feedback,
        session_correct=int(data.get("session_correct", 0)),
        session_total=int(data.get("session_total", 0)),
    )
    await state.update_data(**session_data_from_result(result), user_id=user_id)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(format_result_message(result), parse_mode="HTML")
    await callback.answer()

    # связь «нота на стане ↔ звук»
    samples = audio_gen.synth_tone(note_freq(expected), duration_ms=700)
    ogg_path = await audio_gen.save_as_voice_ogg(samples)
    await send_voice_file(callback.message, ogg_path)

    await _new_notation_exercise(callback.message, state, user_id)
