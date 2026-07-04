"""
Общие действия во время тренировки: стоп сессии, повтор звука.
"""
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from services import audio_gen
from services.exercise import session_summary_text
from utils.helpers import BTN_REPLAY, BTN_STOP, SECTION_LABELS
from utils.keyboards import main_menu_keyboard
from utils.media import send_voice_file
from utils.states import TRAINING_STATES

router = Router(name="common")


@router.message(F.text == BTN_STOP)
async def stop_training(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    exercise_type = data.get("exercise_type", "")
    label = SECTION_LABELS.get(exercise_type, "тренировка")
    correct = int(data.get("session_correct", 0))
    total = int(data.get("session_total", 0))
    await state.clear()
    await message.answer(
        session_summary_text(correct, total, label),
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(StateFilter(*TRAINING_STATES), F.text == BTN_REPLAY)
async def replay_audio(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    freqs = data.get("replay_freqs")
    mode = data.get("replay_mode", "sequence")
    if not freqs and mode not in ("context", "progression", "fet"):
        await message.answer("Сейчас нечего повторять — начни упражнение заново.")
        return

    if mode == "chord":
        samples = audio_gen.synth_chord(freqs, duration_ms=1400)
    elif mode == "tone":
        samples = audio_gen.synth_tone(freqs[0], duration_ms=1200)
    elif mode == "rhythm":
        samples = audio_gen.synth_rhythm_pattern(freqs)
    elif mode == "fet":
        chords = data.get("replay_chords") or []
        target = (freqs or [None])[0]
        if not chords or not target:
            await message.answer("Сейчас нечего повторять.")
            return
        samples = audio_gen.synth_fet_question(chords, target)
    elif mode == "melody":
        chords = data.get("replay_chords") or []
        rhythm = data.get("replay_rhythm") or [1.0] * len(freqs or [])
        if not chords or not freqs:
            await message.answer("Сейчас нечего повторять.")
            return
        samples = audio_gen.synth_melody_with_cadence(chords, freqs, rhythm)
    elif mode == "progression":
        chords = data.get("replay_chords") or []
        if not chords:
            await message.answer("Сейчас нечего повторять.")
            return
        samples = audio_gen.synth_chord_progression(
            chords, context_freqs=data.get("replay_context")
        )
    elif mode == "context":
        context = data.get("replay_context") or []
        target = freqs or data.get("replay_target") or []
        if not target:
            await message.answer("Сейчас нечего повторять.")
            return
        samples = audio_gen.synth_with_context(
            context,
            target,
            target_as_chord=bool(data.get("replay_target_as_chord")),
            target_note_ms=int(data.get("replay_target_ms", 700)),
        )
    else:
        samples = audio_gen.synth_sequence(freqs, note_duration_ms=600, gap_ms=150)

    ogg_path = await audio_gen.save_as_voice_ogg(samples)
    await send_voice_file(message, ogg_path, caption="🔁 Повтор:")
