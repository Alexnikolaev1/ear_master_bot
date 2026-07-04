"""
Музыкальная теория для функционального слуха, гармонии и диктанта.
Все построения — в равномерной темперации, ноты из таблицы NOTE_FREQS.
"""
from __future__ import annotations

import random
from typing import Optional

from utils.helpers import NOTE_FREQS, NOTE_NAMES, note_freq, semitone_shift

# Мажорная гамма: полутоны от тоники
MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11, 12]
# Натуральный минор
MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10, 12]

# Подписи ступеней: movable-do (solfège) + римская цифра — ядро метода FET / Kodály
DEGREE_LABELS = {
    1: "Do (I)",
    2: "Re (II)",
    3: "Mi (III)",
    4: "Fa (IV)",
    5: "Sol (V)",
    6: "La (VI)",
    7: "Ti (VII)",
    8: "Do↑ (I)",
}

DEGREE_SHORT = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "I↑"}

# Старые подписи — для совместимости со слабыми местами в БД
_LEGACY_DEGREE_LABELS = {
    1: "I (тоника)",
    2: "II",
    3: "III",
    4: "IV (субдоминанта)",
    5: "V (доминанта)",
    6: "VI",
    7: "VII",
    8: "I↑ (октава)",
}

# Тоники, для которых все ступени есть в таблице (белые клавиши + простые диезы)
SAFE_TONICS = ["C3", "D3", "E3", "F3", "G3", "A3", "C4", "D4", "F4", "G4"]

# Каденции: название -> список ступеней (1-based) трезвучий
CADENCES: dict[str, list[int]] = {
    "Автентическая (V–I)": [5, 1],
    "Плагальная (IV–I)": [4, 1],
    "Прерванная (V–VI)": [5, 6],
    "Половинная (I–V)": [1, 5],
}

# Обращения мажорного трезвучия: (bass_offset_in_chord, label)
# chord tones: 0, 4, 7 — bass is which chord tone is lowest
INVERSIONS = {
    "Основной вид": 0,       # прима в басу
    "Секстаккорд": 1,        # терция в басу
    "Квартсекстаккорд": 2,   # квинта в басу
}

# Мелодические контуры для диктанта (ступени)
MELODY_PATTERNS: list[tuple[str, list[int]]] = [
    ("1–2–3", [1, 2, 3]),
    ("1–3–5", [1, 3, 5]),
    ("1–5–3", [1, 5, 3]),
    ("5–3–1", [5, 3, 1]),
    ("3–2–1", [3, 2, 1]),
    ("1–3–2", [1, 3, 2]),
    ("1–2–5", [1, 2, 5]),
    ("5–4–3–2–1", [5, 4, 3, 2, 1]),
    ("1–3–5–8", [1, 3, 5, 8]),
    ("1–5–1", [1, 5, 1]),
]

# Ритм: размер такта -> типичные интервалы между ударами (мс), 4 удара / 3 удара
METER_PATTERNS: dict[str, list[list[int]]] = {
    "4/4": [
        [400, 400, 400],           # 4 ровных доли
        [400, 200, 200, 400],
        [200, 200, 400, 400],
    ],
    "3/4": [
        [400, 400],                # 3 доли
        [200, 200, 400],
        [400, 200, 200],
    ],
}


def random_tonic(low_octave: int = 3, high_octave: int = 4) -> str:
    pool = [t for t in SAFE_TONICS if low_octave <= int(t[-1]) <= high_octave]
    return random.choice(pool or SAFE_TONICS)


def scale_note(tonic: str, degree: int, minor: bool = False) -> tuple[str, float]:
    """Ступень 1..8 относительно тоники. 8 = октава."""
    steps = MINOR_STEPS if minor else MAJOR_STEPS
    degree = max(1, min(8, degree))
    semitones = steps[degree - 1]
    return semitone_shift(tonic, semitones)


def scale_freqs(tonic: str, degrees: list[int], minor: bool = False) -> list[float]:
    return [scale_note(tonic, d, minor)[1] for d in degrees]


def tonic_context_freqs(tonic: str, minor: bool = False) -> list[float]:
    """Короткий мелодический контекст: I–III–V–I↑."""
    return scale_freqs(tonic, [1, 3, 5, 8], minor)


