"""
Тренировка распознавания типов аккордов на слух.
Адаптивная сложность и FSM-сессия.
"""
import random

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database
from services import audio_gen
from services.exercise import format_result_message, record_answer, session_data_from_result
from utils.helpers import chords_for_level, note_freq, random_base_note, semitone_shift
from utils.keyboards import chord_choice_keyboard, training_keyboard
from utils.media import send_voice_file
from utils.states import ChordStates

router = Router(name="chords")


async def _user_level(user_id: int) -> int:
    user = await database.get_user(user_id)
    return int(user["level"]) if user else 1


async def _new_chord_exercise(message: Message, state: FSMContext, user_id: int) -> None:
    level = await _user_level(user_id)
    pool = chords_for_level(level)
    chord_name, semitone_list = random.choice(list(pool.items()))
    base_note = random_base_note("C3", "C4")
    base_freq = note_freq(base_note)
    freqs = [base_freq] + [semitone_shift(base_note, s)[1] for s in semitone_list[1:]]

    samples = audio_gen.synth_chord(freqs, duration_ms=1400)
    ogg_path = await audio_gen.save_as_voice_ogg(samples)

    await state.update_data(
        exercise_type="chords",
        expected=chord_name,
        question=f"{base_note}: {chord_name}",
        replay_freqs=freqs,
        replay_mode="chord",
        user_id=user_id,
    )
    await state.set_state(ChordStates.waiting_for_answer)

    await send_voice_file(
        message,
        ogg_path,
        caption="🎹 Послушай аккорд и определи его тип:",
        reply_markup=chord_choice_keyboard(pool),
    )


@router.message(F.text == "🎹 Аккорды")
async def start_chords(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    await state.set_data({
        "session_correct": 0,
        "session_total": 0,
        "exercise_type": "chords",
        "user_id": user_id,
    })
    level = await _user_level(user_id)
    await message.answer(
        f"Режим аккордов (уровень {level}). Сложность растёт вместе с тобой.",
        reply_markup=training_keyboard(with_replay=True),
    )
    await _new_chord_exercise(message, state, user_id)


@router.callback_query(ChordStates.waiting_for_answer, F.data.startswith("chord_ans:"))
async def check_chord_answer(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    expected = data.get("expected")
    user_id = callback.from_user.id
    if not expected:
        await callback.answer("Сессия устарела, начнём заново.")
        await state.set_data({
            "session_correct": 0,
            "session_total": 0,
            "exercise_type": "chords",
            "user_id": user_id,
        })
        await _new_chord_exercise(callback.message, state, user_id)
        return

    chosen = callback.data.split(":", 1)[1]
    is_correct = chosen == expected
    feedback = (
        f"✅ Верно! Это «{expected}»."
        if is_correct
        else f"❌ Неверно. Правильный ответ: «{expected}»."
    )

    result = await record_answer(
        user_id=user_id,
        exercise_type="chords",
        question=data.get("question", ""),
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
    await _new_chord_exercise(callback.message, state, user_id)
