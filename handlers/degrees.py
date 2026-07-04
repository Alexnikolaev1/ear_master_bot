"""
Functional Ear Training (Alain Benbassat) + режимы внутреннего слуха.

Режимы:
- 🧬 Обычный FET: каденция → ступень → ответ → разрешение
- 🧘 Внутренний: каденция → ступень → пауза (удержи в голове) → ответ
- 🔮 Представь: каденция → представь названную ступень → проверка звуком
"""
from __future__ import annotations

import asyncio
import random

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import database
from services import audio_gen
from services.coach import pedagogical_tip_async
from services.exercise import format_result_message, record_answer, session_data_from_result
from services.music_theory import (
    DEGREE_LABELS,
    degree_from_label,
    degrees_for_fet_mastery,
    fet_cadence_chords,
    pick_weighted_item,
    random_tonic,
    resolution_freqs,
    resolution_path,
    scale_note,
)
from utils.helpers import BTN_FET_INNER, BTN_FET_NORMAL, BTN_FET_IMAGINE
from utils.keyboards import choice_keyboard, training_keyboard
from utils.media import send_voice_file
from utils.states import DegreeStates

router = Router(name="degrees")


async def _user_level(user_id: int) -> int:
    user = await database.get_user(user_id)
    return int(user["level"]) if user else 1


async def _degrees_accuracy(user_id: int) -> float:
    summary = await database.get_accuracy_summary(user_id, limit_per_type=30)
    for row in summary:
        if row["exercise_type"] == "degrees":
            return float(row["accuracy"]) / 100.0
    return 0.0


def _fet_training_keyboard() -> object:
    return training_keyboard(with_replay=True, with_fet_modes=True)


async def _pick_degree(user_id: int, focus: str | None = None) -> tuple[int, list[int]]:
    level = await _user_level(user_id)
    accuracy = await _degrees_accuracy(user_id)
    degrees = degrees_for_fet_mastery(accuracy, level)
    if focus:
        d = degree_from_label(focus)
        if d and d in degrees:
            return d, degrees
        if d:
            return d, sorted(set(degrees + [d]))
    weak_rows = await database.get_weak_items(user_id, "degrees")
    weak_names = []
    for w in weak_rows:
        nd = degree_from_label(w["expected"])
        if nd:
            weak_names.append(DEGREE_LABELS[nd])
    labels = [DEGREE_LABELS[d] for d in degrees]
    expected_label = pick_weighted_item(labels, weak_names)
    degree = degree_from_label(expected_label) or random.choice(degrees)
    return degree, degrees


async def _new_degree_exercise(
    message: Message,
    state: FSMContext,
    user_id: int,
    *,
    focus: str | None = None,
) -> None:
    data = await state.get_data()
    fet_mode = data.get("fet_mode", "normal")
    degree, degrees = await _pick_degree(user_id, focus or data.get("focus"))
    tonic = random_tonic()
    cadence = fet_cadence_chords(tonic)
    _, target_freq = scale_note(tonic, degree)
    labels = [DEGREE_LABELS[d] for d in degrees]

    await state.update_data(
        exercise_type="degrees",
        expected=DEGREE_LABELS[degree],
        question=f"FET:{fet_mode} tonic={tonic} degree={degree}",
        tonic=tonic,
        degree=degree,
        replay_mode="fet",
        replay_chords=cadence,
        replay_freqs=[target_freq],
        user_id=user_id,
        focus=focus or data.get("focus"),
    )

    if fet_mode == "imagine":
        # Каденция без цели — пользователь представляет названную ступень
        samples = audio_gen.synth_chord_progression(cadence, chord_ms=650, gap_ms=90)
        ogg_path = await audio_gen.save_as_voice_ogg(samples)
        await state.set_state(DegreeStates.waiting_for_imagine)
        await send_voice_file(
            message,
            ogg_path,
            caption=f"🔮 Тональность {tonic[0]} major — представь ступень внутри",
        )
        await message.answer(
            f"🔮 Представь внутри: <b>{DEGREE_LABELS[degree]}</b>\n"
            "Когда образ ясен — нажми кнопку.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Готов — проверить звуком", callback_data="imagine_ready")]
            ]),
        )
        return

    # normal / inner: полный FET-вопрос
    samples = audio_gen.synth_fet_question(cadence, target_freq)
    ogg_path = await audio_gen.save_as_voice_ogg(samples)
    await state.set_state(DegreeStates.waiting_for_answer)

    if fet_mode == "inner":
        await send_voice_file(
            message,
            ogg_path,
            caption=(
                f"🧘 Внутренний слух · {tonic[0]} major\n"
                "Каденция и ступень прозвучали. Удержи звук в голове..."
            ),
        )
        await message.answer("🧘 …держи образ…")
        await asyncio.sleep(2.5)
        await message.answer(
            "Какая это была ступень?",
            reply_markup=choice_keyboard(labels, "degree_ans"),
        )
    else:
        pool_hint = ", ".join(DEGREE_LABELS[d].split()[0] for d in degrees)
        await send_voice_file(
            message,
            ogg_path,
            caption=(
                f"🧬 FET · {tonic[0]} major\n"
                f"Каденция I–IV–V–I, затем ступень. Пул: {pool_hint}"
            ),
            reply_markup=choice_keyboard(labels, "degree_ans"),
        )


