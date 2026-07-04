"""
Музыкальные константы, частоты нот, адаптивная сложность и текстовые хелперы.
Клавиатуры — в utils.keyboards.
"""
from __future__ import annotations

import json
import math
import random
from typing import Tuple

import config

with open(config.NOTE_FREQS_PATH, "r", encoding="utf-8") as f:
    NOTE_FREQS: dict[str, float] = json.load(f)

NOTE_NAMES = list(NOTE_FREQS.keys())

# Интервалы: название -> полутоны
INTERVALS: dict[str, int] = {
    "Прима": 0,
    "Малая секунда": 1,
    "Большая секунда": 2,
    "Малая терция": 3,
    "Большая терция": 4,
    "Чистая кварта": 5,
    "Тритон": 6,
    "Чистая квинта": 7,
    "Малая секста": 8,
    "Большая секста": 9,
    "Малая септима": 10,
    "Большая септима": 11,
    "Октава": 12,
}

# Пулы интервалов по сложности
INTERVALS_EASY = {
    k: INTERVALS[k]
    for k in ("Прима", "Большая секунда", "Малая терция", "Большая терция", "Чистая кварта", "Чистая квинта", "Октава")
}
INTERVALS_MEDIUM = {
    k: INTERVALS[k]
    for k in (*INTERVALS_EASY, "Малая секунда", "Малая секста", "Большая секста")
}
INTERVALS_HARD = INTERVALS

# Аккорды: название -> полутоны от основного тона
CHORDS: dict[str, list[int]] = {
    "Мажорное трезвучие": [0, 4, 7],
    "Минорное трезвучие": [0, 3, 7],
    "Уменьшённое трезвучие": [0, 3, 6],
    "Увеличенное трезвучие": [0, 4, 8],
    "Доминантсептаккорд": [0, 4, 7, 10],
    "Минорный септаккорд": [0, 3, 7, 10],
}

CHORDS_EASY = {k: CHORDS[k] for k in ("Мажорное трезвучие", "Минорное трезвучие")}
CHORDS_MEDIUM = {
    k: CHORDS[k]
    for k in (*CHORDS_EASY, "Уменьшённое трезвучие", "Увеличенное трезвучие")
}
CHORDS_HARD = CHORDS

# Ритмические рисунки: от простого к сложному
RHYTHM_PATTERNS: list[list[int]] = [
    [500, 500, 500],
    [250, 250, 500],
    [500, 250, 250],
    [333, 333, 333, 333],
    [250, 250, 250, 250, 500],
    [375, 125, 500],
    [250, 500, 250],
    [125, 125, 250, 500],
    [200, 600, 200],           # синкопа
    [150, 150, 300, 600],
]

MAIN_MENU_BUTTONS = [
    "🧠 План на сегодня",
    "💪 Слабые места",
    "🎵 Интервалы",
    "🎼 Ступени",
    "🎹 Аккорды",
    "🏛 Гармония",
    "🥁 Ритм",
    "🎤 Пение",
    "📖 Ноты",
    "🎶 Мелодии",
    "✍️ Диктант",
    "📚 Теория",
    "📊 Прогресс",
]

BTN_STOP = "⏹ Стоп"
BTN_REPLAY = "🔁 Повторить"
BTN_HARMONIC = "🎼 Гармонический"
BTN_MELODIC = "🎶 Мелодический"
BTN_METER = "⏱ Размер"
BTN_PATTERN = "🥁 Рисунок"
BTN_FET_NORMAL = "🧬 Обычный FET"
BTN_FET_INNER = "🧘 Внутренний"
BTN_FET_IMAGINE = "🔮 Представь"
BTN_MELODY_NAME = "🎶 Угадай мелодию"
BTN_MELODY_DEGREE = "🎯 Первая ступень"
BTN_MELODY_DICTATION = "✍️ 3 ступени"
BTN_MELODY_SING = "🎤 Спой начало"

SECTION_LABELS = {
    "intervals": "Интервалы",
    "chords": "Аккорды",
    "rhythm": "Ритм",
    "intonation": "Интонация",
    "notation": "Ноты",
    "theory": "Теория",
    "degrees": "Ступени (FET)",
    "harmony": "Гармония",
    "dictation": "Диктант",
    "singing": "Пение",
    "meter": "Размер такта",
    "weakspots": "Слабые места",
    "lesson": "Урок дня",
    "plan": "План на сегодня",
    "melodies": "Мелодии",
}


def intervals_for_level(level: int) -> dict[str, int]:
    if level <= 2:
        return INTERVALS_EASY
    if level <= 4:
        return INTERVALS_MEDIUM
    return INTERVALS_HARD


def chords_for_level(level: int) -> dict[str, list[int]]:
    if level <= 2:
        return CHORDS_EASY
    if level <= 4:
        return CHORDS_MEDIUM
    return CHORDS_HARD


def rhythm_patterns_for_level(level: int) -> list[list[int]]:
    if level <= 2:
        return RHYTHM_PATTERNS[:3]
    if level <= 4:
        return RHYTHM_PATTERNS[:5]
    return RHYTHM_PATTERNS


def note_range_for_level(level: int) -> tuple[str, str]:
    """Диапазон нот для интонации/интервалов в зависимости от уровня."""
    if level <= 2:
        return "C3", "C4"
    if level <= 4:
        return "C3", "C5"
    return "A2", "E5"


def freq_to_cents_diff(measured_hz: float, target_hz: float) -> float:
    """Разница между измеренной и эталонной частотой в центах (100 центов = полутон)."""
    if measured_hz <= 0 or target_hz <= 0:
        return float("nan")
    return 1200.0 * math.log2(measured_hz / target_hz)


def note_freq(note_name: str) -> float:
    return NOTE_FREQS[note_name]


def semitone_shift(note_name: str, semitones: int) -> Tuple[str, float]:
    """Нота на N полутонов выше/ниже. При выходе за таблицу — расчёт по формуле."""
    if note_name in NOTE_NAMES:
        idx = NOTE_NAMES.index(note_name)
        new_idx = idx + semitones
        if 0 <= new_idx < len(NOTE_NAMES):
            new_name = NOTE_NAMES[new_idx]
            return new_name, NOTE_FREQS[new_name]
    base_freq = NOTE_FREQS[note_name]
    freq = base_freq * (2 ** (semitones / 12))
    return f"{note_name}+{semitones}п/т", freq


def random_base_note(low: str = "C3", high: str = "C5") -> str:
    low_idx = NOTE_NAMES.index(low)
    high_idx = NOTE_NAMES.index(high)
    return random.choice(NOTE_NAMES[low_idx : high_idx + 1])


def cents_feedback_text(deviation_cents: float) -> str:
    abs_dev = abs(deviation_cents)
    direction = "выше" if deviation_cents > 0 else "ниже"
    if abs_dev <= config.CENTS_TOLERANCE_PERFECT:
        return f"🎯 Идеально чисто! Отклонение всего {abs_dev:.0f} центов."
    if abs_dev <= config.CENTS_TOLERANCE_OK:
        return f"✅ Почти чисто! Вы спели на {abs_dev:.0f} центов {direction} нормы."
    if abs_dev <= config.CENTS_TOLERANCE_CLOSE:
        return (
            f"🔶 Близко, но мимо. Вы спели на {abs_dev:.0f} центов {direction} нормы "
            "— попробуйте скорректировать."
        )
    return (
        f"❌ Мимо ноты. Вы спели на {abs_dev:.0f} центов {direction} "
        "— послушайте эталон ещё раз и повторите."
    )
