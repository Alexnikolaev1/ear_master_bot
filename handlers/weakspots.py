"""
Режим «Слабые места»: spaced repetition по ошибкам пользователя.
"""
import random

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database
from services import audio_gen
from services.exercise import format_result_message, record_answer, session_data_from_result
from services.music_theory import (
    CADENCES,
    DEGREE_LABELS,
    INVERSIONS,
    MELODY_PATTERNS,
    cadence_chord_freqs,
    degree_from_label,
    fet_cadence_chords,
    inversion_freqs,
    random_tonic,
    resolution_freqs,
    scale_freqs,
    tonic_context_freqs,
)
from utils.helpers import INTERVALS, note_freq, random_base_note, semitone_shift
from utils.keyboards import choice_keyboard, training_keyboard
from utils.media import send_voice_file
from utils.states import WeakSpotStates

router = Router(name="weakspots")


async def _new_weak_exercise(message: Message, state: FSMContext, user_id: int) -> None:
    weak = await database.get_weak_items(user_id, limit=20)
    if not weak:
        # нет статистики — даём случайный интервал как старт
        await message.answer(
            "Пока мало ошибок для анализа — потренируй интервалы и ступени, "
            "и слабые места появятся сами. Даю разминку по интервалам."
        )
        item = {"exercise_type": "intervals", "expected": random.choice(list(INTERVALS.keys()))}
    else:
        # взвешенный выбор: чем ниже accuracy, тем чаще
        weights = [max(0.05, 1.0 - float(w["accuracy"])) for w in weak]
        item = random.choices(weak, weights=weights, k=1)[0]

    ex_type = item["exercise_type"]
    expected = item["expected"]

    # нормализуем типы, которые мапим на кнопки
    if ex_type in ("intervals", "weakspots") and expected in INTERVALS:
        await _play_interval(message, state, user_id, expected)
    elif ex_type == "degrees" and degree_from_label(expected):
        await _play_degree(message, state, user_id, expected)
    elif ex_type == "harmony" and expected in INVERSIONS:
        await _play_inversion(message, state, user_id, expected)
    elif ex_type == "harmony" and expected in CADENCES:
        await _play_cadence(message, state, user_id, expected)
    elif ex_type == "dictation" and expected in dict(MELODY_PATTERNS):
        await _play_dictation(message, state, user_id, expected)
    elif expected in INTERVALS:
        await _play_interval(message, state, user_id, expected)
    else:
        # fallback
        await _play_interval(message, state, user_id, random.choice(list(INTERVALS.keys())))


async def _play_interval(message, state, user_id, expected: str) -> None:
    semitones = INTERVALS[expected]
    base = random_base_note("C3", "C5")
    note2, freq2 = semitone_shift(base, semitones)
    freqs = [note_freq(base), freq2]
    samples = audio_gen.synth_sequence(freqs, note_duration_ms=600, gap_ms=150)
    ogg = await audio_gen.save_as_voice_ogg(samples)
    await state.update_data(
        exercise_type="weakspots",
        source_type="intervals",
        expected=expected,
        question=f"weak interval {base}",
        replay_freqs=freqs,
        replay_mode="sequence",
        options=list(INTERVALS.keys()),
        prefix="weak_ans",
        user_id=user_id,
    )
    await state.set_state(WeakSpotStates.waiting_for_answer)
    await send_voice_file(
        message, ogg,
        caption="💪 Слабое место: интервалы. Что это?",
        reply_markup=choice_keyboard(list(INTERVALS.keys()), "weak_ans"),
    )


async def _play_degree(message, state, user_id, expected: str) -> None:
    degree = degree_from_label(expected)
    if not degree:
        degree = 1
    # всегда отвечаем в актуальных подписях FET
    expected = DEGREE_LABELS[degree]
    tonic = random_tonic()
    cadence = fet_cadence_chords(tonic)
    from services.music_theory import scale_note
    _, target = scale_note(tonic, degree)
    samples = audio_gen.synth_fet_question(cadence, target)
    ogg = await audio_gen.save_as_voice_ogg(samples)
    labels = list(DEGREE_LABELS.values())
    await state.update_data(
        exercise_type="weakspots",
        source_type="degrees",
        expected=expected,
        question=f"weak degree {tonic}",
        tonic=tonic,
        degree=degree,
        replay_mode="fet",
        replay_chords=cadence,
        replay_freqs=[target],
        user_id=user_id,
    )
    await state.set_state(WeakSpotStates.waiting_for_answer)
    await send_voice_file(
        message, ogg,
        caption="💪 Слабое место (FET): каденция, затем ступень. Какая?",
        reply_markup=choice_keyboard(labels, "weak_ans"),
    )


async def _play_inversion(message, state, user_id, expected: str) -> None:
    inv = INVERSIONS[expected]
    root = random_base_note("C3", "C4")
    freqs = inversion_freqs(root, "major", inv)
    samples = audio_gen.synth_chord(freqs, duration_ms=1400)
    ogg = await audio_gen.save_as_voice_ogg(samples)
    await state.update_data(
        exercise_type="weakspots",
        source_type="harmony",
        expected=expected,
        question=f"weak inv {root}",
        replay_mode="chord",
        replay_freqs=freqs,
        user_id=user_id,
    )
    await state.set_state(WeakSpotStates.waiting_for_answer)
    await send_voice_file(
        message, ogg,
        caption="💪 Слабое место: обращения. Какое обращение?",
        reply_markup=choice_keyboard(list(INVERSIONS.keys()), "weak_ans"),
    )


