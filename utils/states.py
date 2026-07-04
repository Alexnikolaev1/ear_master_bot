"""
FSM-состояния всех разделов тренировки.
Данные текущего упражнения и сессии хранятся в FSMContext.update_data.
"""
from aiogram.fsm.state import State, StatesGroup


class IntervalStates(StatesGroup):
    waiting_for_answer = State()


class ChordStates(StatesGroup):
    waiting_for_answer = State()


class NotationStates(StatesGroup):
    waiting_for_answer = State()


class IntonationStates(StatesGroup):
    waiting_for_voice = State()


class RhythmStates(StatesGroup):
    waiting_for_voice = State()
    waiting_for_meter = State()


class TheoryStates(StatesGroup):
    waiting_for_question = State()


class DegreeStates(StatesGroup):
    waiting_for_answer = State()
    waiting_for_imagine = State()
    waiting_for_imagine_result = State()


class HarmonyStates(StatesGroup):
    waiting_for_answer = State()


class DictationStates(StatesGroup):
    waiting_for_answer = State()


class SingingStates(StatesGroup):
    waiting_for_voice = State()


class WeakSpotStates(StatesGroup):
    waiting_for_answer = State()
    waiting_for_voice = State()


class LessonStates(StatesGroup):
    waiting_for_answer = State()
    waiting_for_voice = State()


class MelodyStates(StatesGroup):
    waiting_for_answer = State()
    waiting_for_voice = State()


# Все состояния тренировки — для общих кнопок «Стоп» / «Повторить»
TRAINING_STATES = (
    IntervalStates.waiting_for_answer,
    ChordStates.waiting_for_answer,
    NotationStates.waiting_for_answer,
    IntonationStates.waiting_for_voice,
    RhythmStates.waiting_for_voice,
    RhythmStates.waiting_for_meter,
    TheoryStates.waiting_for_question,
    DegreeStates.waiting_for_answer,
    DegreeStates.waiting_for_imagine,
    DegreeStates.waiting_for_imagine_result,
    HarmonyStates.waiting_for_answer,
    DictationStates.waiting_for_answer,
    SingingStates.waiting_for_voice,
    WeakSpotStates.waiting_for_answer,
    WeakSpotStates.waiting_for_voice,
    LessonStates.waiting_for_answer,
    LessonStates.waiting_for_voice,
    MelodyStates.waiting_for_answer,
    MelodyStates.waiting_for_voice,
)
