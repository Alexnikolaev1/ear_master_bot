"""
Раздел «Теория»: вопрос текстом → Gemini → опциональная озвучка edge-tts.
"""
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from services.gemini_service import explain_theory
from services.tts import synthesize_speech
from utils.helpers import BTN_REPLAY, BTN_STOP
from utils.keyboards import training_keyboard
from utils.media import send_audio_file
from utils.states import TheoryStates

router = Router(name="theory")


@router.message(F.text == "📚 Теория")
async def start_theory(message: Message, state: FSMContext) -> None:
    await state.set_data({"exercise_type": "theory", "session_correct": 0, "session_total": 0})
    await state.set_state(TheoryStates.waiting_for_question)
    await message.answer(
        "📚 Задай любой вопрос по теории музыки — например:\n"
        "«Что такое тритон?», «Как строить квинтовый круг?», "
        "«Чем отличается лад от тональности?»\n\n"
        "Нажми «⏹ Стоп», чтобы вернуться в меню.",
        reply_markup=training_keyboard(with_replay=False),
    )


@router.message(
    TheoryStates.waiting_for_question,
    F.text,
    ~F.text.in_({BTN_STOP, BTN_REPLAY}),
)
async def answer_theory_question(message: Message, state: FSMContext) -> None:
    processing = await message.answer("🤔 Думаю над ответом...")
    answer = await explain_theory(message.text)
    # Telegram лимит ~4096 символов
    if len(answer) > 4000:
        answer = answer[:3990] + "…"
    await processing.edit_text(answer)

    try:
        mp3_path = await synthesize_speech(answer[:500])  # TTS — краткая версия
        await send_audio_file(message, mp3_path, title="Объяснение теории")
    except Exception:
        pass

    await message.answer("Можешь задать ещё один вопрос или нажать «⏹ Стоп».")
