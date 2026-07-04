"""
🧠 План на сегодня — персональный ритуал от тренерского мозга.
Собирается по слабым местам, точности и уровню; ведёт по шагам до финала.
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import asdict

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
import database
from services import audio_gen
from services.coach import PlanStep, build_daily_plan, pedagogical_tip_async, ritual_closing
from services.exercise import format_result_message, record_answer, session_data_from_result
from services.music_theory import (
    DEGREE_LABELS,
    METER_PATTERNS,
    degree_from_label,
    degrees_for_level,
    fet_cadence_chords,
    pick_weighted_item,
    random_tonic,
    resolution_freqs,
    scale_note,
)
from services.pitch_analysis import PitchAnalysisError, analyze_pitch
from services.rhythm_analysis import RhythmAnalysisError, analyze_rhythm
from utils.helpers import (
    INTERVALS,
    cents_feedback_text,
    intervals_for_level,
    note_freq,
    random_base_note,
    rhythm_patterns_for_level,
    semitone_shift,
)
from utils.keyboards import choice_keyboard, main_menu_keyboard, training_keyboard
from utils.media import download_voice, send_voice_file
from utils.states import LessonStates

router = Router(name="lesson")


def _steps_from_data(data: dict) -> list[PlanStep]:
    raw = data.get("plan_steps") or []
    return [PlanStep(**s) for s in raw]


async def start_lesson(message: Message, state: FSMContext) -> None:
    """Точка входа (меню + голосовые команды)."""
    user_id = message.from_user.id
    already = await database.plan_done_today(user_id)
    plan = await build_daily_plan(user_id)

    lines = [plan.intro, ""]
    for i, step in enumerate(plan.steps, 1):
        lines.append(f"{i}. <b>{step.title}</b> — {step.detail} (~{step.minutes} мин)")
    if already:
        lines.append("\n✅ Сегодня план уже отмечался — можно пройти ещё раз для закрепления.")
    lines.append("\nПоехали!")

    await state.set_data({
        "session_correct": 0,
        "session_total": 0,
        "exercise_type": "plan",
        "plan_steps": [asdict(s) for s in plan.steps],
        "plan_step_idx": 0,
        "step_left": plan.steps[0].count,
        "focus_summary": plan.focus_summary,
        "user_id": user_id,
    })
    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=training_keyboard(with_replay=True),
    )
    await _run_current(message, state, user_id)


@router.message(F.text.in_({"🧠 План на сегодня", "🎯 Урок дня"}))
async def start_plan_btn(message: Message, state: FSMContext) -> None:
    await start_lesson(message, state)


async def _run_current(message: Message, state: FSMContext, user_id: int) -> None:
    data = await state.get_data()
    steps = _steps_from_data(data)
    idx = int(data.get("plan_step_idx", 0))
    if idx >= len(steps):
        await _finish_plan(message, state, user_id)
        return

    step = steps[idx]
    left = int(data.get("step_left", step.count))
    await message.answer(
        f"📍 <b>{step.title}</b> ({step.count - left + 1}/{step.count})\n{step.detail}",
        parse_mode="HTML",
    )
    await state.update_data(step_kind=step.kind, focus=step.focus)

    if step.kind == "intonation":
        await _q_intonation(message, state, user_id)
    elif step.kind in ("fet", "fet_inner"):
        await _q_fet(message, state, user_id, inner=(step.kind == "fet_inner"))
    elif step.kind in ("interval", "harmony"):
        await _q_interval(message, state, user_id, focus=step.focus)
    elif step.kind == "melodies":
        await _q_melody(message, state, user_id)
    elif step.kind == "singing":
        await _q_singing(message, state, user_id)
    else:
        await _q_rhythm(message, state, user_id)


async def _after_question(message: Message, state: FSMContext, user_id: int) -> None:
    data = await state.get_data()
    left = int(data.get("step_left", 1)) - 1
    if left > 0:
        await state.update_data(step_left=left)
        await _run_current(message, state, user_id)
        return

    steps = _steps_from_data(data)
    idx = int(data.get("plan_step_idx", 0)) + 1
    if idx >= len(steps):
        await state.update_data(plan_step_idx=idx)
        await _finish_plan(message, state, user_id)
        return

    next_step = steps[idx]
    await state.update_data(plan_step_idx=idx, step_left=next_step.count)
    await message.answer(f"⏭ Далее: <b>{next_step.title}</b>", parse_mode="HTML")
    await _run_current(message, state, user_id)


async def _finish_plan(message: Message, state: FSMContext, user_id: int) -> None:
    data = await state.get_data()
    correct = int(data.get("session_correct", 0))
    total = int(data.get("session_total", 0))
    focus = data.get("focus_summary", "общий баланс")

    first_today = await database.save_daily_plan(user_id, focus, correct, total)
    await database.update_streak(user_id)
    await database.add_user_xp(user_id, 30 if first_today else 15)
    await database.log_exercise(
        user_id=user_id,
        exercise_type="plan",
        question="daily_plan",
        expected="complete",
        user_answer=f"{correct}/{total}",
        is_correct=True,
    )

    user = await database.get_user(user_id)
    streak = int(user["streak"]) if user else 0
    plan_streak = await database.get_plan_streak(user_id)

    text = ritual_closing(correct, total, streak, focus)
    text += f"\n📅 Планов подряд: <b>{plan_streak}</b>"
    if first_today:
        text += "\n+30 XP за ритуал дня"
        if plan_streak in (3, 7, 14, 30):
            title = f"🧠 Ритуал {plan_streak} дней"
            if await database.grant_achievement(user_id, f"plan_streak_{plan_streak}", title):
                text += f"\n🏆 Достижение: «{title}»!"
    else:
        text += "\n+15 XP за повторную сессию"

    await state.clear()
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_keyboard())


# ----- генераторы вопросов -----

async def _q_intonation(message, state, user_id) -> None:
    note = random_base_note("C3", "C5")
    freq = note_freq(note)
    ogg = await audio_gen.save_as_voice_ogg(audio_gen.synth_tone(freq, duration_ms=1100))
    await state.update_data(
        expected=note, target_freq=freq,
        replay_freqs=[freq], replay_mode="tone",
    )
    await state.set_state(LessonStates.waiting_for_voice)
    await send_voice_file(message, ogg, caption=f"🎤 Спой ноту {note}")


async def _q_fet(message, state, user_id, *, inner: bool) -> None:
    data = await state.get_data()
    focus = data.get("focus")
    level = 1
    user = await database.get_user(user_id)
    if user:
        level = int(user["level"])
    degrees = degrees_for_level(level)
    if focus:
        d = degree_from_label(focus)
        degree = d if d else random.choice(degrees)
        if degree not in degrees:
            degrees = sorted(set(degrees + [degree]))
    else:
        weak = await database.get_weak_items(user_id, "degrees")
        names = []
        for w in weak:
            d = degree_from_label(w["expected"])
            if d:
                names.append(DEGREE_LABELS[d])
        labels = [DEGREE_LABELS[d] for d in degrees]
        degree = degree_from_label(pick_weighted_item(labels, names)) or random.choice(degrees)

    tonic = random_tonic()
    cadence = fet_cadence_chords(tonic)
    _, target = scale_note(tonic, degree)
    samples = audio_gen.synth_fet_question(cadence, target)
    ogg = await audio_gen.save_as_voice_ogg(samples)
    labels = [DEGREE_LABELS[d] for d in degrees]

    await state.update_data(
        expected=DEGREE_LABELS[degree],
        tonic=tonic,
        degree=degree,
        replay_mode="fet",
        replay_chords=cadence,
        replay_freqs=[target],
        step_kind="fet_inner" if inner else "fet",
    )
    await state.set_state(LessonStates.waiting_for_answer)

    if inner:
        await send_voice_file(
            message, ogg,
            caption=f"🧘 {tonic[0]} major — удержи ступень в голове...",
        )
        await message.answer("🧘 …")
        await asyncio.sleep(2.5)
        await message.answer(
            "Какая это была ступень?",
            reply_markup=choice_keyboard(labels, "plan_ans"),
        )
    else:
        await send_voice_file(
            message, ogg,
            caption=f"🧬 FET · {tonic[0]} major — какая ступень?",
            reply_markup=choice_keyboard(labels, "plan_ans"),
        )


async def _q_interval(message, state, user_id, focus: str | None = None) -> None:
    user = await database.get_user(user_id)
    level = int(user["level"]) if user else 1
    pool = intervals_for_level(level)
    if focus and focus in pool:
        name = focus
    else:
        weak = await database.get_recent_wrong_expected(user_id, "intervals")
        name = pick_weighted_item(list(pool.keys()), weak)
    semitones = pool.get(name) or INTERVALS.get(name) or 7
    if name not in pool and name in INTERVALS:
        semitones = INTERVALS[name]
        pool = {**pool, name: semitones}
    base = random_base_note("C3", "C4")
    note2, freq2 = semitone_shift(base, semitones)
    freqs = [note_freq(base), freq2]
    ogg = await audio_gen.save_as_voice_ogg(
        audio_gen.synth_sequence(freqs, note_duration_ms=600, gap_ms=150)
    )
    await state.update_data(
        expected=name,
        replay_freqs=freqs,
        replay_mode="sequence",
        step_kind="interval",
    )
    await state.set_state(LessonStates.waiting_for_answer)
    await send_voice_file(
        message, ogg,
        caption="🎵 Какой интервал?",
        reply_markup=choice_keyboard(list(pool.keys()), "plan_ans"),
    )


async def _q_melody(message, state, user_id) -> None:
    from handlers.melodies import _melody_keyboard
    from services.melodies import ID_TO_TITLE, build_melody_audio_plan, melody_options, pick_melody

    user = await database.get_user(user_id)
    level = int(user["level"]) if user else 1
    melody = pick_melody(level)
    plan = build_melody_audio_plan(melody)
    samples = audio_gen.synth_melody_with_cadence(
        plan["cadence"], plan["freqs"], plan["rhythm"], quarter_ms=300
    )
    ogg = await audio_gen.save_as_voice_ogg(samples)
    options = melody_options(melody, level=level)
    await state.update_data(
        expected=melody["id"],
        expected_title=melody["title"],
        replay_mode="melody",
        replay_chords=plan["cadence"],
        replay_freqs=plan["freqs"],
        replay_rhythm=plan["rhythm"],
        step_kind="melodies",
        _id_to_title=ID_TO_TITLE,
    )
    await state.set_state(LessonStates.waiting_for_answer)
    await send_voice_file(
        message, ogg,
        caption=f"🎶 {plan['tonic'][0]} major — какая мелодия?",
        reply_markup=_melody_keyboard(options),
    )


async def _q_singing(message, state, user_id) -> None:
    base = random_base_note("C3", "A3")
    name, semitones = random.choice([
        (k, v) for k, v in intervals_for_level(3).items() if v > 0
    ] or [("Чистая квинта", 7)])
    target_name, target_freq = semitone_shift(base, semitones)
    ogg = await audio_gen.save_as_voice_ogg(
        audio_gen.synth_tone(note_freq(base), duration_ms=1000)
    )
    await state.update_data(
        expected=name,
        target_freq=target_freq,
        target_note=target_name,
        replay_freqs=[note_freq(base)],
        replay_mode="tone",
        step_kind="singing",
    )
    await state.set_state(LessonStates.waiting_for_voice)
    await send_voice_file(
        message, ogg,
        caption=f"🎤 Спой «{name}» вверх от {base}",
    )


async def _q_rhythm(message, state, user_id) -> None:
    user = await database.get_user(user_id)
    level = int(user["level"]) if user else 1
    if random.random() < 0.5:
        pattern = random.choice(rhythm_patterns_for_level(level))
        ogg = await audio_gen.save_as_voice_ogg(audio_gen.synth_rhythm_pattern(pattern))
        await state.update_data(
            expected_pattern=pattern,
            expected="rhythm",
            replay_freqs=pattern,
            replay_mode="rhythm",
            step_kind="rhythm",
        )
        await state.set_state(LessonStates.waiting_for_voice)
        await send_voice_file(message, ogg, caption="🥁 Повтори ритм голосом/хлопками")
    else:
        meter = random.choice(list(METER_PATTERNS.keys()))
        pattern = random.choice(METER_PATTERNS[meter])
        ogg = await audio_gen.save_as_voice_ogg(audio_gen.synth_rhythm_pattern(pattern))
        await state.update_data(
            expected=meter,
            replay_freqs=pattern,
            replay_mode="rhythm",
            step_kind="meter",
        )
        await state.set_state(LessonStates.waiting_for_answer)
        await send_voice_file(
            message, ogg,
            caption="⏱ Какой размер?",
            reply_markup=choice_keyboard(list(METER_PATTERNS.keys()), "plan_ans"),
        )


async def _record_and_feedback(
    message: Message,
    state: FSMContext,
    user_id: int,
    *,
    expected: str,
    chosen: str,
    is_correct: bool,
    feedback: str,
    profile_type: str | None = None,
    deviation_cents=None,
) -> None:
    data = await state.get_data()
    kind = data.get("step_kind", "plan")
    if not is_correct:
        tip = await pedagogical_tip_async(
            expected, chosen, profile_type or kind,
            context=kind,
        )
        if tip:
            feedback = f"{feedback}\n\n{tip}"

    result = await record_answer(
        user_id=user_id,
        exercise_type="plan",
        question=kind,
        expected=str(expected),
        user_answer=str(chosen),
        is_correct=is_correct,
        feedback=feedback,
        deviation_cents=deviation_cents,
        session_correct=int(data.get("session_correct", 0)),
        session_total=int(data.get("session_total", 0)),
    )
    if profile_type:
        await database.log_exercise(
            user_id=user_id,
            exercise_type=profile_type,
            question=kind,
            expected=str(expected),
            user_answer=str(chosen),
            is_correct=is_correct,
            deviation_cents=deviation_cents,
        )
    await state.update_data(**session_data_from_result(result))
    await message.answer(format_result_message(result), parse_mode="HTML")

    if kind in ("fet", "fet_inner") and data.get("tonic") and data.get("degree"):
        res = resolution_freqs(data["tonic"], int(data["degree"]))
        res_ogg = await audio_gen.save_as_voice_ogg(
            audio_gen.synth_sequence(res, note_duration_ms=300, gap_ms=40)
        )
        await send_voice_file(message, res_ogg, caption="🧲 Разрешение → тоника")


@router.callback_query(
    LessonStates.waiting_for_answer,
    F.data.startswith("plan_ans:") | F.data.startswith("melody_ans:"),
)
async def plan_button(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    expected = data.get("expected")
    user_id = callback.from_user.id
    chosen = callback.data.split(":", 1)[1]
    kind = data.get("step_kind", "")

    # мелодии хранят id, для отображения — title
    display_expected = data.get("expected_title") or expected
    display_chosen = chosen
    if kind == "melodies":
        from services.melodies import ID_TO_TITLE
        display_chosen = ID_TO_TITLE.get(chosen, chosen)
        display_expected = data.get("expected_title") or ID_TO_TITLE.get(expected, expected)

    is_correct = chosen == expected
    if is_correct:
        feedback = f"✅ Верно! ({display_expected})"
    else:
        feedback = f"❌ Правильно: {display_expected}."

    profile = {
        "fet": "degrees", "fet_inner": "degrees",
        "interval": "intervals", "meter": "meter",
        "melodies": "melodies",
    }.get(kind)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _record_and_feedback(
        callback.message, state, user_id,
        expected=str(display_expected), chosen=str(display_chosen),
        is_correct=is_correct, feedback=feedback,
        profile_type=profile,
    )
    await _after_question(callback.message, state, user_id)


@router.message(LessonStates.waiting_for_voice, F.voice)
async def plan_voice(message: Message, state: FSMContext, bot) -> None:
    data = await state.get_data()
    user_id = message.from_user.id
    kind = data.get("step_kind")

    if message.voice.duration > config.MAX_VOICE_DURATION_SEC:
        await message.answer("⏱ Запись слишком длинная.")
        return

    processing = await message.answer("🎧 Анализирую...")

    if kind in ("intonation", "singing"):
        target_freq = data.get("target_freq")
        try:
            async with download_voice(bot, message.voice.file_id, "plan_in") as path:
                pitch = await analyze_pitch(path, target_freq)
        except PitchAnalysisError as e:
            await processing.edit_text(f"😔 {e}\nПопробуй ещё раз.")
            return
        deviation = pitch["deviation_cents"]
        tol = config.CENTS_TOLERANCE_OK + (5 if kind == "singing" else 0)
        is_correct = abs(deviation) <= tol
        feedback = cents_feedback_text(deviation)
        await processing.delete()
        await _record_and_feedback(
            message, state, user_id,
            expected=str(data.get("expected")),
            chosen=f"{pitch['median_hz']:.1f}",
            is_correct=is_correct,
            feedback=feedback,
            profile_type="intonation" if kind == "intonation" else "singing",
            deviation_cents=deviation,
        )
    else:
        pattern = data.get("expected_pattern")
        try:
            async with download_voice(bot, message.voice.file_id, "plan_in") as path:
                analysis = await analyze_rhythm(path, pattern)
        except RhythmAnalysisError as e:
            await processing.edit_text(f"😔 {e}\nЕщё раз.")
            return
        is_correct = analysis["avg_error_pct"] <= 30
        feedback = (
            f"✅ Принято (погрешность {analysis['avg_error_pct']:.0f}%)."
            if is_correct
            else f"🔶 Погрешность {analysis['avg_error_pct']:.0f}% — идём дальше."
        )
        await processing.delete()
        await _record_and_feedback(
            message, state, user_id,
            expected=str(pattern),
            chosen=str(analysis["user_intervals_ms"]),
            is_correct=is_correct,
            feedback=feedback,
            profile_type="rhythm",
        )

    await _after_question(message, state, user_id)


@router.message(LessonStates.waiting_for_voice)
async def plan_need_voice(message: Message) -> None:
    await message.answer("Нужно голосовое сообщение 🎙.")