async def _play_cadence(message, state, user_id, expected: str) -> None:
    degrees = CADENCES[expected]
    tonic = random_tonic()
    context = tonic_context_freqs(tonic)
    chords = [cadence_chord_freqs(tonic, d) for d in degrees]
    samples = audio_gen.synth_chord_progression(chords, context_freqs=context)
    ogg = await audio_gen.save_as_voice_ogg(samples)
    await state.update_data(
        exercise_type="weakspots",
        source_type="harmony",
        expected=expected,
        question=f"weak cadence {tonic}",
        replay_mode="progression",
        replay_context=context,
        replay_chords=chords,
        user_id=user_id,
    )
    await state.set_state(WeakSpotStates.waiting_for_answer)
    await send_voice_file(
        message, ogg,
        caption="💪 Слабое место: каденции. Какая каденция?",
        reply_markup=choice_keyboard(list(CADENCES.keys()), "weak_ans"),
    )


async def _play_dictation(message, state, user_id, expected: str) -> None:
    degrees = dict(MELODY_PATTERNS)[expected]
    tonic = random_tonic()
    context = tonic_context_freqs(tonic)
    melody = scale_freqs(tonic, degrees)
    samples = audio_gen.synth_with_context(context, melody, target_note_ms=450)
    ogg = await audio_gen.save_as_voice_ogg(samples)
    options = [expected]
    others = [p[0] for p in MELODY_PATTERNS if p[0] != expected]
    options += random.sample(others, min(3, len(others)))
    random.shuffle(options)
    await state.update_data(
        exercise_type="weakspots",
        source_type="dictation",
        expected=expected,
        question=f"weak dict {tonic}",
        replay_mode="context",
        replay_context=context,
        replay_freqs=melody,
        user_id=user_id,
    )
    await state.set_state(WeakSpotStates.waiting_for_answer)
    await send_voice_file(
        message, ogg,
        caption="💪 Слабое место: диктант. Какой контур?",
        reply_markup=choice_keyboard(options, "weak_ans"),
    )


@router.message(F.text == "💪 Слабые места")
async def start_weakspots(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    await state.set_data({
        "session_correct": 0,
        "session_total": 0,
        "exercise_type": "weakspots",
        "user_id": user_id,
    })
    weak = await database.get_weak_items(user_id, limit=5)
    if weak:
        lines = [
            f"• {w['expected']} ({w['exercise_type']}: {100 * w['accuracy']:.0f}%)"
            for w in weak[:5]
        ]
        preview = "Сейчас в фокусе:\n" + "\n".join(lines)
    else:
        preview = "Накоплю статистику ошибок и буду бить точно в слабые места."
    await message.answer(
        f"💪 Режим работы над ошибками.\n{preview}",
        reply_markup=training_keyboard(with_replay=True),
    )
    await _new_weak_exercise(message, state, user_id)


@router.callback_query(WeakSpotStates.waiting_for_answer, F.data.startswith("weak_ans:"))
async def check_weak(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    expected = data.get("expected")
    user_id = callback.from_user.id
    if not expected:
        await callback.answer("Сессия устарела.")
        await _new_weak_exercise(callback.message, state, user_id)
        return

    chosen = callback.data.split(":", 1)[1]
    is_correct = chosen == expected
    feedback = (
        f"✅ Закрепили! «{expected}»."
        if is_correct
        else f"❌ Ещё раз запомни: «{expected}» (ты выбрал «{chosen}»)."
    )
    if not is_correct:
        from services.coach import pedagogical_tip_async
        tip = await pedagogical_tip_async(
            expected, chosen, data.get("source_type") or "weakspots",
            context=data.get("question", ""),
        )
        if tip:
            feedback = f"{feedback}\n\n{tip}"

    # логируем и в weakspots, и в исходный тип — чтобы accuracy исходного типа росла
    result = await record_answer(
        user_id=user_id,
        exercise_type="weakspots",
        question=data.get("question", ""),
        expected=expected,
        user_answer=chosen,
        is_correct=is_correct,
        feedback=feedback,
        session_correct=int(data.get("session_correct", 0)),
        session_total=int(data.get("session_total", 0)),
    )
    source = data.get("source_type")
    if source and source != "weakspots":
        await database.log_exercise(
            user_id=user_id,
            exercise_type=source,
            question=data.get("question", ""),
            expected=expected,
            user_answer=chosen,
            is_correct=is_correct,
        )
    await state.update_data(**session_data_from_result(result))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(format_result_message(result), parse_mode="HTML")
    await callback.answer()

    if data.get("source_type") == "degrees" and data.get("tonic") and data.get("degree"):
        res = resolution_freqs(data["tonic"], int(data["degree"]))
        res_ogg = await audio_gen.save_as_voice_ogg(
            audio_gen.synth_sequence(res, note_duration_ms=300, gap_ms=40)
        )
        await send_voice_file(callback.message, res_ogg, caption="🧲 Разрешение → тоника")

    await _new_weak_exercise(callback.message, state, user_id)

