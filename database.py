"""
database.py
Асинхронная обёртка над SQLite (через aiosqlite-подобный подход на потоках,
чтобы не блокировать event loop aiogram).

Мы используем стандартный модуль sqlite3, но все обращения к БД оборачиваем
в asyncio.to_thread(...), так как sqlite3 синхронный, а бот асинхронный.
"""
import sqlite3
import asyncio
import json
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional, Any

import config


def _connect() -> sqlite3.Connection:
    """Создаёт соединение с БД. check_same_thread=False, т.к. вызываем из разных потоков executor'а."""
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")  # чуть быстрее и надёжнее при конкурентном доступе
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Добавляет колонку, если её ещё нет (лёгкая миграция без alembic)."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _init_schema_sync() -> None:
    """Синхронная инициализация схемы БД (вызывается один раз при старте)."""
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                level INTEGER DEFAULT 1,
                xp INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                last_training_date TEXT,
                timezone TEXT DEFAULT 'Europe/Moscow',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS exercise_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                exercise_type TEXT,
                question TEXT,
                expected TEXT,
                user_answer TEXT,
                is_correct INTEGER,
                deviation_cents REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                data TEXT,
                expires_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                code TEXT,
                title TEXT,
                achieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, code)
            );

            CREATE INDEX IF NOT EXISTS idx_log_user_type
                ON exercise_log(user_id, exercise_type, timestamp);

            CREATE TABLE IF NOT EXISTS daily_plans (
                user_id INTEGER NOT NULL,
                plan_date TEXT NOT NULL,
                focus TEXT,
                correct INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, plan_date)
            );
            """
        )
        # миграции для уже существующих БД
        _ensure_column(conn, "users", "xp", "INTEGER DEFAULT 0")
        _ensure_column(conn, "users", "reminder_hour", "INTEGER")
        _ensure_column(conn, "users", "last_reminder_date", "TEXT")


async def init_db() -> None:
    """Публичная асинхронная точка инициализации БД, вызывается при старте бота."""
    await asyncio.to_thread(_init_schema_sync)


# ---------------------------------------------------------------------------
# Пользователи
# ---------------------------------------------------------------------------

def _get_or_create_user_sync(user_id: int, name: str) -> sqlite3.Row:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (user_id, name, timezone) VALUES (?, ?, ?)",
                (user_id, name, config.DEFAULT_TIMEZONE),
            )
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return row


async def get_or_create_user(user_id: int, name: str) -> sqlite3.Row:
    return await asyncio.to_thread(_get_or_create_user_sync, user_id, name)


def _get_user_sync(user_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


async def get_user(user_id: int) -> Optional[sqlite3.Row]:
    return await asyncio.to_thread(_get_user_sync, user_id)


def _add_user_xp_sync(user_id: int, xp_gain: int, xp_per_level: int = 100) -> Optional[int]:
    """
    Начисляет XP и повышает уровень при необходимости.
    Возвращает новый уровень, если был level-up, иначе None.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT level, xp FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        level = row["level"] or 1
        xp = (row["xp"] or 0) + xp_gain
        leveled_up_to = None
        while xp >= xp_per_level:
            xp -= xp_per_level
            level += 1
            leveled_up_to = level
        conn.execute(
            "UPDATE users SET level = ?, xp = ? WHERE user_id = ?",
            (level, xp, user_id),
        )
        return leveled_up_to


async def add_user_xp(user_id: int, xp_gain: int) -> Optional[int]:
    return await asyncio.to_thread(_add_user_xp_sync, user_id, xp_gain)


def _update_streak_sync(user_id: int) -> int:
    """Обновляет серию ежедневных тренировок (streak) и возвращает новое значение."""
    today = datetime.utcnow().date()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT streak, last_training_date FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return 0
        streak = row["streak"] or 0
        last_date_str = row["last_training_date"]
        if last_date_str:
            last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
            delta = (today - last_date).days
            if delta == 0:
                pass  # уже тренировались сегодня, streak не меняем
            elif delta == 1:
                streak += 1
            else:
                streak = 1
        else:
            streak = 1
        conn.execute(
            "UPDATE users SET streak = ?, last_training_date = ? WHERE user_id = ?",
            (streak, today.strftime("%Y-%m-%d"), user_id),
        )
        return streak


