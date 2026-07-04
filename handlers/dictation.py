"""
Мелодический диктант: короткая фраза по ступеням → выбор контура.
"""
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database
from services import audio_gen
from services.exercise import format_result_message, record_answer, session_data_from_result
from services.music_theory import (
    melody_options,
    patterns_for_level,
    pick_weighted_item,
    random_tonic,
    scale_freqs,
    tonic_context_freqs,
)
from utils.keyboards import choice_keyboard, training_keyboard
from utils.media import send_voice_file
from utils.states import DictationStates

router = Router(name="dictation")


async def _user_level(user_id: int) -> int:
    user = await database.get_user(user_id)
    return int(user["level"]) if user else 1


async def _new_dictation(message: Message, state: FSMContext, user_id: int) -> None:
    level = await _user_level(user_id)
    pool = patterns_for_level(level)
    weak_rows = await database.get_weak_items(user_id, "dictation")
    weak_names = [w["expected"] for w in weak_rows]
    label = pick_weighted_item([p[0] for p in pool], weak_names)
    degrees = dict(pool)[label]

    tonic = random_tonic()
    context = tonic_context_freqs(tonic)
    melody = scale_freqs(tonic, degrees)
    samples = audio_gen.synth_with_context(
        context, melody, target_note_ms=450, target_gap_ms=80
    )
    ogg_path = await audio_gen.save_as_voice_ogg(samples)
    options = melody_options(label, pool, count=4)

    await state.update_data(
        exercise_type="dictation",
        expected=label,
        question=f"{tonic} {label}",
        replay_mode="context",
        replay_context=context,
        replay_freqs=melody,
        replay_target_ms=450,
        user_id=user_id,
    )
    await state.set_state(DictationStates.waiting_for_answer)

    await send_voice_file(
        message,
        ogg_path,
        caption=(
            f"✍️ Мелодический диктант (тональность {tonic[0]} major).\n"
            "Сначала контекст, затем мелодия. Какой контур по ступеням?"
        ),
        reply_markup=choice_keyboard(options, "dictation_ans"),
    )


@router.message(F.text == "✍️ Диктант")
async def start_dictation(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    await state.set_data({
        "session_correct": 0,
        "session_total": 0,
        "exercise_type": "dictation",
        "user_id": user_id,
    })
    await message.answer(
        "Мелодический диктант: запомни короткую фразу и выбери контур по ступеням.",
        reply_markup=training_keyboard(with_replay=True),
    )
    await _new_dictation(message, state, user_id)


@router.callback_query(DictationStates.waiting_for_answer, F.data.startswith("dictation_ans:"))
async def check_dictation(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    expected = data.get("expected")
    user_id = callback.from_user.id
    if not expected:
        await callback.answer("Сессия устарела.")
        await _new_dictation(callback.message, state, user_id)
        return

    chosen = callback.data.split(":", 1)[1]
    is_correct = chosen == expected
    feedback = (
        f"✅ Верно! Контур: {expected}."
        if is_correct
        else f"❌ Неверно. Правильный контур: {expected}."
    )
    result = await record_answer(
        user_id=user_id,
        exercise_type="dictation",
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
    await _new_dictation(callback.message, state, user_id)
