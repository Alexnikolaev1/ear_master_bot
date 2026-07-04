"""
Тренерский мозг: персональный план на день, педагогические подсказки, ритуал.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import database
from services.music_theory import DEGREE_LABELS, degree_from_label

# Типичные путаницы ступеней (FET) — короткие подсказки «как у педагога»
DEGREE_CONFUSION_TIPS = {
    frozenset({"Fa (IV)", "Sol (V)"}): (
        "Fa мягче и «просится» вниз к Mi/Do; Sol ярче, устойчивее, как опора доминанты. "
        "Сравни: Fa тянет домой через Mi, Sol — через вводный тон или прямо в Do."
    ),
    frozenset({"Mi (III)", "Fa (IV)"}): (
        "Mi — устойчивая ступень трезвучия тоники (светлая, «на месте»). "
        "Fa на полтона выше и звучит напряжённее, как будто хочет вниз."
    ),
    frozenset({"Ti (VII)", "Do (I)"}): (
        "Ti — вводный тон: острый, тянет вверх в Do. "
        "Если слышишь сильное «желание» разрешиться вверх — это Ti, не тоника."
    ),
    frozenset({"Ti (VII)", "Do↑ (I)"}): (
        "Ti тянет вверх в Do. Do↑ — уже дом, спокойный и устойчивый."
    ),
    frozenset({"La (VI)", "Sol (V)"}): (
        "Sol — доминанта, яркая опора. La чуть выше и мягче, часто «грустнее», "
        "тянет к Sol или вниз к Do через Fa–Mi."
    ),
    frozenset({"Re (II)", "Do (I)"}): (
        "Do — дом, полный покой. Re — лёгкое напряжение, хочет вниз в Do "
        "(как начало многих мелодий: Re–Do)."
    ),
    frozenset({"Re (II)", "Mi (III)"}): (
        "Re неустойчива и часто идёт в Do; Mi — третья тоники, звучит устойчивее и светлее."
    ),
}

# Нормализация legacy-подписей к актуальным
def _norm_degree_label(label: str) -> str:
    d = degree_from_label(label)
    return DEGREE_LABELS[d] if d else label


@dataclass
class PlanStep:
    kind: str
    title: str
    detail: str
    count: int = 3
    focus: Optional[str] = None  # конкретная ступень/интервал
    minutes: int = 2


@dataclass
class DailyPlan:
    steps: list[PlanStep]
    intro: str
    total_minutes: int
    focus_summary: str


async def build_daily_plan(user_id: int) -> DailyPlan:
    """Собирает персональный план по слабым местам, точности и streak."""
    user = await database.get_user(user_id)
    level = int(user["level"]) if user else 1
    streak = int(user["streak"]) if user else 0

    weak = await database.get_weak_items(user_id, limit=8)
    summary = await database.get_accuracy_summary(user_id, limit_per_type=25)

    acc = {s["exercise_type"]: s["accuracy"] for s in summary}
    weak_degrees = [w for w in weak if w["exercise_type"] == "degrees"]
    weak_intervals = [w for w in weak if w["exercise_type"] == "intervals"]
    weak_other = [w for w in weak if w["exercise_type"] not in ("degrees", "intervals", "lesson", "plan")]

    focus_bits = []
    steps: list[PlanStep] = []
    day = datetime.utcnow().timetuple().tm_yday

    # 1. Разогрев интонации — всегда коротко
    steps.append(PlanStep(
        kind="intonation",
        title="Разогрев голоса",
        detail="Одна-две ноты чисто — включить слух и голос",
        count=2,
        minutes=1,
    ))

    # 2. Ядро FET — больше, если ступени слабые
    fet_count = 6 if weak_degrees or acc.get("degrees", 100) < 70 else 4
    focus_deg = None
    if weak_degrees:
        focus_deg = _norm_degree_label(weak_degrees[0]["expected"])
        focus_bits.append(focus_deg)
    steps.append(PlanStep(
        kind="fet",
        title="FET — функциональный слух",
        detail=(
            f"Фокус на {focus_deg}" if focus_deg
            else "Каденция I–IV–V–I → ступень → разрешение"
        ),
        count=fet_count,
        focus=focus_deg,
        minutes=3,
    ))

    # 3. Внутренний слух — с уровня 2 или если FET уже ок
    if level >= 2 or acc.get("degrees", 0) >= 60:
        steps.append(PlanStep(
            kind="fet_inner",
            title="Внутренний слух",
            detail="Удержи ступень в голове, потом ответь — тренировка аудиации",
            count=3,
            focus=focus_deg,
            minutes=2,
        ))

    # 4. Слабый интервал или гармония
    if weak_intervals:
        focus_iv = weak_intervals[0]["expected"]
        focus_bits.append(focus_iv)
        steps.append(PlanStep(
            kind="interval",
            title="Слабый интервал",
            detail=f"Добиваем: {focus_iv}",
            count=3,
            focus=focus_iv,
            minutes=2,
        ))
    elif weak_other:
        w = weak_other[0]
        focus_bits.append(w["expected"])
        kind = "harmony" if w["exercise_type"] == "harmony" else "interval"
        steps.append(PlanStep(
            kind=kind,
            title="Слабое место",
            detail=f"{w['expected']} ({w['exercise_type']})",
            count=3,
            focus=w["expected"],
            minutes=2,
        ))
    else:
        # без явных слабых мест — чередуем интервалы и живые мелодии
        if day % 3 == 0:
            steps.append(PlanStep(
                kind="melodies",
                title="Живые мелодии",
                detail="Узнай мотив — перенос слуха на реальную музыку",
                count=3,
                minutes=2,
            ))
        else:
            steps.append(PlanStep(
                kind="interval",
                title="Интервалы",
                detail="Закрепление мелодических интервалов",
                count=3,
                minutes=2,
            ))

    # 5. Активное пение или ритм — чередуем по дню
    if day % 2 == 0 or acc.get("singing", 100) < acc.get("rhythm", 100):
        steps.append(PlanStep(
            kind="singing",
            title="Пение",
            detail="Спой ступень или интервал — активный слух",
            count=2,
            minutes=2,
        ))
    else:
        steps.append(PlanStep(
            kind="rhythm",
            title="Ритм",
            detail="Повтори рисунок или определи размер",
            count=2,
            minutes=2,
        ))

    total = sum(s.minutes for s in steps)
    focus_summary = ", ".join(focus_bits[:3]) if focus_bits else "общий баланс навыков"

    streak_line = (
        f"Серия {streak}🔥 — не прерывай ритуал!"
        if streak > 0
        else "Сегодня отличный день начать серию."
    )
    intro = (
        f"🧠 <b>Твой план на сегодня</b> (~{total} мин)\n"
        f"Уровень {level}. Фокус: <b>{focus_summary}</b>\n"
        f"{streak_line}"
    )
    return DailyPlan(steps=steps, intro=intro, total_minutes=total, focus_summary=focus_summary)


def pedagogical_tip(expected: str, chosen: str, exercise_type: str = "degrees") -> Optional[str]:
    """Короткая подсказка педагога при ошибке (без вызова API)."""
    if exercise_type in ("degrees", "lesson", "plan", "weakspots"):
        a, b = _norm_degree_label(expected), _norm_degree_label(chosen)
        if a == b:
            return None
        tip = DEGREE_CONFUSION_TIPS.get(frozenset({a, b}))
        if tip:
            return f"💡 {tip}"
        stable = {"Do (I)", "Mi (III)", "Sol (V)", "Do↑ (I)"}
        if a in stable and b not in stable:
            return (
                f"💡 {a} — более устойчивая ступень. "
                f"{b} звучит напряжённее и «хочет» разрешиться в тонику."
            )
        if b in stable and a not in stable:
            return (
                f"💡 {a} неустойчива и тянет к тонике. "
                f"Сравни с устойчивой {b}: у неустойчивой больше «движения»."
            )
    if exercise_type == "intervals":
        return (
            f"💡 Запомни эталон «{expected}» ещё раз через «🔁 Повторить», "
            "потом сравни с тем, что выбрал — ищи характер (напряжение / покой / яркость)."
        )
    if exercise_type in ("melodies", "melody_degree", "melody_dictation", "melody_sing"):
        return (
            f"💡 Ещё раз прослушай через «🔁 Повторить» — "
            f"правильный ответ: «{expected}». Поймай первую ступень и контур."
        )
    return None


async def pedagogical_tip_async(
    expected: str,
    chosen: str,
    exercise_type: str = "degrees",
    *,
    context: str = "",
    use_ai: bool = True,
) -> Optional[str]:
    """
    Подсказка при ошибке: сначала быстрый локальный разбор,
    при отсутствии — короткий AI-разбор (Gemini, с кэшем).
    """
    # режимы мелодий со ступенями — та же логика, что FET
    tip_type = (
        "degrees"
        if exercise_type in ("melody_degree", "melody_dictation", "melody_sing")
        else exercise_type
    )
    local = pedagogical_tip(expected, chosen, tip_type)
    # известные пары ступеней — локальный совет достаточно точный и мгновенный
    if local and tip_type in ("degrees", "lesson", "plan", "weakspots"):
        a, b = _norm_degree_label(expected), _norm_degree_label(chosen)
        if DEGREE_CONFUSION_TIPS.get(frozenset({a, b})):
            return local

    if use_ai:
        try:
            from services.gemini_service import explain_confusion
            ai = await explain_confusion(
                exercise_type=tip_type,
                expected=expected,
                chosen=chosen,
                context=context,
            )
            if ai:
                return f"💡 {ai}"
        except Exception:
            pass
    return local


def ritual_closing(correct: int, total: int, streak: int, focus: str) -> str:
    """Финальный текст ритуала после плана."""
    pct = 100.0 * correct / total if total else 0
    if pct >= 80:
        mood = "Сильная сессия. Слух сегодня поработал на высоком уровне."
    elif pct >= 55:
        mood = "Хорошая работа. Завтра тот же ритуал — и будет ещё увереннее."
    else:
        mood = "Главное — что ты пришёл. Ошибки сегодня = точность завтра."

    next_streak = streak  # уже обновлён в БД
    return (
        f"🏁 <b>План выполнен!</b>\n\n"
        f"{mood}\n"
        f"Верно: <b>{correct}/{total}</b> ({pct:.0f}%)\n"
        f"Фокус дня: {focus}\n"
        f"🔥 Серия дней: <b>{next_streak}</b>\n\n"
        f"Завтра в это же время — снова «🧠 План на сегодня». "
        f"10 минут ритуала сильнее часа раз в неделю."
    )
