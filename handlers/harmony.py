"""
Гармонический слух: обращения трезвучий и каденции.
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
    INVERSIONS,
    cadence_chord_freqs,
    inversion_freqs,
    pick_weighted_item,
    random_tonic,
    tonic_context_freqs,
)
from utils.helpers import random_base_note
from utils.keyboards import choice_keyboard, training_keyboard
from utils.media import send_voice_file
from utils.states import HarmonyStates

router = Router(name="harmony")


async def _user_level(user_id: int) -> int:
    user = await database.get_user(user_id)
    return int(user["level"]) if user else 1


async def _new_harmony_exercise(message: Message, state: FSMContext, user_id: int) -> None:
    level = await _user_level(user_id)
    mode = "cadence" if level >= 3 and random.random() < 0.5 else "inversion"
    weak_rows = await database.get_weak_items(user_id, "harmony")
    weak_names = [w["expected"] for w in weak_rows]

    if mode == "inversion":
        inv_name = pick_weighted_item(list(INVERSIONS.keys()), weak_names)
        inv_idx = INVERSIONS[inv_name]
        quality = random.choice(["major", "minor"])
        root = random_base_note("C3", "C4")
        freqs = inversion_freqs(root, quality, inv_idx)
        samples = audio_gen.synth_chord(freqs, duration_ms=1500)
        caption = "🏛 Послушай трезвучие. Какое это обращение?\n(слушай нижний звук — бас)"
        options = list(INVERSIONS.keys())
        expected = inv_name
        question = f"inv {quality} {root} {inv_name}"
        await state.update_data(
            replay_mode="chord",
            replay_freqs=freqs,
            replay_context=None,
            replay_chords=None,
        )
    else:
        cad_name = pick_weighted_item(list(CADENCES.keys()), weak_names)
        degrees = CADENCES[cad_name]
        tonic = random_tonic()
        context = tonic_context_freqs(tonic)
        chords = [cadence_chord_freqs(tonic, d) for d in degrees]
        samples = audio_gen.synth_chord_progression(chords, context_freqs=context)
        caption = f"🏛 Тональность {tonic[0]} major (сначала контекст).\nКакая каденция прозвучала?"
        options = list(CADENCES.keys())
        expected = cad_name
        question = f"cadence {tonic} {cad_name}"
        await state.update_data(
            replay_mode="progression",
            replay_freqs=None,
            replay_context=context,
            replay_chords=chords,
        )

    ogg_path = await audio_gen.save_as_voice_ogg(samples)
    await state.update_data(
        exercise_type="harmony",
        expected=expected,
        question=question,
        harmony_mode=mode,
        user_id=user_id,
    )
    await state.set_state(HarmonyStates.waiting_for_answer)

    await send_voice_file(
        message,
        ogg_path,
        caption=caption,
        reply_markup=choice_keyboard(options, "harmony_ans"),
    )


@router.message(F.text == "🏛 Гармония")
async def start_harmony(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    await state.set_data({
        "session_correct": 0,
        "session_total": 0,
        "exercise_type": "harmony",
        "user_id": user_id,
    })
    await message.answer(
        "Гармонический слух: обращения трезвучий и каденции (V–I, IV–I, V–VI…).",
        reply_markup=training_keyboard(with_replay=True),
    )
    await _new_harmony_exercise(message, state, user_id)


@router.callback_query(HarmonyStates.waiting_for_answer, F.data.startswith("harmony_ans:"))
async def check_harmony(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    expected = data.get("expected")
    user_id = callback.from_user.id
    if not expected:
        await callback.answer("Сессия устарела.")
        await _new_harmony_exercise(callback.message, state, user_id)
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
        exercise_type="harmony",
        question=data.get("question", ""),
        expected=expected,
        user_answer=chosen,
        is_correct=is_correct,
        feedback=feedback,
        session_correct=int(data.get("session_correct", 0)),
        session_total=int(data.get("session_total", 0)),
    )
    await state.update_data(**session_data_from_result(result))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(format_result_message(result), parse_mode="HTML")
    await callback.answer()
    await _new_harmony_exercise(callback.message, state, user_id)
