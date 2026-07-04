"""
Единый движок упражнений: логирование, streak, уровень, достижения, итог сессии.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import database

# Пороги достижений: (exercise_type, streak, code, title)
ACHIEVEMENTS = (
    ("intervals", 5, "intervals_5", "🎵 Ухо настраивается"),
    ("intervals", 10, "perfect_ear_10", "🏆 Идеальный слух"),
    ("intervals", 25, "intervals_25", "🎼 Интервальный мастер"),
    ("chords", 5, "chords_5", "🎹 Аккордовый слух"),
    ("chords", 10, "chords_10", "🎹 Гармонист"),
    ("rhythm", 5, "rhythm_machine_5", "🥁 Ритм-машина"),
    ("rhythm", 10, "rhythm_10", "🥁 Метроном"),
    ("intonation", 5, "intonation_5", "🎤 Чистый голос"),
    ("intonation", 10, "intonation_10", "🎤 Интонационный мастер"),
    ("notation", 10, "sight_reader_10", "📖 Читаю с листа"),
    ("notation", 25, "notation_25", "📖 Зрительный гений"),
    ("degrees", 10, "degrees_10", "🎼 Чувствую тональность"),
    ("harmony", 10, "harmony_10", "🏛 Гармонический слух"),
    ("dictation", 10, "dictation_10", "✍️ Мелодическая память"),
    ("singing", 10, "singing_10", "🎤 Пою интервалы"),
    ("meter", 5, "meter_5", "⏱ Чувствую размер"),
    ("weakspots", 10, "weakspots_10", "💪 Работаю над ошибками"),
    ("lesson", 5, "lesson_5", "🎯 Ученик дня"),
    ("melodies", 10, "melodies_10", "🎶 Знаю мелодии"),
    ("melodies", 25, "melodies_25", "🎶 Живая музыка"),
)

# Опыт за ответ: верный / неверный
XP_CORRECT = 10
XP_WRONG = 2
XP_PER_LEVEL = 100


@dataclass
class ExerciseResult:
    is_correct: bool
    feedback: str
    achievements: list[str] = field(default_factory=list)
    level_up: Optional[int] = None
    session_correct: int = 0
    session_total: int = 0


def session_summary_text(correct: int, total: int, exercise_label: str) -> str:
    if total <= 0:
        return f"⏹ Тренировка «{exercise_label}» завершена."
    pct = 100.0 * correct / total
    medal = "🥇" if pct >= 90 else "🥈" if pct >= 70 else "🥉" if pct >= 50 else "💪"
    return (
        f"⏹ <b>Сессия завершена</b> — {exercise_label}\n\n"
        f"{medal} Верно: <b>{correct}/{total}</b> ({pct:.0f}%)\n"
        f"Отличная работа! Возвращайся, когда будешь готов 🎶"
    )


async def record_answer(
    *,
    user_id: int,
    exercise_type: str,
    question: str,
    expected: str,
    user_answer: str,
    is_correct: bool,
    feedback: str,
    deviation_cents: Optional[float] = None,
    session_correct: int = 0,
    session_total: int = 0,
) -> ExerciseResult:
    """Логирует ответ, обновляет streak/уровень/достижения и возвращает обогащённый результат."""
    await database.log_exercise(
        user_id=user_id,
        exercise_type=exercise_type,
        question=question,
        expected=expected,
        user_answer=user_answer,
        is_correct=is_correct,
        deviation_cents=deviation_cents,
    )
    await database.update_streak(user_id)

    session_total += 1
    if is_correct:
        session_correct += 1

    xp_gain = XP_CORRECT if is_correct else XP_WRONG
    new_level = await database.add_user_xp(user_id, xp_gain)

    achievements: list[str] = []
    streak = await database.get_streak_of_correct(user_id, exercise_type)
    for ex_type, need, code, title in ACHIEVEMENTS:
        if ex_type == exercise_type and streak == need:
            granted = await database.grant_achievement(user_id, code, title)
            if granted:
                achievements.append(title)

    # достижение за серию ежедневных тренировок
    user = await database.get_user(user_id)
    if user and user["streak"] in (3, 7, 14, 30):
        code = f"daily_streak_{user['streak']}"
        title = f"🔥 Серия {user['streak']} дней"
        if await database.grant_achievement(user_id, code, title):
            achievements.append(title)

    result = ExerciseResult(
        is_correct=is_correct,
        feedback=feedback,
        achievements=achievements,
        level_up=new_level,
        session_correct=session_correct,
        session_total=session_total,
    )
    return result


def format_result_message(result: ExerciseResult) -> str:
    parts = [result.feedback]
    if result.level_up:
        parts.append(f"\n⬆ Новый уровень: <b>{result.level_up}</b>!")
    for title in result.achievements:
        parts.append(f"\n🏆 Достижение открыто: «{title}»!")
    if result.session_total > 0:
        parts.append(
            f"\n\n📊 Сессия: {result.session_correct}/{result.session_total}"
        )
    return "".join(parts)


def session_data_from_result(result: ExerciseResult) -> dict[str, Any]:
    return {
        "session_correct": result.session_correct,
        "session_total": result.session_total,
    }