@router.message(F.text == "🎼 Ступени")
async def start_degrees(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    await state.set_data({
        "session_correct": 0,
        "session_total": 0,
        "exercise_type": "degrees",
        "fet_mode": "normal",
        "user_id": user_id,
    })
    level = await _user_level(user_id)
    await message.answer(
        "🧬 <b>Functional Ear Training</b> (Benbassat)\n\n"
        "• <b>🧬 Обычный</b> — каденция → ступень → ответ → разрешение\n"
        "• <b>🧘 Внутренний</b> — удержи звук в голове, потом ответь\n"
        "• <b>🔮 Представь</b> — сначала образ внутри, потом проверка\n\n"
        f"Уровень {level}. 10 минут в день — сильнее часа раз в неделю.",
        parse_mode="HTML",
        reply_markup=_fet_training_keyboard(),
    )
    await _new_degree_exercise(message, state, user_id)


_FET_STATES = StateFilter(
    DegreeStates.waiting_for_answer,
    DegreeStates.waiting_for_imagine,
    DegreeStates.waiting_for_imagine_result,
)


@router.message(_FET_STATES, F.text == BTN_FET_NORMAL)
async def mode_normal(message: Message, state: FSMContext) -> None:
    await state.update_data(fet_mode="normal")
    await message.answer("🧬 Режим: обычный FET")
    await _new_degree_exercise(message, state, message.from_user.id)


@router.message(_FET_STATES, F.text == BTN_FET_INNER)
async def mode_inner(message: Message, state: FSMContext) -> None:
    await state.update_data(fet_mode="inner")
    await message.answer("🧘 Режим: внутренний слух (аудиация)")
    await _new_degree_exercise(message, state, message.from_user.id)


@router.message(_FET_STATES, F.text == BTN_FET_IMAGINE)
async def mode_imagine(message: Message, state: FSMContext) -> None:
    await state.update_data(fet_mode="imagine")
    await message.answer("🔮 Режим: представь ступень, потом проверь")
    await _new_degree_exercise(message, state, message.from_user.id)


async def _finish_answer(
    message: Message,
    state: FSMContext,
    user_id: int,
    chosen: str,
    *,
    is_correct: bool,
    feedback: str,
) -> None:
    data = await state.get_data()
    expected = data.get("expected", "")
    if not is_correct:
        tip = await pedagogical_tip_async(
            expected, chosen, "degrees",
            context=data.get("question", ""),
        )
        if tip:
            feedback = f"{feedback}\n\n{tip}"

    result = await record_answer(
        user_id=user_id,
        exercise_type="degrees",
        question=data.get("question", ""),
        expected=expected,
        user_answer=chosen,
        is_correct=is_correct,
        feedback=feedback,
        session_correct=int(data.get("session_correct", 0)),
        session_total=int(data.get("session_total", 0)),
    )
    await state.update_data(**session_data_from_result(result))
    await message.answer(format_result_message(result), parse_mode="HTML")

    degree = int(data.get("degree") or 1)
    tonic = data.get("tonic") or random_tonic()
    res_freqs = resolution_freqs(tonic, degree)
    res_ogg = await audio_gen.save_as_voice_ogg(
        audio_gen.synth_sequence(res_freqs, note_duration_ms=320, gap_ms=40)
    )
    await send_voice_file(message, res_ogg, caption="🧲 Гравитация → тоника")
    await _new_degree_exercise(message, state, user_id)


@router.callback_query(DegreeStates.waiting_for_answer, F.data.startswith("degree_ans:"))
async def check_degree(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    expected = data.get("expected")
    user_id = callback.from_user.id
    if not expected:
        await callback.answer("Сессия устарела.")
        await _new_degree_exercise(callback.message, state, user_id)
        return

    chosen = callback.data.split(":", 1)[1]
    is_correct = chosen == expected
    degree = int(data.get("degree") or 1)
    path = resolution_path(degree)
    path_text = "→".join(DEGREE_LABELS[d].split()[0] for d in path)

    if is_correct:
        feedback = f"✅ Верно! Это <b>{expected}</b>.\n🎧 Разрешение: {path_text}"
    else:
        feedback = (
            f"❌ Это было <b>{expected}</b> (ты выбрал «{chosen}»).\n"
            f"🎧 Разрешение: {path_text}"
        )

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _finish_answer(
        callback.message, state, user_id, chosen,
        is_correct=is_correct, feedback=feedback,
    )


@router.callback_query(DegreeStates.waiting_for_imagine, F.data == "imagine_ready")
async def imagine_ready(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = callback.from_user.id
    degree = int(data.get("degree") or 1)
    tonic = data.get("tonic")
    target_freq = (data.get("replay_freqs") or [None])[0]
    if not tonic or not target_freq:
        await callback.answer("Сессия устарела")
        await _new_degree_exercise(callback.message, state, user_id)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()

    # Проигрываем загаданную ступень
    probe = audio_gen.synth_tone(target_freq, duration_ms=1000)
    ogg = await audio_gen.save_as_voice_ogg(probe)
    await send_voice_file(
        callback.message,
        ogg,
        caption=f"Эталон: {DEGREE_LABELS[degree]}. Совпало с твоим образом?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Совпало", callback_data="imagine_ok"),
                InlineKeyboardButton(text="❌ Не совпало", callback_data="imagine_no"),
            ]
        ]),
    )
    await state.set_state(DegreeStates.waiting_for_imagine_result)


@router.callback_query(DegreeStates.waiting_for_imagine_result, F.data.in_({"imagine_ok", "imagine_no"}))
async def imagine_result(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    user_id = callback.from_user.id
    expected = data.get("expected", "")
    matched = callback.data == "imagine_ok"
    feedback = (
        f"✅ Образ совпал с {expected}. Так и тренируется внутренний слух!"
        if matched
        else (
            f"🔶 Образ пока плывёт. Ещё раз представь {expected}, "
            "пропой «внутри», затем послушай разрешение."
        )
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _finish_answer(
        callback.message, state, user_id,
        chosen="matched" if matched else "missed",
        is_correct=matched,
        feedback=feedback,
    )
