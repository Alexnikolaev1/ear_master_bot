"""
Раздел «Прогресс»: уровень, XP, графики, достижения, AI-рекомендация.
"""
import asyncio

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import config
import database
from services.exercise import XP_PER_LEVEL
from services.gemini_service import suggest_training_plan
from utils.keyboards import main_menu_keyboard
from utils.media import send_photo_file, temp_path

router = Router(name="stats")

EXERCISE_LABELS = {
    "intervals": "Интервалы",
    "chords": "Аккорды",
    "rhythm": "Ритм",
    "intonation": "Интонация",
    "notation": "Ноты",
    "degrees": "Ступени FET",
    "harmony": "Гармония",
    "dictation": "Диктант",
    "singing": "Пение",
    "meter": "Размер",
    "weakspots": "Слабые места",
    "lesson": "Урок дня",
    "plan": "План",
    "melodies": "Мелодии",
}


def _plot_daily_accuracy_sync(daily_rows: list, title: str) -> str:
    dates = [r["day"] for r in daily_rows]
    pct = [100.0 * r["correct"] / r["total"] if r["total"] else 0 for r in daily_rows]

    fig, ax = plt.subplots(figsize=(6, 3.2), dpi=140)
    ax.plot(dates, pct, marker="o", color="#4C72B0", linewidth=2)
    ax.set_ylim(0, 105)
    ax.set_ylabel("% верных ответов")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    plt.xticks(rotation=40, ha="right", fontsize=8)
    plt.tight_layout()

    out_path = temp_path("chart", ".png")
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def _plot_intonation_history_sync(rows: list) -> str:
    deviations = [r["deviation_cents"] for r in rows]
    x = list(range(1, len(deviations) + 1))

    fig, ax = plt.subplots(figsize=(6, 3.2), dpi=140)
    ax.axhline(0, color="gray", linewidth=1, linestyle="--")
    ax.axhspan(-config.CENTS_TOLERANCE_OK, config.CENTS_TOLERANCE_OK, color="#8FCB9B", alpha=0.3)
    ax.plot(x, deviations, marker="o", color="#C44E52", linewidth=2)
    ax.set_ylabel("Отклонение, центы")
    ax.set_xlabel("Попытка")
    ax.set_title("Точность интонации (0 = идеально, зелёная зона = зачёт)")
    ax.grid(alpha=0.3)
    plt.tight_layout()

    out_path = temp_path("chart", ".png")
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def _plot_accuracy_bars_sync(summary: list) -> str:
    labels = [EXERCISE_LABELS.get(s["exercise_type"], s["exercise_type"]) for s in summary]
    values = [s["accuracy"] for s in summary]

    fig, ax = plt.subplots(figsize=(6, 3.2), dpi=140)
    bars = ax.bar(labels, values, color="#4C72B0")
    ax.set_ylim(0, 105)
    ax.set_ylabel("% верных")
    ax.set_title("Точность по разделам (последние попытки)")
    ax.grid(axis="y", alpha=0.3)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2, f"{val:.0f}%",
                ha="center", va="bottom", fontsize=8)
    plt.xticks(rotation=20, ha="right", fontsize=8)
    plt.tight_layout()

    out_path = temp_path("chart", ".png")
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


@router.message(F.text == "📊 Прогресс")
async def show_stats(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    user = await database.get_or_create_user(user_id, message.from_user.full_name or "Музыкант")

    level = user["level"] or 1
    xp = user["xp"] or 0
    total = await database.get_total_exercises(user_id)
    achievements = await database.get_achievements(user_id)
    ach_text = (
        "\n".join(f"🏆 {a['title']}" for a in achievements)
        if achievements
        else "Пока нет достижений — тренируйся!"
    )

    summary = await database.get_accuracy_summary(user_id)
    summary_lines = []
    for s in summary:
        label = EXERCISE_LABELS.get(s["exercise_type"], s["exercise_type"])
        summary_lines.append(f"• {label}: {s['correct']}/{s['total']} ({s['accuracy']:.0f}%)")
    accuracy_block = "\n".join(summary_lines) if summary_lines else "Пока нет данных по разделам."

    xp_bar_filled = int(10 * xp / XP_PER_LEVEL)
    xp_bar = "█" * xp_bar_filled + "░" * (10 - xp_bar_filled)

    weak = await database.get_weak_items(user_id, limit=5)
    if weak:
        weak_block = "\n".join(
            f"• {w['expected']} ({EXERCISE_LABELS.get(w['exercise_type'], w['exercise_type'])}: "
            f"{100 * w['accuracy']:.0f}%)"
            for w in weak
        )
    else:
        weak_block = "Пока нет явных слабых мест — отличная работа!"

    plan_today = await database.plan_done_today(user_id)
    plan_streak = await database.get_plan_streak(user_id)
    plan_line = (
        f"✅ План на сегодня выполнен (ритуал {plan_streak} дн.)"
        if plan_today
        else f"⬜ План на сегодня ещё ждёт (ритуал {plan_streak} дн.)"
    )

    await message.answer(
        f"📊 <b>Твой прогресс</b>\n\n"
        f"⭐ Уровень: <b>{level}</b>\n"
        f"XP: [{xp_bar}] {xp}/{XP_PER_LEVEL}\n"
        f"🔥 Серия тренировок: <b>{user['streak']}</b>\n"
        f"🧠 {plan_line}\n"
        f"📝 Всего упражнений: <b>{total}</b>\n\n"
        f"<b>Точность:</b>\n{accuracy_block}\n\n"
        f"<b>💪 Слабые места:</b>\n{weak_block}\n\n"
        f"<b>Достижения:</b>\n{ach_text}",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )

    if summary:
        chart_path = await asyncio.to_thread(_plot_accuracy_bars_sync, summary)
        await send_photo_file(message, chart_path)

    interval_daily = await database.get_daily_accuracy(user_id, "intervals", days=14)
    if interval_daily:
        chart_path = await asyncio.to_thread(
            _plot_daily_accuracy_sync, interval_daily, "Интервалы: % верных ответов"
        )
        await send_photo_file(message, chart_path)

    intonation_history = await database.get_intonation_history(user_id, limit=30)
    if intonation_history:
        chart_path = await asyncio.to_thread(_plot_intonation_history_sync, intonation_history)
        await send_photo_file(message, chart_path)

    if not summary:
        await message.answer("Данных пока маловато для графиков — потренируйся и возвращайся 📈")

    if summary:
        summary_text = "; ".join(
            f"{s['exercise_type']}: {s['correct']}/{s['total']}" for s in summary
        )
        recommendation = await suggest_training_plan(summary_text)
        await message.answer(f"🤖 <b>Совет от AI-тренера:</b>\n{recommendation}", parse_mode="HTML")
