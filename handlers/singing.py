"""
Активное пение: спой интервал вверх или ступень в тональности.
"""
import random

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import config
import database
from services import audio_gen
from services.exercise import format_result_message, record_answer, session_data_from_result
from services.music_theory import (
    DEGREE_LABELS,
    degrees_for_level,
    fet_cadence_chords,
    random_tonic,
    scale_note,
)
from services.pitch_analysis import PitchAnalysisError, analyze_pitch
from utils.helpers import (
    INTERVALS_EASY,
    cents_feedback_text,
    intervals_for_level,
    note_freq,
    random_base_note,
    semitone_shift,
)
from utils.keyboards import training_keyboard
from utils.media import download_voice, send_voice_file
from utils.states import SingingStates

router = Router(name="singing")


async def _user_level(user_id: int) -> int:
    user = await database.get_user(user_id)
    return int(user["level"]) if user else 1


async def _new_singing(message: Message, state: FSMContext, user_id: int) -> None:
    level = await _user_level(user_id)
    # чередуем: спой интервал / спой ступень
    mode = "degree" if level >= 2 and random.random() < 0.45 else "interval"

    if mode == "interval":
        pool = intervals_for_level(level)
        # прима бессмысленна для пения «второй ноты»
        pool = {k: v for k, v in pool.items() if v > 0} or INTERVALS_EASY
        name, semitones = random.choice(list(pool.items()))
        base = random_base_note("C3", "A3")
        base_freq = note_freq(base)
        target_name, target_freq = semitone_shift(base, semitones)
        samples = audio_gen.synth_tone(base_freq, duration_ms=1100)
        caption = (
            f"🎤 Спой интервал «{name}» ВВЕРХ от услышанной ноты ({base}).\n"
            "Держи целевую ноту 2–3 секунды на «а-а-а»."
        )
        expected = name
        question = f"sing interval {base}->{target_name}"
        replay_freqs = [base_freq]
        replay_mode = "tone"
        replay_chords = None
    else:
        degrees = [d for d in degrees_for_level(level) if d != 1]
        degree = random.choice(degrees or [5])
        tonic = random_tonic(3, 3)
        cadence = fet_cadence_chords(tonic)
        target_name, target_freq = scale_note(tonic, degree)
        # FET-якорь + тоника как опора перед пением
        samples = audio_gen.synth_fet_question(cadence, note_freq(tonic), target_ms=800)
        caption = (
            f"🎤 Тональность {tonic[0]} major. Спой ступень {DEGREE_LABELS[degree]}.\n"
            "Сначала каденция I–IV–V–I и тоника — затем спой нужную ступень."
        )
        expected = DEGREE_LABELS[degree]
        question = f"sing degree {tonic} {degree}"
        replay_freqs = [note_freq(tonic)]
        replay_mode = "fet"
        replay_chords = cadence

    ogg_path = await audio_gen.save_as_voice_ogg(samples)
    await state.update_data(
        exercise_type="singing",
        expected=expected,
        question=question,
        target_freq=target_freq,
        target_note=target_name,
        singing_mode=mode,
        replay_freqs=replay_freqs,
        replay_mode=replay_mode,
        replay_chords=replay_chords,
        user_id=user_id,
    )
    await state.set_state(SingingStates.waiting_for_voice)

    await send_voice_file(message, ogg_path, caption=caption)


@router.message(F.text == "🎤 Пение")
async def start_singing(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    await state.set_data({
        "session_correct": 0,
        "session_total": 0,
        "exercise_type": "singing",
        "user_id": user_id,
    })
    await message.answer(
        "Активный слух: спой интервал или ступень. Это сильнее развивает внутренний слух, "
        "чем только угадывание кнопок.",
        reply_markup=training_keyboard(with_replay=True),
    )
    await _new_singing(message, state, user_id)


@router.message(SingingStates.waiting_for_voice, F.voice)
async def check_singing(message: Message, state: FSMContext, bot) -> None:
    data = await state.get_data()
    target_freq = data.get("target_freq")
    if target_freq is None:
        await message.answer("Что-то пошло не так — нажми «🎤 Пение».")
        await state.clear()
        return

    if message.voice.duration > config.MAX_VOICE_DURATION_SEC:
        await message.answer(
            f"⏱ Запись длиннее {config.MAX_VOICE_DURATION_SEC} секунд — запиши покороче."
        )
        return

    processing = await message.answer("🎧 Слушаю твоё пение...")
    try:
        async with download_voice(bot, message.voice.file_id, "sing_in") as path:
            pitch = await analyze_pitch(path, target_freq)
    except PitchAnalysisError as e:
        await processing.edit_text(f"😔 {e}\nПопробуй спеть громче и дольше.")
        return

    deviation = pitch["deviation_cents"]
    # для пения чуть мягче допуск
    is_correct = abs(deviation) <= config.CENTS_TOLERANCE_OK + 5
    feedback = cents_feedback_text(deviation)
    feedback = f"{feedback}\nЦель: {data.get('expected')} ({data.get('target_note')})."

    result = await record_answer(
        user_id=message.from_user.id,
        exercise_type="singing",
        question=data.get("question", ""),
        expected=data.get("expected", ""),
        user_answer=f"{pitch['median_hz']:.1f} Hz",
        is_correct=is_correct,
        feedback=feedback,
        deviation_cents=deviation,
        session_correct=int(data.get("session_correct", 0)),
        session_total=int(data.get("session_total", 0)),
    )
    await state.update_data(**session_data_from_result(result))
    await processing.edit_text(format_result_message(result), parse_mode="HTML")

    if abs(deviation) > config.CENTS_TOLERANCE_CLOSE:
        ref = audio_gen.synth_tone(target_freq, duration_ms=1000)
        ogg = await audio_gen.save_as_voice_ogg(ref)
        await send_voice_file(
            message, ogg, caption=f"Эталон: {data.get('target_note')}"
        )

    await _new_singing(message, state, message.from_user.id)


@router.message(SingingStates.waiting_for_voice)
async def singing_wrong_content(message: Message) -> None:
    await message.answer("Отправь голосовое сообщение 🎙 с пением.")