def triad_freqs(tonic: str, degree: int, minor_key: bool = False) -> list[float]:
    """Трезвучие на ступени мажорной/минорной гаммы (диатоническое)."""
    # ступени трезвучия: degree, degree+2, degree+4 (в гамме)
    root_deg = degree
    third_deg = ((degree - 1 + 2) % 7) + 1
    fifth_deg = ((degree - 1 + 4) % 7) + 1
    # если third/fifth «ниже» корня по номеру — поднимаем на октаву
    notes = []
    for d in (root_deg, third_deg, fifth_deg):
        name, freq = scale_note(tonic, d, minor_key)
        # для ступеней ниже корня в круговой нумерации — октава вверх
        if d < root_deg:
            name, freq = semitone_shift(name, 12) if name in NOTE_NAMES else (name, freq * 2)
        notes.append(freq)
    return notes


def fet_cadence_chords(tonic: str) -> list[list[float]]:
    """
    Классическая каденция метода Alain Benbassat / Functional Ear Trainer:
    I – IV – V – I. Жёстко якорит тональность в ухе.
    """
    return [triad_freqs(tonic, d) for d in (1, 4, 5, 1)]


def resolution_path(degree: int) -> list[int]:
    """
    Разрешение ступени в тонику — «гравитация» звука (ключ FET).
    После ответа ученик слышит, куда «хочет» пойти нота.
    """
    if degree <= 1:
        return [1]
    if degree == 8:
        return [8, 5, 3, 1]
    if degree == 7:
        return [7, 8]  # вводный тон тянет вверх в тонику
    return list(range(degree, 0, -1))


def resolution_freqs(tonic: str, degree: int) -> list[float]:
    return scale_freqs(tonic, resolution_path(degree))


def inversion_freqs(root_note: str, quality: str = "major", inversion: int = 0) -> list[float]:
    """
    Трезвучие с обращением.
    inversion: 0 = основной вид, 1 = секстаккорд, 2 = квартсекстаккорд.
    """
    intervals = [0, 4, 7] if quality == "major" else [0, 3, 7]
    tones = [semitone_shift(root_note, s)[1] for s in intervals]
    # rotate so bass is tones[inversion], raise lower notes by octave
    ordered = tones[inversion:] + [f * 2 for f in tones[:inversion]]
    return ordered


def cadence_chord_freqs(tonic: str, degree: int) -> list[float]:
    return triad_freqs(tonic, degree, minor_key=False)


def melody_options(correct: str, pool: list[tuple[str, list[int]]], count: int = 4) -> list[str]:
    labels = [p[0] for p in pool]
    others = [l for l in labels if l != correct]
    distractors = random.sample(others, min(count - 1, len(others)))
    options = distractors + [correct]
    random.shuffle(options)
    return options


def patterns_for_level(level: int) -> list[tuple[str, list[int]]]:
    if level <= 2:
        return MELODY_PATTERNS[:5]
    if level <= 4:
        return MELODY_PATTERNS[:8]
    return MELODY_PATTERNS


def degrees_for_level(level: int) -> list[int]:
    """Прогрессия Benbassat: сначала устойчивые, потом проходящие, потом вводный тон."""
    if level <= 2:
        return [1, 3, 5, 8]
    if level <= 4:
        return [1, 2, 3, 4, 5, 8]
    return [1, 2, 3, 4, 5, 6, 7, 8]


def degrees_for_fet_mastery(correct_streak_like_accuracy: float, level: int) -> list[int]:
    """
    Пул ступеней по освоению FET:
    точность по разделу degrees + общий уровень.
    """
    base = degrees_for_level(level)
    if correct_streak_like_accuracy >= 0.85 and level >= 3:
        return [1, 2, 3, 4, 5, 6, 7, 8]
    if correct_streak_like_accuracy >= 0.7:
        return list(dict.fromkeys(base + [2, 4]))
    return base


def pick_weighted_item(items: list[str], weak_items: list[str], weak_weight: float = 0.55) -> str:
    """С вероятностью weak_weight берёт элемент из слабых, иначе — из полного пула."""
    if weak_items and random.random() < weak_weight:
        # слабые, которые есть в текущем пуле
        candidates = [w for w in weak_items if w in items]
        if candidates:
            return random.choice(candidates)
    return random.choice(items)


def format_degree_options(degrees: list[int]) -> list[str]:
    return [DEGREE_LABELS[d] for d in degrees]


def degree_from_label(label: str) -> Optional[int]:
    for d, name in DEGREE_LABELS.items():
        if name == label or DEGREE_SHORT.get(d) == label:
            return d
    for d, name in _LEGACY_DEGREE_LABELS.items():
        if name == label:
            return d
    # solfège без римской цифры
    solfege = {"do": 1, "re": 2, "mi": 3, "fa": 4, "sol": 5, "la": 6, "ti": 7, "si": 7}
    key = label.strip().lower().split()[0].replace("↑", "")
    return solfege.get(key)