async def update_streak(user_id: int) -> int:
    return await asyncio.to_thread(_update_streak_sync, user_id)


def _set_user_level_sync(user_id: int, level: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET level = ? WHERE user_id = ?", (level, user_id))


async def set_user_level(user_id: int, level: int) -> None:
    await asyncio.to_thread(_set_user_level_sync, user_id, level)


def _set_user_timezone_sync(user_id: int, tz: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET timezone = ? WHERE user_id = ?", (tz, user_id))


async def set_user_timezone(user_id: int, tz: str) -> None:
    await asyncio.to_thread(_set_user_timezone_sync, user_id, tz)


def _set_reminder_hour_sync(user_id: int, hour: Optional[int]) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET reminder_hour = ? WHERE user_id = ?",
            (hour, user_id),
        )


async def set_reminder_hour(user_id: int, hour: Optional[int]) -> None:
    """hour=None отключает напоминания; 0..23 — локальный час."""
    await asyncio.to_thread(_set_reminder_hour_sync, user_id, hour)


def _get_users_for_reminders_sync() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT user_id, name, timezone, reminder_hour, last_reminder_date,
                      last_training_date
               FROM users
               WHERE reminder_hour IS NOT NULL"""
        ).fetchall()
        return [dict(r) for r in rows]


async def get_users_for_reminders() -> list[dict]:
    return await asyncio.to_thread(_get_users_for_reminders_sync)


def _mark_reminder_sent_sync(user_id: int, day: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET last_reminder_date = ? WHERE user_id = ?",
            (day, user_id),
        )


async def mark_reminder_sent(user_id: int, day: str) -> None:
    await asyncio.to_thread(_mark_reminder_sent_sync, user_id, day)


# ---------------------------------------------------------------------------
# Лог упражнений
# ---------------------------------------------------------------------------

def _log_exercise_sync(
    user_id: int,
    exercise_type: str,
    question: str,
    expected: str,
    user_answer: str,
    is_correct: bool,
    deviation_cents: Optional[float] = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO exercise_log
               (user_id, exercise_type, question, expected, user_answer, is_correct, deviation_cents)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, exercise_type, question, expected, user_answer, int(is_correct), deviation_cents),
        )


async def log_exercise(
    user_id: int,
    exercise_type: str,
    question: str,
    expected: str,
    user_answer: str,
    is_correct: bool,
    deviation_cents: Optional[float] = None,
) -> None:
    await asyncio.to_thread(
        _log_exercise_sync, user_id, exercise_type, question, expected, user_answer, is_correct, deviation_cents
    )


def _get_recent_stats_sync(user_id: int, exercise_type: str, limit: int = 20) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM exercise_log
               WHERE user_id = ? AND exercise_type = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (user_id, exercise_type, limit),
        ).fetchall()
        return [dict(r) for r in rows]


async def get_recent_stats(user_id: int, exercise_type: str, limit: int = 20) -> list:
    return await asyncio.to_thread(_get_recent_stats_sync, user_id, exercise_type, limit)


def _get_daily_accuracy_sync(user_id: int, exercise_type: str, days: int = 14) -> list:
    """Возвращает список (дата, процент_верных) за последние N дней для графика."""
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT date(timestamp) as day,
                      SUM(is_correct) as correct,
                      COUNT(*) as total
               FROM exercise_log
               WHERE user_id = ? AND exercise_type = ? AND date(timestamp) >= ?
               GROUP BY day ORDER BY day ASC""",
            (user_id, exercise_type, since),
        ).fetchall()
        return [dict(r) for r in rows]


async def get_daily_accuracy(user_id: int, exercise_type: str, days: int = 14) -> list:
    return await asyncio.to_thread(_get_daily_accuracy_sync, user_id, exercise_type, days)


