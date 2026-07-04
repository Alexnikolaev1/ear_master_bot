"""
Библиотека узнаваемых мелодий (public domain / народные) в ступенях.
Слух учится на «живой» музыке, а не только на абстрактных упражнениях.
"""
from __future__ import annotations

import random
from typing import Optional

from services.music_theory import DEGREE_LABELS, fet_cadence_chords, random_tonic, scale_freqs

# degrees: 1=Do … 8=Do↑; ритм — относительные длительности (четверть = 1.0)
MELODY_LIBRARY: list[dict] = [
    {
        "id": "ode_to_joy",
        "title": "Ода к радости",
        "hint": "Бетховен",
        "degrees": [3, 3, 4, 5, 5, 4, 3, 2, 1, 1, 2, 3, 3, 2, 2],
        "rhythm": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1.5, 0.5, 2],
    },
    {
        "id": "twinkle",
        "title": "Яркая звёздочка",
        "hint": "Twinkle Twinkle",
        "degrees": [1, 1, 5, 5, 6, 6, 5, 4, 4, 3, 3, 2, 2, 1],
        "rhythm": [1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 2],
    },
    {
        "id": "mary_lamb",
        "title": "У Марии был барашек",
        "hint": "народная / детская",
        "degrees": [3, 2, 1, 2, 3, 3, 3, 2, 2, 2, 3, 5, 5],
        "rhythm": [1, 1, 1, 1, 1, 1, 2, 1, 1, 2, 1, 1, 2],
    },
    {
        "id": "jingle",
        "title": "Jingle Bells",
        "hint": "рождественская",
        "degrees": [3, 3, 3, 3, 3, 3, 3, 5, 1, 2, 3],
        "rhythm": [1, 1, 2, 1, 1, 2, 1, 1, 1, 1, 4],
    },
    {
        "id": "bereza",
        "title": "Во поле берёза стояла",
        "hint": "русская народная",
        "degrees": [5, 3, 5, 3, 5, 6, 5, 4, 3, 2, 1],
        "rhythm": [1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 2],
    },
    {
        "id": "kalinka",
        "title": "Калинка",
        "hint": "русская народная",
        "degrees": [5, 3, 1, 5, 3, 1, 2, 3, 4, 3, 2, 1],
        "rhythm": [0.5, 0.5, 1, 0.5, 0.5, 1, 1, 1, 1, 1, 1, 2],
    },
    {
        "id": "seni",
        "title": "Ах вы сени",
        "hint": "русская народная",
        "degrees": [5, 5, 6, 5, 4, 3, 2, 1, 2, 3, 1],
        "rhythm": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2],
    },
    {
        "id": "yolochka",
        "title": "В лесу родилась ёлочка",
        "hint": "детская песня",
        "degrees": [5, 3, 3, 4, 2, 2, 1, 2, 3, 4, 5, 5, 5],
        "rhythm": [1, 1, 2, 1, 1, 2, 1, 1, 1, 1, 1, 1, 2],
    },
    {
        "id": "frere",
        "title": "Брат Яков",
        "hint": "Frère Jacques",
        "degrees": [1, 2, 3, 1, 1, 2, 3, 1, 3, 4, 5, 3, 4, 5],
        "rhythm": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 1, 1, 2],
    },
    {
        "id": "london_bridge",
        "title": "Лондонский мост",
        "hint": "London Bridge",
        "degrees": [5, 6, 5, 4, 3, 4, 5, 2, 3, 4, 3, 4, 5],
        "rhythm": [1.5, 0.5, 1, 1, 1, 1, 2, 1, 1, 2, 1, 1, 2],
    },
    {
        "id": "lightly_row",
        "title": "Плыви, лодочка",
        "hint": "Lightly Row",
        "degrees": [5, 3, 3, 4, 2, 2, 1, 2, 3, 4, 5, 5, 5],
        "rhythm": [1, 1, 2, 1, 1, 2, 1, 1, 1, 1, 1, 1, 2],
    },
    {
        "id": "au_clair",
        "title": "При свете луны",
        "hint": "Au clair de la lune",
        "degrees": [1, 1, 1, 2, 3, 2, 1, 3, 2, 2, 1],
        "rhythm": [1, 1, 1, 1, 2, 2, 1, 1, 1, 1, 2],
    },
    {
        "id": "happy_birthday",
        "title": "Happy Birthday",
        "hint": "день рождения",
        "degrees": [5, 5, 6, 5, 8, 7, 5, 5, 6, 5, 1, 8],
        "rhythm": [0.75, 0.25, 1, 1, 1, 2, 0.75, 0.25, 1, 1, 1, 2],
    },
    {
        "id": "hot_cross",
        "title": "Hot Cross Buns",
        "hint": "детская английская",
        "degrees": [3, 2, 1, 3, 2, 1, 1, 1, 1, 1, 2, 2, 2, 2, 3, 2, 1],
        "rhythm": [1, 1, 2, 1, 1, 2, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1, 1, 2],
    },
    {
        "id": "row_boat",
        "title": "Row Your Boat",
        "hint": "Row, Row, Row Your Boat",
        "degrees": [1, 1, 1, 2, 3, 3, 2, 3, 4, 5],
        "rhythm": [1, 1, 0.75, 0.25, 2, 0.75, 0.25, 0.75, 0.25, 2],
    },
    {
        "id": "are_you_sleeping",
        "title": "Are You Sleeping",
        "hint": "тот же мотив, что Брат Яков",
        "degrees": [1, 2, 3, 1, 3, 4, 5],
        "rhythm": [1, 1, 1, 1, 1, 1, 2],
    },
    {
        "id": "korobeiniki",
        "title": "Коробейники",
        "hint": "русская / Tetris-тема",
        "degrees": [5, 2, 3, 4, 3, 2, 1, 1, 3, 5, 4, 3, 2],
        "rhythm": [1, 0.5, 0.5, 1, 0.5, 0.5, 1, 0.5, 0.5, 1, 0.5, 0.5, 2],
    },
    {
        "id": "katusha",
        "title": "Катюша",
        "hint": "русская песня",
        "degrees": [1, 3, 5, 5, 6, 5, 4, 3, 2, 1, 2, 3, 1],
        "rhythm": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2],
    },
    {
        "id": "smoke_water",
        "title": "Smoke on the Water",
        "hint": "Deep Purple (мотив)",
        "degrees": [1, 4, 5, 1, 4, 6, 5, 1, 4, 5, 4, 1],
        "rhythm": [1, 1, 2, 1, 1, 1, 2, 1, 1, 1, 1, 2],
    },
    {
        "id": "amazing_grace",
        "title": "Amazing Grace",
        "hint": "гимн",
        "degrees": [1, 3, 5, 8, 6, 5, 3, 1, 2, 3],
        "rhythm": [1, 1, 2, 1, 1, 2, 1, 1, 1, 2],
    },
    {
        "id": "when_saints",
        "title": "When the Saints",
        "hint": "госпел / джаз",
        "degrees": [1, 3, 4, 5, 1, 3, 4, 5, 5, 4, 3, 1, 3, 2],
        "rhythm": [1, 1, 1, 2, 1, 1, 1, 2, 1, 1, 1, 1, 1, 2],
    },
    {
        "id": "scarborough",
        "title": "Scarborough Fair",
        "hint": "английская баллада",
        "degrees": [1, 1, 1, 2, 3, 5, 5, 4, 3, 1, 2, 1],
        "rhythm": [1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 2],
    },
    {
        "id": "greensleeves",
        "title": "Greensleeves",
        "hint": "английская народная",
        "degrees": [5, 8, 7, 6, 5, 4, 3, 2, 1, 2, 3],
        "rhythm": [1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 2],
    },
    {
        "id": "oh_susanna",
        "title": "Oh! Susanna",
        "hint": "американская народная",
        "degrees": [1, 2, 3, 5, 5, 6, 5, 3, 1, 2, 3, 3, 2, 1, 2],
        "rhythm": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2],
    },
]


