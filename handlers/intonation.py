"""
Тренировка интонации: эталонная нота → пение → анализ высоты тона в центах.
"""
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import config
import database
from services import audio_gen
from services.exercise import format_result_message, record_answer, session_data_from_result
from services.pitch_analysis import PitchAnalysisError, analyze_pitch
from utils.helpers import cents_feedback_text, note_freq, note_range_for_level, random_base_note
from utils.keyboards import training_keyboard
from utils.media import download_voice, send_voice_file
from utils.states import IntonationStates

router = Router(name="intonation")


async def _user_level(user_id: int) -> int:
    user = await database.get_user(user_id)
    return int(user["level"]) if user else 1


async def _new_intonation_exercise(message: Message, state: FSMContext, user_id: int) -> None:
    level = await _user_level(user_id)
    low, high = note_range_for_level(level)
    # для пения удобнее средние ноты
    try:
        target_note = random_base_note(low, high)
    except ValueError:
        target_note = random_base_note("C3", "C5")
    target_freq = note_freq(target_note)

    samples = audio_gen.synth_tone(target_freq, duration_ms=1200)
    ogg_path = await audio_gen.save_as_voice_ogg(samples)

    await state.update_data(
        exercise_type="intonation",
        target_note=target_note,
        target_freq=target_freq,
        replay_freqs=[target_freq],
        replay_mode="tone",
        user_id=user_id,
    )
    await state.set_state(IntonationStates.waiting_for_voice)

    await send_voice_file(
        message,
        ogg_path,
        caption=(
            f"🎤 Спой ноту, которую услышал ({target_note}), и отправь голосовым сообщением.\n"
            "Пой ровно на одной высоте 2–3 секунды, без слов — просто «а-а-а»."
        ),
    )


@router.message(F.text == "🎤 Интонация")
async def start_intonation(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    await state.set_data({
        "session_correct": 0,
        "session_total": 0,
        "exercise_type": "intonation",
        "user_id": user_id,
    })
    level = await _user_level(user_id)
    await message.answer(
        f"Режим интонации (уровень {level}). Спой ноту — я скажу отклонение в центах.",
        reply_markup=training_keyboard(with_replay=True),
    )
    await _new_intonation_exercise(message, state, user_id)


@router.message(IntonationStates.waiting_for_voice, F.voice)
async def check_intonation_answer(message: Message, state: FSMContext, bot) -> None:
    data = await state.get_data()
    target_note = data.get("target_note")
    target_freq = data.get("target_freq")
    if target_freq is None:
        await message.answer("Что-то пошло не так — нажми «🎤 Интонация».")
        await state.clear()
        return

    if message.voice.duration > config.MAX_VOICE_DURATION_SEC:
        await message.answer(
            f"⏱ Запись длиннее {config.MAX_VOICE_DURATION_SEC} секунд — запиши покороче."
        )
        return

    processing_msg = await message.answer("🎧 Слушаю твоё пение...")

    try:
        async with download_voice(bot, message.voice.file_id, "intonation_in") as local_path:
            pitch = await analyze_pitch(local_path, target_freq)
    except PitchAnalysisError as e:
        await processing_msg.edit_text(
            f"😔 {e}\nПопробуй перезаписать, спев чуть громче и дольше."
        )
        return

    deviation = pitch["deviation_cents"]
    is_correct = abs(deviation) <= config.CENTS_TOLERANCE_OK
    feedback = cents_feedback_text(deviation)

    result = await record_answer(
        user_id=message.from_user.id,
        exercise_type="intonation",
        question=target_note,
        expected=target_note,
        user_answer=f"{pitch['median_hz']:.1f} Hz",
        is_correct=is_correct,
        feedback=feedback,
        deviation_cents=deviation,
        session_correct=int(data.get("session_correct", 0)),
        session_total=int(data.get("session_total", 0)),
    )
    await state.update_data(**session_data_from_result(result))

    await processing_msg.edit_text(format_result_message(result), parse_mode="HTML")

    if abs(deviation) > config.CENTS_TOLERANCE_CLOSE:
        ref_samples = audio_gen.synth_tone(target_freq, duration_ms=1000)
        ref_ogg = await audio_gen.save_as_voice_ogg(ref_samples)
        await send_voice_file(
            message,
            ref_ogg,
            caption=f"Вот эталонная нота {target_note} ещё раз — попробуй ещё разок 🎯",
        )

    await _new_intonation_exercise(message, state, message.from_user.id)


@router.message(IntonationStates.waiting_for_voice)
async def intonation_wrong_content(message: Message) -> None:
    await message.answer("Пожалуйста, отправь голосовое сообщение 🎙 с пением ноты.")
