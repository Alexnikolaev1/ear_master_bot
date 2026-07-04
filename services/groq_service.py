"""
services/groq_service.py
Распознавание голосовых команд пользователя через Groq Whisper (бесплатный тариф, высокие лимиты).

Используется, когда пользователь присылает голосовое сообщение вне контекста
упражнения на интонацию (например, чтобы сказать "тренировка интервалов" голосом).
"""
import asyncio
import config
from utils.rate_limiter import RateLimiter

_rate_limiter = RateLimiter(max_calls=config.GROQ_MAX_CALLS_PER_MIN, period_sec=60)

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not config.GROQ_API_KEY:
        return None
    from groq import Groq
    _client = Groq(api_key=config.GROQ_API_KEY)
    return _client


def _transcribe_sync(file_path: str) -> str:
    client = _get_client()
    if client is None:
        raise RuntimeError("Groq API не настроен (отсутствует GROQ_API_KEY).")
    with open(file_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            file=(file_path, f.read()),
            model="whisper-large-v3-turbo",
            language="ru",
            response_format="text",
        )
    # В зависимости от версии SDK результат может быть строкой или объектом с .text
    return transcription if isinstance(transcription, str) else getattr(transcription, "text", str(transcription))


async def transcribe_voice_command(file_path: str):
    """Распознаёт голосовую команду. Возвращает None, если лимит исчерпан или сервис недоступен."""
    if not _rate_limiter.allow():
        return None
    try:
        return await asyncio.to_thread(_transcribe_sync, file_path)
    except Exception:
        return None


# Простая маршрутизация распознанного текста к разделам бота (ключевые слова)
COMMAND_KEYWORDS = {
    "урок": "lesson",
    "план": "lesson",
    "ритуал": "lesson",
    "слаб": "weakspots",
    "ошибк": "weakspots",
    "интервал": "intervals",
    "ступен": "degrees",
    "тональн": "degrees",
    "аккорд": "chords",
    "гармон": "harmony",
    "каденц": "harmony",
    "ритм": "rhythm",
    "пение": "singing",
    "спой": "singing",
    "интонац": "intonation",
    "диктант": "dictation",
    "мелодии": "melodies",
    "мелодию": "melodies",
    "песн": "melodies",
    "теори": "theory",
    "прогресс": "stats",
    "статистик": "stats",
    "ноты": "notation",
    "нотн": "notation",
}


def route_command_text(text: str):
    """Определяет, к какому разделу относится распознанная голосовая команда."""
    lowered = text.lower()
    for keyword, section in COMMAND_KEYWORDS.items():
        if keyword in lowered:
            return section
    return None