def _get_intonation_history_sync(user_id: int, limit: int = 30) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT deviation_cents, timestamp FROM exercise_log
               WHERE user_id = ? AND exercise_type = 'intonation' AND deviation_cents IS NOT NULL
               ORDER BY timestamp ASC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


async def get_intonation_history(user_id: int, limit: int = 30) -> list:
    return await asyncio.to_thread(_get_intonation_history_sync, user_id, limit)


def _get_streak_of_correct_sync(user_id: int, exercise_type: str) -> int:
    """Считает подряд идущие верные ответы (для достижений)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT is_correct FROM exercise_log
               WHERE user_id = ? AND exercise_type = ?
               ORDER BY timestamp DESC LIMIT 50""",
            (user_id, exercise_type),
        ).fetchall()
        streak = 0
        for r in rows:
            if r["is_correct"]:
                streak += 1
            else:
                break
        return streak


async def get_streak_of_correct(user_id: int, exercise_type: str) -> int:
    return await asyncio.to_thread(_get_streak_of_correct_sync, user_id, exercise_type)


def _get_accuracy_summary_sync(user_id: int, limit_per_type: int = 20) -> list[dict]:
    """Сводка точности по всем типам упражнений."""
    types = (
        "intervals", "chords", "rhythm", "intonation", "notation",
        "degrees", "harmony", "dictation", "singing", "meter", "weakspots", "lesson",
        "plan", "melodies",
    )
    result = []
    with get_conn() as conn:
        for ex_type in types:
            rows = conn.execute(
                """SELECT is_correct FROM exercise_log
                   WHERE user_id = ? AND exercise_type = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (user_id, ex_type, limit_per_type),
            ).fetchall()
            if not rows:
                continue
            correct = sum(r["is_correct"] for r in rows)
            result.append({
                "exercise_type": ex_type,
                "correct": correct,
                "total": len(rows),
                "accuracy": 100.0 * correct / len(rows),
            })
    return result


async def get_accuracy_summary(user_id: int, limit_per_type: int = 20) -> list[dict]:
    return await asyncio.to_thread(_get_accuracy_summary_sync, user_id, limit_per_type)


def _get_total_exercises_sync(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM exercise_log WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return int(row["cnt"]) if row else 0


async def get_total_exercises(user_id: int) -> int:
    return await asyncio.to_thread(_get_total_exercises_sync, user_id)


def _get_weak_items_sync(
    user_id: int,
    exercise_type: Optional[str] = None,
    min_attempts: int = 2,
    max_accuracy: float = 0.65,
    limit: int = 15,
    days: int = 30,
) -> list[dict]:
    """
    Элементы с низкой точностью (spaced repetition / слабые места).
    Возвращает [{exercise_type, expected, correct, total, accuracy}, ...]
    отсортировано по возрастанию accuracy.
    """
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    params: list[Any] = [user_id, since]
    type_filter = ""
    if exercise_type:
        type_filter = "AND exercise_type = ?"
        params.append(exercise_type)
    params.extend([min_attempts, max_accuracy, limit])
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT exercise_type, expected,
                   SUM(is_correct) AS correct,
                   COUNT(*) AS total,
                   1.0 * SUM(is_correct) / COUNT(*) AS accuracy
            FROM exercise_log
            WHERE user_id = ? AND date(timestamp) >= ? {type_filter}
              AND expected IS NOT NULL AND expected != ''
            GROUP BY exercise_type, expected
            HAVING total >= ? AND accuracy <= ?
            ORDER BY accuracy ASC, total DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]


async def get_weak_items(
    user_id: int,
    exercise_type: Optional[str] = None,
    min_attempts: int = 2,
    max_accuracy: float = 0.65,
    limit: int = 15,
) -> list[dict]:
    return await asyncio.to_thread(
        _get_weak_items_sync, user_id, exercise_type, min_attempts, max_accuracy, limit
    )


def _get_recent_wrong_expected_sync(user_id: int, exercise_type: str, limit: int = 5) -> list[str]:
    """Последние неверные ответы — для немедленного повтора ошибки."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT expected FROM exercise_log
               WHERE user_id = ? AND exercise_type = ? AND is_correct = 0
               ORDER BY timestamp DESC LIMIT ?""",
            (user_id, exercise_type, limit),
        ).fetchall()
        return [r["expected"] for r in rows if r["expected"]]


async def get_recent_wrong_expected(user_id: int, exercise_type: str, limit: int = 5) -> list[str]:
    return await asyncio.to_thread(_get_recent_wrong_expected_sync, user_id, exercise_type, limit)


def _save_daily_plan_sync(user_id: int, focus: str, correct: int, total: int) -> bool:
    """Сохраняет выполнение плана. True если это первое завершение за сегодня."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT 1 FROM daily_plans WHERE user_id = ? AND plan_date = ?",
            (user_id, today),
        ).fetchone()
        conn.execute(
            """INSERT INTO daily_plans (user_id, plan_date, focus, correct, total)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, plan_date) DO UPDATE SET
                 focus=excluded.focus, correct=excluded.correct,
                 total=excluded.total, completed_at=CURRENT_TIMESTAMP""",
            (user_id, today, focus, correct, total),
        )
        return existing is None


