"""
Тренировка распознавания интервалов на слух.
Адаптивная сложность, мелодический/гармонический режим, FSM-сессия.
"""
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database
from services import audio_gen
from services.exercise import format_result_message, record_answer, session_data_from_result
from services.coach import pedagogical_tip_async
from services.music_theory import pick_weighted_item
from utils.helpers import (
    BTN_HARMONIC,
    BTN_MELODIC,
    intervals_for_level,
    note_freq,
    note_range_for_level,
    random_base_note,
    semitone_shift,
)
from utils.keyboards import interval_choice_keyboard, training_keyboard
from utils.media import send_voice_file
from utils.states import IntervalStates

router = Router(name="intervals")


async def _user_level(user_id: int) -> int:
    user = await database.get_user(user_id)
    return int(user["level"]) if user else 1


async def _new_interval_exercise(message: Message, state: FSMContext, user_id: int) -> None:
    data = await state.get_data()
    level = await _user_level(user_id)
    pool = intervals_for_level(level)
    mode = data.get("interval_mode", "melodic")

    weak_rows = await database.get_weak_items(user_id, "intervals")
    recent_wrong = await database.get_recent_wrong_expected(user_id, "intervals", limit=3)
    weak_names = [w["expected"] for w in weak_rows] + recent_wrong
    interval_name = pick_weighted_item(list(pool.keys()), weak_names)
    semitones = pool[interval_name]
    low, high = note_range_for_level(level)
    try:
        base_note = random_base_note(low, high)
        note2_name, freq2 = semitone_shift(base_note, semitones)
        if note2_name.endswith("п/т"):
            base_note = random_base_note(low, "C4")
            note2_name, freq2 = semitone_shift(base_note, semitones)
    except (KeyError, ValueError):
        base_note = "C4"
        note2_name, freq2 = semitone_shift(base_note, semitones)

    freq1 = note_freq(base_note)
    freqs = [freq1, freq2]

    if mode == "harmonic":
        samples = audio_gen.synth_chord(freqs, duration_ms=1200)
        caption = "🎵 Послушай гармонический интервал (оба тона вместе) и выбери ответ:"
        replay_mode = "chord"
    else:
        samples = audio_gen.synth_sequence(freqs, note_duration_ms=600, gap_ms=150)
        caption = "🎵 Послушай мелодический интервал и выбери ответ:"
        replay_mode = "sequence"

    ogg_path = await audio_gen.save_as_voice_ogg(samples)

    await state.update_data(
        exercise_type="intervals",
        expected=interval_name,
        question=f"{base_note} -> {note2_name} ({mode})",
        replay_freqs=freqs,
        replay_mode=replay_mode,
        interval_mode=mode,
        user_id=user_id,
    )
    await state.set_state(IntervalStates.waiting_for_answer)

    await send_voice_file(
        message,
        ogg_path,
        caption=caption,
        reply_markup=interval_choice_keyboard(pool),
    )


@router.message(F.text == "🎵 Интервалы")
async def start_intervals(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    data = await state.get_data()
    await state.set_data({
        "session_correct": 0,
        "session_total": 0,
        "interval_mode": data.get("interval_mode", "melodic"),
        "exercise_type": "intervals",
        "user_id": user_id,
    })
    level = await _user_level(user_id)
    mode = data.get("interval_mode", "melodic")
    mode_label = "мелодический" if mode == "melodic" else "гармонический"
    await message.answer(
        f"Режим интервалов (уровень {level}, {mode_label}).\n"
        f"Сложность подстраивается автоматически.",
        reply_markup=training_keyboard(with_replay=True, with_mode=True),
    )
    await _new_interval_exercise(message, state, user_id)


@router.message(IntervalStates.waiting_for_answer, F.text == BTN_MELODIC)
async def set_melodic(message: Message, state: FSMContext) -> None:
    await state.update_data(interval_mode="melodic")
    await message.answer("🎶 Режим: мелодический (тона по очереди).")
    await _new_interval_exercise(message, state, message.from_user.id)


@router.message(IntervalStates.waiting_for_answer, F.text == BTN_HARMONIC)
async def set_harmonic(message: Message, state: FSMContext) -> None:
    await state.update_data(interval_mode="harmonic")
    await message.answer("🎼 Режим: гармонический (тона вместе).")
    await _new_interval_exercise(message, state, message.from_user.id)


@router.callback_query(IntervalStates.waiting_for_answer, F.data.startswith("interval_ans:"))
async def check_interval_answer(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    expected = data.get("expected")
    user_id = callback.from_user.id
    if not expected:
        await callback.answer("Сессия устарела, начнём заново.")
        await state.set_data({
            "session_correct": 0,
            "session_total": 0,
            "interval_mode": "melodic",
            "exercise_type": "intervals",
            "user_id": user_id,
        })
        await _new_interval_exercise(callback.message, state, user_id)
        return

    chosen = callback.data.split(":", 1)[1]
    is_correct = chosen == expected
    feedback = (
        f"✅ Верно! Это действительно «{expected}»."
        if is_correct
        else f"❌ Не совсем. Правильный ответ: «{expected}» (ты выбрал «{chosen}»)."
    )
    if not is_correct:
        tip = await pedagogical_tip_async(
            expected, chosen, "intervals",
            context=data.get("question", ""),
        )
        if tip:
            feedback = f"{feedback}\n\n{tip}"

    result = await record_answer(
        user_id=user_id,
        exercise_type="intervals",
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
    await _new_interval_exercise(callback.message, state, user_id)