def melodies_for_level(level: int) -> list[dict]:
    if level <= 2:
        return [m for m in MELODY_LIBRARY if len(m["degrees"]) <= 12]
    if level <= 4:
        return [m for m in MELODY_LIBRARY if len(m["degrees"]) <= 15]
    return list(MELODY_LIBRARY)


def pick_melody(level: int = 3, exclude_id: Optional[str] = None) -> dict:
    pool = melodies_for_level(level)
    if exclude_id:
        pool = [m for m in pool if m["id"] != exclude_id] or pool
    return random.choice(pool)


def melody_options(correct: dict, level: int = 3, count: int = 4) -> list[str]:
    pool = melodies_for_level(level)
    titles = [m["title"] for m in pool if m["id"] != correct["id"]]
    distractors = random.sample(titles, min(count - 1, len(titles)))
    options = distractors + [correct["title"]]
    random.shuffle(options)
    return options


def first_degree_label(melody: dict) -> str:
    """Подпись первой ступени мотива (Do/Re/Mi…)."""
    d = int(melody["degrees"][0])
    # октавная тоника в начале — всё равно Do
    if d == 8:
        d = 1
    return DEGREE_LABELS[d]


def first_degree_options(correct_label: str, count: int = 4) -> list[str]:
    """Варианты ответа для режима «первая ступень»."""
    pool = [DEGREE_LABELS[d] for d in (1, 2, 3, 4, 5, 6, 7)]
    others = [x for x in pool if x != correct_label]
    distractors = random.sample(others, min(count - 1, len(others)))
    options = distractors + [correct_label]
    random.shuffle(options)
    return options


