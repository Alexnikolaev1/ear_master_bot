"""
Узнаваемые мелодии:
- 🎶 Угадай мелодию
- 🎯 Первая ступень
- ✍️ 3 ступени — мини-диктант контура
- 🎤 Спой начало — активный слух на живом мотиве
"""
from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
import database
from services import audio_gen
from services.coach import pedagogical_tip_async
from services.exercise import format_result_message, record_answer, session_data_from_result
from services.melodies import (
    ID_TO_MELODY,
    ID_TO_TITLE,
    TITLE_TO_ID,
    build_melody_audio_plan,
    first_degree_options,
    melody_options,
    motif_contour,
    motif_contour_options,
    opening_target_freq,
    pick_melody,
)
from services.music_theory import DEGREE_LABELS
from services.pitch_analysis import PitchAnalysisError, analyze_pitch
from utils.helpers import (
    BTN_MELODY_DEGREE,
    BTN_MELODY_DICTATION,
    BTN_MELODY_NAME,
    BTN_MELODY_SING,
    cents_feedback_text,
)
from utils.keyboards import choice_keyboard, training_keyboard
from utils.media import download_voice, send_voice_file
from utils.states import MelodyStates

router = Router(name="melodies")

_MELODY_STATES = StateFilter(
    MelodyStates.waiting_for_answer,
    MelodyStates.waiting_for_voice,
)


