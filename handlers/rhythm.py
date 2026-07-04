"""
Тренировка ритма: повтор рисунка голосом + определение размера такта.
"""
import random

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
import database
from services import audio_gen
from services.exercise import format_result_message, record_answer, session_data_from_result
from services.music_theory import METER_PATTERNS
from services.rhythm_analysis import RhythmAnalysisError, analyze_rhythm
from utils.helpers import BTN_METER, BTN_PATTERN, rhythm_patterns_for_level
from utils.keyboards import choice_keyboard, training_keyboard
from utils.media import download_voice, send_voice_file
from utils.states import RhythmStates

router = Router(name="rhythm")


async def _user_level(user_id: int) -> int:
    user = await database.get_user(user_id)
    return int(user["level"]) if user else 1


async def _new_pattern_exercise(message: Message, state: FSMContext, user_id: int) -> None:
    level = await _user_level(user_id)
    pattern = random.choice(rhythm_patterns_for_level(level))
    samples = audio_gen.synth_rhythm_pattern(pattern)
    ogg_path = await audio_gen.save_as_voice_ogg(samples)

    await state.update_data(
        exercise_type="rhythm",
        rhythm_mode="pattern",
        expected_pattern=pattern,
        replay_freqs=pattern,
        replay_mode="rhythm",
        user_id=user_id,
    )
    await state.set_state(RhythmStates.waiting_for_voice)

    await send_voice_file(
        message,
        ogg_path,
        caption=(
            "🥁 Послушай ритм и повтори голосовым сообщением "
            "(хлопни в ладоши или постучи по столу).\n"
            f"Запись не длиннее {config.MAX_VOICE_DURATION_SEC} секунд."
        ),
    )


async def _new_meter_exercise(message: Message, state: FSMContext, user_id: int) -> None:
    meter = random.choice(list(METER_PATTERNS.keys()))
    pattern = random.choice(METER_PATTERNS[meter])
    samples = audio_gen.synth_rhythm_pattern(pattern)
    ogg_path = await audio_gen.save_as_voice_ogg(samples)

    await state.update_data(
        exercise_type="meter",
        rhythm_mode="meter",
        expected=meter,
        replay_freqs=pattern,
        replay_mode="rhythm",
        user_id=user_id,
    )
    await state.set_state(RhythmStates.waiting_for_meter)

    await send_voice_file(
        message,
        ogg_path,
        caption="⏱ Послушай пульс. Какой размер такта?",
        reply_markup=choice_keyboard(list(METER_PATTERNS.keys()), "meter_ans"),
    )


async def _next_rhythm(message, state, user_id) -> None:
    data = await state.get_data()
    if data.get("rhythm_mode") == "meter":
        await _new_meter_exercise(message, state, user_id)
    else:
        await _new_pattern_exercise(message, state, user_id)


