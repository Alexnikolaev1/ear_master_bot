"""
services/gemini_service.py
Обёртка над Google Gemini 1.5 Flash (бесплатный тариф) для:
- объяснения музыкальной теории по запросу пользователя
- генерации персональных рекомендаций на основе истории ошибок
- мотивационных сообщений

Кэшируем ответы на объяснения теории на 30 дней (см. database.cache_*),
так как одинаковые вопросы задают многие пользователи, а квота Gemini free ограничена.
"""
import hashlib
import asyncio

import config
import database
from utils.rate_limiter import RateLimiter, DailyCounter

_rate_limiter = RateLimiter(max_calls=config.GEMINI_MAX_CALLS_PER_MIN, period_sec=60)
_daily_counter = DailyCounter(max_per_day=config.GEMINI_MAX_CALLS_PER_DAY)

_model = None


def _get_model():
    """Ленивая инициализация модели Gemini (чтобы не падать при импорте без ключа)."""
    global _model
    if _model is not None:
        return _model
    if not config.GEMINI_API_KEY:
        return None
    import google.generativeai as genai
    genai.configure(api_key=config.GEMINI_API_KEY)
    _model = genai.GenerativeModel("gemini-1.5-flash")
    return _model


def _cache_key(prompt: str) -> str:
    return "gemini:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _call_gemini_sync(prompt: str) -> str:
    model = _get_model()
    if model is None:
        raise RuntimeError("Gemini API не настроен (отсутствует GEMINI_API_KEY).")
    response = model.generate_content(prompt)
    return response.text.strip()


async def _call_with_limits(prompt: str) -> str:
    if not _rate_limiter.allow() or not _daily_counter.allow():
        return (
            "⏳ Сейчас слишком много запросов к AI-объяснению. "
            "Попробуйте, пожалуйста, через минуту — а пока потренируйтесь на слух!"
        )
    try:
        return await asyncio.to_thread(_call_gemini_sync, prompt)
    except Exception as e:
        return f"😔 Не получилось получить объяснение от AI прямо сейчас ({e}). Попробуйте позже."


async def explain_theory(question: str) -> str:
    """Объясняет теоретический музыкальный вопрос пользователя, используя кэш."""
    prompt = (
        "Ты — дружелюбный преподаватель музыкальной теории и сольфеджио. "
        "Объясни простым языком, с примерами, следующий вопрос ученика. "
        "Отвечай кратко (не более 6-8 предложений), но по существу, на русском языке.\n\n"
        f"Вопрос ученика: {question}"
    )
    key = _cache_key(prompt)
    cached = await database.cache_get(key)
    if cached:
        return cached

    answer = await _call_with_limits(prompt)
    if answer and not answer.startswith("⏳") and not answer.startswith("😔"):
        await database.cache_set(key, answer)
    return answer


async def suggest_training_plan(weak_areas_summary: str) -> str:
    """Генерирует персональную рекомендацию по тренировке на основе слабых мест ученика."""
    prompt = (
        "Ты — персональный AI-тренер по музыкальному слуху. "
        "На основе статистики ошибок ученика ниже, дай короткую (3-5 предложений) "
        "персональную рекомендацию, что ему стоит потренировать сегодня и почему. "
        "Будь мотивирующим и конкретным. Ответ на русском.\n\n"
        f"Статистика ученика:\n{weak_areas_summary}"
    )
    return await _call_with_limits(prompt)


async def motivational_message(context_summary: str) -> str:
    """Короткое мотивирующее сообщение (например, при достижении streak или после сложной тренировки)."""
    prompt = (
        "Напиши одно короткое (1-2 предложения) тёплое мотивирующее сообщение музыканту "
        "на русском языке, с лёгким юмором, по поводу следующего события: "
        f"{context_summary}"
    )
    return await _call_with_limits(prompt)


async def explain_confusion(
    *,
    exercise_type: str,
    expected: str,
    chosen: str,
    context: str = "",
) -> str:
    """
    Короткий AI-разбор типичной ошибки слуха (кэшируется по паре expected/chosen).
    Возвращает пустую строку при лимитах/ошибке — вызывающий код использует fallback.
    """
    if not expected or not chosen or expected == chosen:
        return ""
    prompt = (
        "Ты — опытный преподаватель сольфеджио и функционального слуха (movable-do, FET). "
        "Ученик ошибся в упражнении. Объясни ЗА 2–3 коротких предложения на русском:\n"
        "1) чем на слух отличаются правильный и выбранный ответ;\n"
        "2) какой «якорь» или ощущение поможет не путать их в следующий раз.\n"
        "Без вступлений и списков — только суть, дружелюбно.\n\n"
        f"Тип упражнения: {exercise_type}\n"
        f"Правильный ответ: {expected}\n"
        f"Ответ ученика: {chosen}\n"
        f"Контекст: {context or 'нет'}"
    )
    key = _cache_key(prompt)
    cached = await database.cache_get(key)
    if cached:
        return cached

    answer = await _call_with_limits(prompt)
    if not answer or answer.startswith("⏳") or answer.startswith("😔"):
        return ""
    # обрезаем на всякий случай
    answer = answer.strip()
    if len(answer) > 500:
        answer = answer[:497] + "…"
    await database.cache_set(key, answer, ttl_days=60)
    return answer