def _melody_keyboard(titles: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for title in titles:
        mid = TITLE_TO_ID.get(title, title[:20])
        rows.append([InlineKeyboardButton(text=title, callback_data=f"melody_ans:{mid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _contour_keyboard(options: list[str]) -> InlineKeyboardMarkup:
    """Индекс в callback — контур хранится в FSM (лимит 64 байта)."""
    rows = []
    for i, label in enumerate(options):
        rows.append([InlineKeyboardButton(text=label, callback_data=f"mdct_ans:{i}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _melody_training_keyboard() -> object:
    return training_keyboard(with_replay=True, with_melody_modes=True)


async def _user_level(user_id: int) -> int:
    user = await database.get_user(user_id)
    return int(user["level"]) if user else 1


async def _new_melody(message: Message, state: FSMContext, user_id: int) -> None:
    data = await state.get_data()
    mode = data.get("melody_mode", "name")
    level = await _user_level(user_id)
    melody = pick_melody(level)

    if mode == "degree":
        plan = build_melody_audio_plan(melody, motif_notes=5)
        samples = audio_gen.synth_melody_with_cadence(
            plan["cadence"], plan["freqs"], plan["rhythm"], quarter_ms=300
        )
        ogg = await audio_gen.save_as_voice_ogg(samples)
        expected_label = plan["first_degree"]
        options = first_degree_options(expected_label)
        await state.update_data(
            exercise_type="melodies",
            melody_mode="degree",
            expected=expected_label,
            expected_title=melody["title"],
            melody_id=melody["id"],
            question=f"melody_deg:{melody['id']}:{plan['tonic']}",
            replay_mode="melody",
            replay_chords=plan["cadence"],
            replay_freqs=plan["freqs"],
            replay_rhythm=plan["rhythm"],
            contour_options=None,
            user_id=user_id,
        )
        await state.set_state(MelodyStates.waiting_for_answer)
        await send_voice_file(
            message,
            ogg,
            caption=(
                f"🎯 Первая ступень · {plan['tonic'][0]} major\n"
                f"Мелодия: «{melody['title']}» (начало).\n"
                "С какой ступени начинается мотив?"
            ),
            reply_markup=choice_keyboard(options, "mdeg_ans"),
        )
        return

    if mode == "dictation":
        plan = build_melody_audio_plan(melody, motif_notes=3)
        samples = audio_gen.synth_melody_with_cadence(
            plan["cadence"], plan["freqs"], plan["rhythm"], quarter_ms=340
        )
        ogg = await audio_gen.save_as_voice_ogg(samples)
        correct = motif_contour(melody, 3)
        options = motif_contour_options(melody, n=3, count=4)
        await state.update_data(
            exercise_type="melodies",
            melody_mode="dictation",
            expected=correct,
            expected_title=melody["title"],
            melody_id=melody["id"],
            question=f"melody_dict:{melody['id']}:{plan['tonic']}:{correct}",
            contour_options=options,
            replay_mode="melody",
            replay_chords=plan["cadence"],
            replay_freqs=plan["freqs"],
            replay_rhythm=plan["rhythm"],
            user_id=user_id,
        )
        await state.set_state(MelodyStates.waiting_for_answer)
        await send_voice_file(
            message,
            ogg,
            caption=(
                f"✍️ Мини-диктант · {plan['tonic'][0]} major\n"
                f"«{melody['title']}» — первые 3 ноты.\n"
                "Какой контур ступеней?"
            ),
            reply_markup=_contour_keyboard(options),
        )
        return

    if mode == "sing":
        # каденция + тоника как опора; пользователь поёт первую ноту мотива
        plan = build_melody_audio_plan(melody, motif_notes=4)
        note_name, target_freq, degree_label = opening_target_freq(melody, plan["tonic"])
        # даём каденцию и тонику, без самой мелодии — чтобы пел по памяти/названию
        # но для новичков лучше дать послушать мотив один раз, потом попросить спеть начало
        samples = audio_gen.synth_melody_with_cadence(
            plan["cadence"], plan["freqs"], plan["rhythm"], quarter_ms=300
        )
        ogg = await audio_gen.save_as_voice_ogg(samples)
        await state.update_data(
            exercise_type="melodies",
            melody_mode="sing",
            expected=degree_label,
            expected_title=melody["title"],
            melody_id=melody["id"],
            target_freq=target_freq,
            target_note=note_name,
            question=f"melody_sing:{melody['id']}:{plan['tonic']}:{degree_label}",
            replay_mode="melody",
            replay_chords=plan["cadence"],
            replay_freqs=plan["freqs"],
            replay_rhythm=plan["rhythm"],
            contour_options=None,
            user_id=user_id,
        )
        await state.set_state(MelodyStates.waiting_for_voice)
        await send_voice_file(
            message,
            ogg,
            caption=(
                f"🎤 Спой начало · {plan['tonic'][0]} major\n"
                f"«{melody['title']}» — послушай, затем спой <b>первую ноту</b> мотива "
                f"ровно 2–3 секунды на «а-а-а».\n"
                f"Запись не длиннее {config.MAX_VOICE_DURATION_SEC} с."
            ),
        )
        await message.answer(
            "Когда готов — отправь голосовое 🎙 с первой нотой мотива."
        )
        return

    # name — угадай мелодию
    plan = build_melody_audio_plan(melody)
    samples = audio_gen.synth_melody_with_cadence(
        plan["cadence"], plan["freqs"], plan["rhythm"], quarter_ms=300
    )
    ogg = await audio_gen.save_as_voice_ogg(samples)
    options = melody_options(melody, level=level)
    await state.update_data(
        exercise_type="melodies",
        melody_mode="name",
        expected=melody["id"],
        expected_title=melody["title"],
        melody_id=melody["id"],
        question=f"melody:{melody['id']}:{plan['tonic']}",
        replay_mode="melody",
        replay_chords=plan["cadence"],
        replay_freqs=plan["freqs"],
        replay_rhythm=plan["rhythm"],
        contour_options=None,
        user_id=user_id,
    )
    await state.set_state(MelodyStates.waiting_for_answer)
    await send_voice_file(
        message,
        ogg,
        caption=(
            f"🎶 Тональность {plan['tonic'][0]} major (сначала каденция).\n"
            "Какая это мелодия?"
        ),
        reply_markup=_melody_keyboard(options),
    )


@router.message(F.text == "🎶 Мелодии")
async def start_melodies(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    await state.set_data({
        "session_correct": 0,
        "session_total": 0,
        "exercise_type": "melodies",
        "melody_mode": "name",
        "user_id": user_id,
    })
    await message.answer(
        "🎶 <b>Мелодии из жизни</b>\n\n"
        "• <b>🎶 Угадай мелодию</b> — назови песню\n"
        "• <b>🎯 Первая ступень</b> — с чего начинается мотив\n"
        "• <b>✍️ 3 ступени</b> — мини-диктант контура (Do-Re-Mi…)\n"
        "• <b>🎤 Спой начало</b> — спой первую ноту мотива\n\n"
        "Так функциональный слух переносится на настоящую музыку.",
        parse_mode="HTML",
        reply_markup=_melody_training_keyboard(),
    )
    await _new_melody(message, state, user_id)


@router.message(_MELODY_STATES, F.text == BTN_MELODY_NAME)
async def mode_name(message: Message, state: FSMContext) -> None:
    await state.update_data(melody_mode="name")
    await message.answer("🎶 Режим: угадай мелодию")
    await _new_melody(message, state, message.from_user.id)


@router.message(_MELODY_STATES, F.text == BTN_MELODY_DEGREE)
async def mode_degree(message: Message, state: FSMContext) -> None:
    await state.update_data(melody_mode="degree")
    await message.answer("🎯 Режим: первая ступень мотива")
    await _new_melody(message, state, message.from_user.id)


@router.message(_MELODY_STATES, F.text == BTN_MELODY_DICTATION)
async def mode_dictation(message: Message, state: FSMContext) -> None:
    await state.update_data(melody_mode="dictation")
    await message.answer("✍️ Режим: мини-диктант — первые 3 ступени")
    await _new_melody(message, state, message.from_user.id)


@router.message(_MELODY_STATES, F.text == BTN_MELODY_SING)
async def mode_sing(message: Message, state: FSMContext) -> None:
    await state.update_data(melody_mode="sing")
    await message.answer("🎤 Режим: спой первую ноту мотива")
    await _new_melody(message, state, message.from_user.id)


async def _finish_melody_answer(
    message: Message,
    state: FSMContext,
    user_id: int,
    *,
    expected_display: str,
    chosen_display: str,
    is_correct: bool,
    feedback: str,
    tip_type: str,
    deviation_cents: float | None = None,
) -> None:
    data = await state.get_data()
    if not is_correct:
        tip = await pedagogical_tip_async(
            expected_display,
            chosen_display,
            tip_type,
            context=data.get("question", ""),
        )
        if tip:
            feedback = f"{feedback}\n\n{tip}"

    result = await record_answer(
        user_id=user_id,
        exercise_type="melodies",
        question=data.get("question", ""),
        expected=expected_display,
        user_answer=chosen_display,
        is_correct=is_correct,
        feedback=feedback,
        deviation_cents=deviation_cents,
        session_correct=int(data.get("session_correct", 0)),
        session_total=int(data.get("session_total", 0)),
    )
    # FET-связанные режимы — в лог ступеней для слабых мест
    if tip_type in ("melody_degree", "melody_dictation", "melody_sing"):
        await database.log_exercise(
            user_id=user_id,
            exercise_type="degrees",
            question=data.get("question", ""),
            expected=expected_display,
            user_answer=chosen_display,
            is_correct=is_correct,
            deviation_cents=deviation_cents,
        )
    if tip_type == "melody_sing":
        await database.log_exercise(
            user_id=user_id,
            exercise_type="singing",
            question=data.get("question", ""),
            expected=expected_display,
            user_answer=chosen_display,
            is_correct=is_correct,
            deviation_cents=deviation_cents,
        )

    await state.update_data(**session_data_from_result(result))
    await message.answer(format_result_message(result), parse_mode="HTML")
    await _new_melody(message, state, user_id)


@router.callback_query(MelodyStates.waiting_for_answer, F.data.startswith("melody_ans:"))
async def check_melody_name(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("melody_mode") != "name":
        await callback.answer()
        return

    expected_id = data.get("expected")
    expected_title = data.get("expected_title") or ID_TO_TITLE.get(expected_id, expected_id)
    user_id = callback.from_user.id
    if not expected_id:
        await callback.answer("Сессия устарела.")
        await _new_melody(callback.message, state, user_id)
        return

    chosen_id = callback.data.split(":", 1)[1]
    chosen_title = ID_TO_TITLE.get(chosen_id, chosen_id)
    is_correct = chosen_id == expected_id
    melody = ID_TO_MELODY.get(expected_id, {})
    contour = motif_contour(melody, 3) if melody.get("degrees") else ""
    if is_correct:
        feedback = f"✅ Верно! Это «{expected_title}»."
        if contour:
            feedback += f"\nНачало: <b>{contour}</b>."
    else:
        feedback = (
            f"❌ Это «{expected_title}» (ты выбрал «{chosen_title}»).\n"
            + (f"Контур начала: <b>{contour}</b>." if contour else "Послушай ещё раз.")
        )

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _finish_melody_answer(
        callback.message,
        state,
        user_id,
        expected_display=expected_title,
        chosen_display=chosen_title,
        is_correct=is_correct,
        feedback=feedback,
        tip_type="melodies",
    )


@router.callback_query(MelodyStates.waiting_for_answer, F.data.startswith("mdeg_ans:"))
async def check_melody_degree(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    expected = data.get("expected")
    title = data.get("expected_title", "")
    user_id = callback.from_user.id
    if not expected:
        await callback.answer("Сессия устарела.")
        await _new_melody(callback.message, state, user_id)
        return

    chosen = callback.data.split(":", 1)[1]
    is_correct = chosen == expected
    feedback = (
        f"✅ Верно! «{title}» начинается с <b>{expected}</b>."
        if is_correct
        else f"❌ «{title}» начинается с <b>{expected}</b> (ты выбрал «{chosen}»)."
    )

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _finish_melody_answer(
        callback.message,
        state,
        user_id,
        expected_display=expected,
        chosen_display=chosen,
        is_correct=is_correct,
        feedback=feedback,
        tip_type="melody_degree",
    )


@router.callback_query(MelodyStates.waiting_for_answer, F.data.startswith("mdct_ans:"))
async def check_melody_dictation(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    expected = data.get("expected")
    options = data.get("contour_options") or []
    title = data.get("expected_title", "")
    user_id = callback.from_user.id
    if not expected or not options:
        await callback.answer("Сессия устарела.")
        await _new_melody(callback.message, state, user_id)
        return

    try:
        idx = int(callback.data.split(":", 1)[1])
        chosen = options[idx]
    except (ValueError, IndexError):
        await callback.answer("Некорректный ответ")
        return

    is_correct = chosen == expected
    feedback = (
        f"✅ Верно! «{title}»: <b>{expected}</b>."
        if is_correct
        else f"❌ «{title}» начинается как <b>{expected}</b> (ты выбрал «{chosen}»)."
    )

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _finish_melody_answer(
        callback.message,
        state,
        user_id,
        expected_display=expected,
        chosen_display=chosen,
        is_correct=is_correct,
        feedback=feedback,
        tip_type="melody_dictation",
    )


@router.message(MelodyStates.waiting_for_voice, F.voice)
async def check_melody_sing(message: Message, state: FSMContext, bot) -> None:
    data = await state.get_data()
    if data.get("melody_mode") != "sing":
        await message.answer("Сейчас нужен другой тип ответа — переключи режим кнопками.")
        return

    target_freq = data.get("target_freq")
    expected = data.get("expected", "")
    title = data.get("expected_title", "")
    note_name = data.get("target_note", "")
    user_id = message.from_user.id

    if target_freq is None:
        await message.answer("Сессия устарела — нажми «🎶 Мелодии».")
        await state.clear()
        return

    if message.voice.duration > config.MAX_VOICE_DURATION_SEC:
        await message.answer(
            f"⏱ Запись длиннее {config.MAX_VOICE_DURATION_SEC} с — покороче, пожалуйста."
        )
        return

    processing = await message.answer("🎧 Слушаю первую ноту мотива...")
    try:
        async with download_voice(bot, message.voice.file_id, "melody_sing") as path:
            pitch = await analyze_pitch(path, target_freq)
    except PitchAnalysisError as e:
        await processing.edit_text(f"😔 {e}\nПопробуй спеть громче и ровнее.")
        return

    deviation = pitch["deviation_cents"]
    is_correct = abs(deviation) <= config.CENTS_TOLERANCE_OK + 5
    pitch_text = cents_feedback_text(deviation)
    feedback = (
        f"{pitch_text}\n"
        f"«{title}» начинается с <b>{expected}</b> ({note_name})."
    )

    await processing.delete()

    if abs(deviation) > config.CENTS_TOLERANCE_CLOSE:
        ref = audio_gen.synth_tone(target_freq, duration_ms=1000)
        ogg = await audio_gen.save_as_voice_ogg(ref)
        await send_voice_file(message, ogg, caption=f"Эталон первой ноты: {note_name}")

    await _finish_melody_answer(
        message,
        state,
        user_id,
        expected_display=expected,
        chosen_display=f"{pitch['median_hz']:.1f} Hz",
        is_correct=is_correct,
        feedback=feedback,
        tip_type="melody_sing",
        deviation_cents=deviation,
    )


@router.message(MelodyStates.waiting_for_voice)
async def melody_need_voice(message: Message) -> None:
    await message.answer("Отправь голосовое сообщение 🎙 с первой нотой мотива.")