async def save_daily_plan(user_id: int, focus: str, correct: int, total: int) -> bool:
    return await asyncio.to_thread(_save_daily_plan_sync, user_id, focus, correct, total)


def _plan_done_today_sync(user_id: int) -> bool:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM daily_plans WHERE user_id = ? AND plan_date = ?",
            (user_id, today),
        ).fetchone()
        return row is not None


async def plan_done_today(user_id: int) -> bool:
    return await asyncio.to_thread(_plan_done_today_sync, user_id)


def _plan_streak_sync(user_id: int) -> int:
    """Сколько дней подряд выполнен план (по daily_plans)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT plan_date FROM daily_plans WHERE user_id = ?
               ORDER BY plan_date DESC LIMIT 60""",
            (user_id,),
        ).fetchall()
    if not rows:
        return 0
    dates = [datetime.strptime(r["plan_date"], "%Y-%m-%d").date() for r in rows]
    today = datetime.utcnow().date()
    streak = 0
    expected = today
    # если сегодня ещё не отмечен — считаем от вчера
    if dates[0] != today:
        if dates[0] != today - timedelta(days=1):
            return 0
        expected = dates[0]
    for d in dates:
        if d == expected:
            streak += 1
            expected = expected - timedelta(days=1)
        else:
            break
    return streak


async def get_plan_streak(user_id: int) -> int:
    return await asyncio.to_thread(_plan_streak_sync, user_id)


# ---------------------------------------------------------------------------
# Достижения
# ---------------------------------------------------------------------------

def _grant_achievement_sync(user_id: int, code: str, title: str) -> bool:
    """Возвращает True, если достижение выдано впервые."""
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO achievements (user_id, code, title) VALUES (?, ?, ?)",
                (user_id, code, title),
            )
            return True
        except sqlite3.IntegrityError:
            return False  # уже было выдано


async def grant_achievement(user_id: int, code: str, title: str) -> bool:
    return await asyncio.to_thread(_grant_achievement_sync, user_id, code, title)


def _get_achievements_sync(user_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT code, title, achieved_at FROM achievements WHERE user_id = ? ORDER BY achieved_at",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


async def get_achievements(user_id: int) -> list:
    return await asyncio.to_thread(_get_achievements_sync, user_id)


# ---------------------------------------------------------------------------
# Кэш (для ответов Gemini)
# ---------------------------------------------------------------------------

def _cache_get_sync(key: str) -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT data, expires_at FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
        if expires_at < datetime.utcnow():
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            return None
        return row["data"]


async def cache_get(key: str) -> Optional[str]:
    return await asyncio.to_thread(_cache_get_sync, key)


def _cache_set_sync(key: str, data: str, ttl_days: int) -> None:
    expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO cache (key, data, expires_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET data=excluded.data, expires_at=excluded.expires_at",
            (key, data, expires_at),
        )


async def cache_set(key: str, data: str, ttl_days: int = config.GEMINI_CACHE_TTL_DAYS) -> None:
    await asyncio.to_thread(_cache_set_sync, key, data, ttl_days)