def _norm_degree(d: int) -> int:
    return 1 if int(d) == 8 else int(d)


def degree_solfege(d: int) -> str:
    """Короткое имя ступени: Do, Re, Mi…"""
    return DEGREE_LABELS[_norm_degree(d)].split()[0]


def motif_contour(melody: dict, n: int = 3) -> str:
    """Контур первых N ступеней: «Mi–Mi–Fa»."""
    degrees = melody["degrees"][:n]
    if len(degrees) < n:
        degrees = degrees + [degrees[-1]] * (n - len(degrees))
    return "-".join(degree_solfege(d) for d in degrees)


def motif_contour_options(melody: dict, n: int = 3, count: int = 4) -> list[str]:
    """
    Варианты мини-диктанта: правильный контур + правдоподобные отвлекающие
    (меняем одну ступень).
    """
    correct = motif_contour(melody, n)
    base = [_norm_degree(d) for d in melody["degrees"][:n]]
    while len(base) < n:
        base.append(base[-1] if base else 1)

    distractors: set[str] = set()
    pool_degrees = [1, 2, 3, 4, 5, 6, 7]
    attempts = 0
    while len(distractors) < count - 1 and attempts < 40:
        attempts += 1
        mutant = list(base)
        idx = random.randrange(n)
        choices = [d for d in pool_degrees if d != mutant[idx]]
        mutant[idx] = random.choice(choices)
        label = "-".join(degree_solfege(d) for d in mutant)
        if label != correct:
            distractors.add(label)

    # если мало мутаций — берём контуры других мелодий
    if len(distractors) < count - 1:
        for other in MELODY_LIBRARY:
            if other["id"] == melody["id"]:
                continue
            label = motif_contour(other, n)
            if label != correct:
                distractors.add(label)
            if len(distractors) >= count - 1:
                break

    options = list(distractors)[: count - 1] + [correct]
    random.shuffle(options)
    return options


def opening_target_freq(melody: dict, tonic: str) -> tuple[str, float, str]:
    """Первая нота мотива: (имя ноты, частота, подпись ступени)."""
    from services.music_theory import scale_note

    d = _norm_degree(melody["degrees"][0])
    name, freq = scale_note(tonic, d)
    return name, freq, DEGREE_LABELS[d]


def build_melody_audio_plan(
    melody: dict,
    tonic: Optional[str] = None,
    *,
    motif_notes: Optional[int] = None,
) -> dict:
    """
    Готовит данные для синтеза: каденция FET + мелодия с ритмом.
    motif_notes — обрезать до N первых нот (для режима «первая ступень»).
    """
    tonic = tonic or random_tonic()
    cadence = fet_cadence_chords(tonic)
    degrees = list(melody["degrees"])
    rhythm = list(melody.get("rhythm") or [1.0] * len(degrees))
    if motif_notes is not None:
        n = max(3, min(motif_notes, len(degrees)))
        degrees = degrees[:n]
        rhythm = rhythm[:n]
    if len(rhythm) < len(degrees):
        rhythm = rhythm + [1.0] * (len(degrees) - len(rhythm))
    freqs = scale_freqs(tonic, degrees)
    return {
        "tonic": tonic,
        "cadence": cadence,
        "freqs": freqs,
        "rhythm": rhythm[: len(freqs)],
        "melody": melody,
        "first_degree": first_degree_label(melody),
    }


# Индексы для клавиатур
TITLE_TO_ID = {m["title"]: m["id"] for m in MELODY_LIBRARY}
ID_TO_TITLE = {m["id"]: m["title"] for m in MELODY_LIBRARY}
ID_TO_MELODY = {m["id"]: m for m in MELODY_LIBRARY}
