"""Клавиатуры бота."""
from __future__ import annotations

import random

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from utils.helpers import (
    BTN_FET_IMAGINE,
    BTN_FET_INNER,
    BTN_FET_NORMAL,
    BTN_HARMONIC,
    BTN_MELODIC,
    BTN_MELODY_DEGREE,
    BTN_MELODY_DICTATION,
    BTN_MELODY_NAME,
    BTN_MELODY_SING,
    BTN_METER,
    BTN_PATTERN,
    BTN_REPLAY,
    BTN_STOP,
    CHORDS,
    INTERVALS,
    MAIN_MENU_BUTTONS,
)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    rows = [MAIN_MENU_BUTTONS[i : i + 2] for i in range(0, len(MAIN_MENU_BUTTONS), 2)]
    keyboard = [[KeyboardButton(text=t) for t in row] for row in rows]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def training_keyboard(
    *,
    with_replay: bool = False,
    with_mode: bool = False,
    with_rhythm_mode: bool = False,
    with_fet_modes: bool = False,
    with_melody_modes: bool = False,
) -> ReplyKeyboardMarkup:
    """Клавиатура во время тренировки."""
    rows: list[list[KeyboardButton]] = []
    if with_mode:
        rows.append([
            KeyboardButton(text=BTN_MELODIC),
            KeyboardButton(text=BTN_HARMONIC),
        ])
    if with_rhythm_mode:
        rows.append([
            KeyboardButton(text=BTN_PATTERN),
            KeyboardButton(text=BTN_METER),
        ])
    if with_fet_modes:
        rows.append([
            KeyboardButton(text=BTN_FET_NORMAL),
            KeyboardButton(text=BTN_FET_INNER),
        ])
        rows.append([KeyboardButton(text=BTN_FET_IMAGINE)])
    if with_melody_modes:
        rows.append([
            KeyboardButton(text=BTN_MELODY_NAME),
            KeyboardButton(text=BTN_MELODY_DEGREE),
        ])
        rows.append([
            KeyboardButton(text=BTN_MELODY_DICTATION),
            KeyboardButton(text=BTN_MELODY_SING),
        ])
    controls = [KeyboardButton(text=BTN_STOP)]
    if with_replay:
        controls.append(KeyboardButton(text=BTN_REPLAY))
    rows.append(controls)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def _choice_keyboard(items: list[str], prefix: str, per_row: int = 2) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, name in enumerate(items, start=1):
        # callback_data лимит 64 байта — короткие префиксы
        row.append(InlineKeyboardButton(text=name, callback_data=f"{prefix}:{name}"))
        if i % per_row == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def interval_choice_keyboard(pool: dict | None = None) -> InlineKeyboardMarkup:
    names = list((pool or INTERVALS).keys())
    return _choice_keyboard(names, "interval_ans")


def chord_choice_keyboard(pool: dict | None = None) -> InlineKeyboardMarkup:
    names = list((pool or CHORDS).keys())
    return _choice_keyboard(names, "chord_ans")


def notation_choice_keyboard(
    correct_note: str,
    note_pool: list[str],
    options_count: int = 4,
) -> InlineKeyboardMarkup:
    pool = [n for n in note_pool if n != correct_note]
    correct_idx = note_pool.index(correct_note)
    nearby = sorted(pool, key=lambda n: abs(note_pool.index(n) - correct_idx))[: (options_count - 1) * 2]
    distractors = random.sample(nearby, min(options_count - 1, len(nearby)))
    options = distractors + [correct_note]
    random.shuffle(options)
    return _choice_keyboard(options, "notation_ans")


def choice_keyboard(items: list[str], prefix: str, per_row: int = 2) -> InlineKeyboardMarkup:
    return _choice_keyboard(items, prefix, per_row)
