"""
utils/rate_limiter.py
Простой скользящий rate limiter в памяти процесса (без внешних зависимостей типа Redis —
для одного инстанса на Railway free tier этого достаточно).

Используется, чтобы не превышать бесплатные квоты Gemini / Groq API.
"""
import time
from collections import deque
from typing import Deque


class RateLimiter:
    """Ограничивает число вызовов за скользящее окно времени."""

    def __init__(self, max_calls: int, period_sec: float):
        self.max_calls = max_calls
        self.period_sec = period_sec
        self._timestamps: Deque[float] = deque()

    def allow(self) -> bool:
        """Проверяет, можно ли сделать вызов прямо сейчас, и если да — регистрирует его."""
        now = time.monotonic()
        # убираем устаревшие метки времени за пределами окна
        while self._timestamps and now - self._timestamps[0] > self.period_sec:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_calls:
            return False
        self._timestamps.append(now)
        return True

    def seconds_until_next_slot(self) -> float:
        """Сколько секунд подождать, если лимит исчерпан."""
        if not self._timestamps:
            return 0.0
        now = time.monotonic()
        oldest = self._timestamps[0]
        return max(0.0, self.period_sec - (now - oldest))


class DailyCounter:
    """Простой суточный счётчик вызовов (сбрасывается при смене даты UTC)."""

    def __init__(self, max_per_day: int):
        self.max_per_day = max_per_day
        self._day = None
        self._count = 0

    def allow(self) -> bool:
        import datetime
        today = datetime.datetime.utcnow().date()
        if self._day != today:
            self._day = today
            self._count = 0
        if self._count >= self.max_per_day:
            return False
        self._count += 1
        return True