@router.message(F.text == "🥁 Ритм")
async def start_rhythm(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    await state.set_data({
        "session_correct": 0,
        "session_total": 0,
        "exercise_type": "rhythm",
        "rhythm_mode": "pattern",
        "user_id": user_id,
    })
    level = await _user_level(user_id)
    await message.answer(
        f"Режим ритма (уровень {level}).\n"
        "«🥁 Рисунок» — повтори хлопками, «⏱ Размер» — угадай 3/4 или 4/4.",
        reply_markup=training_keyboard(with_replay=True, with_rhythm_mode=True),
    )
    await _new_pattern_exercise(message, state, user_id)


@router.message(F.text == BTN_PATTERN)
async def switch_pattern(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = message.from_user.id
    await state.update_data(rhythm_mode="pattern", exercise_type="rhythm")
    # сохраняем сессию если уже в ритме
    if data.get("session_total") is None:
        await state.update_data(session_correct=0, session_total=0)
    await message.answer("🥁 Режим: повтор ритмического рисунка.")
    await _new_pattern_exercise(message, state, user_id)


@router.message(F.text == BTN_METER)
async def switch_meter(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = message.from_user.id
    await state.update_data(rhythm_mode="meter", exercise_type="meter")
    if data.get("session_total") is None:
        await state.update_data(session_correct=0, session_total=0)
    await message.answer("⏱ Режим: определение размера такта.")
    await _new_meter_exercise(message, state, user_id)


@router.message(RhythmStates.waiting_for_voice, F.voice)
async def check_rhythm_answer(message: Message, state: FSMContext, bot) -> None:
    data = await state.get_data()
    expected_pattern = data.get("expected_pattern")
    if not expected_pattern:
        await message.answer("Что-то пошло не так — нажми «🥁 Ритм».")
        await state.clear()
        return

    if message.voice.duration > config.MAX_VOICE_DURATION_SEC:
        await message.answer(
            f"⏱ Запись длиннее {config.MAX_VOICE_DURATION_SEC} секунд — запиши покороче."
        )
        return

    processing_msg = await message.answer("🎧 Слушаю и анализирую твой ритм...")

    try:
        async with download_voice(bot, message.voice.file_id, "rhythm_in") as local_path:
            result_analysis = await analyze_rhythm(local_path, expected_pattern)
    except RhythmAnalysisError as e:
        await processing_msg.edit_text(f"😔 {e}\nПопробуй записать ещё раз, постучав чётче.")
        return

    is_correct = result_analysis["is_correct"]
    if is_correct:
        feedback = (
            f"✅ Отлично! Ритм повторён точно "
            f"(средняя погрешность {result_analysis['avg_error_pct']:.0f}%)."
        )
    else:
        beat_hint = (
            f" Особенно неточно получился удар №{result_analysis['worst_beat_index']}."
            if result_analysis.get("worst_beat_index")
            else ""
        )
        feedback = (
            f"🔶 Есть отклонения (средняя погрешность {result_analysis['avg_error_pct']:.0f}%)."
            f"{beat_hint}\nПопробуй ещё раз, внимательно слушая исходный ритм."
        )

    result = await record_answer(
        user_id=message.from_user.id,
        exercise_type="rhythm",
        question=str(expected_pattern),
        expected=str(expected_pattern),
        user_answer=str(result_analysis["user_intervals_ms"]),
        is_correct=is_correct,
        feedback=feedback,
        session_correct=int(data.get("session_correct", 0)),
        session_total=int(data.get("session_total", 0)),
    )
    await state.update_data(**session_data_from_result(result))
    await processing_msg.edit_text(format_result_message(result), parse_mode="HTML")
    await _new_pattern_exercise(message, state, message.from_user.id)


@router.callback_query(RhythmStates.waiting_for_meter, F.data.startswith("meter_ans:"))
async def check_meter(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    expected = data.get("expected")
    user_id = callback.from_user.id
    if not expected:
        await callback.answer("Сессия устарела.")
        await _new_meter_exercise(callback.message, state, user_id)
        return

    chosen = callback.data.split(":", 1)[1]
    is_correct = chosen == expected
    feedback = (
        f"✅ Верно! Размер {expected}."
        if is_correct
        else f"❌ Неверно. Правильный размер: {expected}."
    )
    result = await record_answer(
        user_id=user_id,
        exercise_type="meter",
        question="meter",
        expected=expected,
        user_answer=chosen,
        is_correct=is_correct,
        feedback=feedback,
        session_correct=int(data.get("session_correct", 0)),
        session_total=int(data.get("session_total", 0)),
    )
    await state.update_data(**session_data_from_result(result), rhythm_mode="meter")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(format_result_message(result), parse_mode="HTML")
    await callback.answer()
    await _new_meter_exercise(callback.message, state, user_id)


@router.message(RhythmStates.waiting_for_voice)
async def rhythm_wrong_content(message: Message) -> None:
    await message.answer("Пожалуйста, отправь голосовое сообщение 🎙 с повтором ритма.")
