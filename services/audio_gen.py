"""
services/audio_gen.py
Локальный синтез звука без внешних платных API.

Используем numpy для генерации волн, soundfile для записи WAV в память/файл,
pydub + ffmpeg для конвертации WAV -> OGG (Opus), который Telegram принимает
как голосовое сообщение (voice note).

Все тяжёлые операции синтеза лёгкие по CPU (простая арифметика numpy),
но на всякий случай вызывающий код должен запускать их через asyncio.to_thread,
чтобы не блокировать event loop при параллельных запросах пользователей.
"""
import os
import numpy as np
import soundfile as sf
from pydub import AudioSegment

import config
from utils.media import cleanup_file, temp_path

__all__ = [
    "synth_tone",
    "synth_chord",
    "synth_sequence",
    "synth_click",
    "synth_rhythm_pattern",
    "save_as_voice_ogg",
    "cleanup_file",
]


def _generate_wave(freq: float, duration_ms: int, volume: float, waveform: str, sample_rate: int) -> np.ndarray:
    """Генерирует одну волну заданной формы. Возвращает numpy-массив float32 в диапазоне [-1, 1]."""
    t = np.linspace(0, duration_ms / 1000.0, int(sample_rate * duration_ms / 1000.0), endpoint=False)

    if waveform == "sine":
        wave = np.sin(2 * np.pi * freq * t)
    elif waveform == "triangle":
        wave = 2 * np.abs(2 * (t * freq - np.floor(t * freq + 0.5))) - 1
    elif waveform == "sawtooth":
        wave = 2 * (t * freq - np.floor(0.5 + t * freq))
    else:
        wave = np.sin(2 * np.pi * freq * t)

    # ADSR-подобная простая огибающая (fade-in/fade-out), чтобы не было щелчков на границах
    envelope = np.ones_like(wave)
    fade_len = max(1, int(sample_rate * 0.01))  # 10 мс
    fade_len = min(fade_len, len(wave) // 2) if len(wave) > 1 else 1
    if fade_len > 0:
        envelope[:fade_len] = np.linspace(0, 1, fade_len)
        envelope[-fade_len:] = np.linspace(1, 0, fade_len)

    return (wave * envelope * volume).astype(np.float32)


def _generate_piano_like_tone(freq: float, duration_ms: int, volume: float, sample_rate: int) -> np.ndarray:
    """Простая имитация тембра пианино через сумму гармоник с убывающей амплитудой."""
    t = np.linspace(0, duration_ms / 1000.0, int(sample_rate * duration_ms / 1000.0), endpoint=False)
    harmonics_amplitudes = [1.0, 0.5, 0.25, 0.12, 0.06]  # затухающие обертоны
    wave = np.zeros_like(t)
    for n, amp in enumerate(harmonics_amplitudes, start=1):
        wave += amp * np.sin(2 * np.pi * freq * n * t)
    wave /= sum(harmonics_amplitudes)

    # Экспоненциальное затухание, характерное для щипковых/ударных тембров (пианино)
    decay = np.exp(-3.0 * t / (duration_ms / 1000.0))
    wave *= decay

    return (wave * volume).astype(np.float32)


def synth_tone(freq: float, duration_ms: int = None, volume: float = None, timbre: str = "piano") -> np.ndarray:
    """Публичная функция синтеза одного тона. timbre: 'piano' | 'sine' | 'triangle' | 'sawtooth'."""
    duration_ms = duration_ms or config.DEFAULT_TONE_DURATION_MS
    volume = volume if volume is not None else config.DEFAULT_VOLUME
    sample_rate = config.SAMPLE_RATE

    if timbre == "piano":
        return _generate_piano_like_tone(freq, duration_ms, volume, sample_rate)
    else:
        return _generate_wave(freq, duration_ms, volume, timbre, sample_rate)


def synth_chord(freqs: list[float], duration_ms: int = None, volume: float = None, timbre: str = "piano") -> np.ndarray:
    """Синтез аккорда — суммирование нескольких тонов с нормализацией, чтобы избежать клиппинга."""
    duration_ms = duration_ms or config.DEFAULT_TONE_DURATION_MS
    volume = volume if volume is not None else config.DEFAULT_VOLUME

    tones = [synth_tone(f, duration_ms, volume, timbre) for f in freqs]
    max_len = max(len(t) for t in tones)
    mix = np.zeros(max_len, dtype=np.float32)
    for t in tones:
        mix[: len(t)] += t

    # нормализация суммарной громкости, чтобы избежать перегрузки (клиппинга)
    peak = np.max(np.abs(mix)) if len(mix) else 0
    if peak > 0.98:
        mix = mix / peak * 0.95

    return mix


def synth_sequence(freqs: list[float], note_duration_ms: int = 500, gap_ms: int = 100,
                    volume: float = None, timbre: str = "piano") -> np.ndarray:
    """Синтез мелодической последовательности — тоны один за другим с паузами."""
    sample_rate = config.SAMPLE_RATE
    gap_samples = int(sample_rate * gap_ms / 1000.0)
    gap = np.zeros(gap_samples, dtype=np.float32)

    chunks = []
    for f in freqs:
        chunks.append(synth_tone(f, note_duration_ms, volume, timbre))
        chunks.append(gap)
    return np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)


def synth_click(duration_ms: int = 40, freq: float = 1000.0, volume: float = 0.6) -> np.ndarray:
    """Короткий импульс-клик для ритмических упражнений (похож на щелчок метронома)."""
    sample_rate = config.SAMPLE_RATE
    t = np.linspace(0, duration_ms / 1000.0, int(sample_rate * duration_ms / 1000.0), endpoint=False)
    wave = np.sin(2 * np.pi * freq * t)
    decay = np.exp(-30 * t)  # быстрое затухание — короткий перкуссивный щелчок
    return (wave * decay * volume).astype(np.float32)


def synth_with_context(
    context_freqs: list[float],
    target_freqs: list[float],
    *,
    context_note_ms: int = 280,
    gap_after_context_ms: int = 350,
    target_as_chord: bool = False,
    target_note_ms: int = 700,
    target_gap_ms: int = 120,
) -> np.ndarray:
    """
    Проигрывает контекст тональности (например I–III–V–I), паузу, затем цель.
    target_as_chord=True — цель как аккорд, иначе мелодическая последовательность.
    """
    sample_rate = config.SAMPLE_RATE
    context = synth_sequence(context_freqs, note_duration_ms=context_note_ms, gap_ms=60)
    pause = np.zeros(int(sample_rate * gap_after_context_ms / 1000.0), dtype=np.float32)
    if target_as_chord:
        target = synth_chord(target_freqs, duration_ms=max(target_note_ms, 1200))
    else:
        target = synth_sequence(target_freqs, note_duration_ms=target_note_ms, gap_ms=target_gap_ms)
    return np.concatenate([context, pause, target])


def synth_melody_rhythmic(
    freqs: list,
    rhythm_quarters: list,
    *,
    quarter_ms: int = 320,
    gap_ms: int = 30,
) -> np.ndarray:
    """Мелодия с относительными длительностями (1.0 = четверть)."""
    chunks: list[np.ndarray] = []
    gap = np.zeros(int(config.SAMPLE_RATE * gap_ms / 1000.0), dtype=np.float32)
    for i, freq in enumerate(freqs):
        dur = max(0.25, float(rhythm_quarters[i] if i < len(rhythm_quarters) else 1.0))
        note_ms = int(quarter_ms * dur)
        chunks.append(synth_tone(freq, duration_ms=note_ms))
        if i < len(freqs) - 1:
            chunks.append(gap)
    return np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)


def synth_melody_with_cadence(
    cadence_chords,
    freqs: list,
    rhythm_quarters: list,
    *,
    quarter_ms: int = 320,
    pause_ms: int = 400,
) -> np.ndarray:
    """Каденция I–IV–V–I, пауза, затем узнаваемая мелодия."""
    sample_rate = config.SAMPLE_RATE
    cadence = synth_chord_progression(cadence_chords, chord_ms=600, gap_ms=80)
    pause = np.zeros(int(sample_rate * pause_ms / 1000.0), dtype=np.float32)
    melody = synth_melody_rhythmic(freqs, rhythm_quarters, quarter_ms=quarter_ms)
    return np.concatenate([cadence, pause, melody])


def synth_fet_question(
    cadence_chords,
    target_freq: float,
    *,
    chord_ms: int = 650,
    gap_ms: int = 90,
    pause_ms: int = 400,
    target_ms: int = 1000,
) -> np.ndarray:
    """
    Вопрос метода Functional Ear Trainer (Alain Benbassat):
    каденция I–IV–V–I → пауза → целевая ступень.
    """
    sample_rate = config.SAMPLE_RATE
    cadence = synth_chord_progression(cadence_chords, chord_ms=chord_ms, gap_ms=gap_ms)
    pause = np.zeros(int(sample_rate * pause_ms / 1000.0), dtype=np.float32)
    target = synth_tone(target_freq, duration_ms=target_ms)
    return np.concatenate([cadence, pause, target])


def synth_chord_progression(
    chords,
    *,
    chord_ms: int = 900,
    gap_ms: int = 150,
    context_freqs=None,
) -> np.ndarray:
    """Последовательность аккордов, опционально с тональным контекстом в начале."""
    sample_rate = config.SAMPLE_RATE
    gap = np.zeros(int(sample_rate * gap_ms / 1000.0), dtype=np.float32)
    chunks: list[np.ndarray] = []
    if context_freqs:
        chunks.append(synth_sequence(context_freqs, note_duration_ms=250, gap_ms=50))
        chunks.append(np.zeros(int(sample_rate * 0.35), dtype=np.float32))
    for i, freqs in enumerate(chords):
        chunks.append(synth_chord(freqs, duration_ms=chord_ms))
        if i < len(chords) - 1:
            chunks.append(gap)
    return np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)


def synth_rhythm_pattern(pattern_intervals_ms: list[int], click_duration_ms: int = 40) -> np.ndarray:
    """
    Синтезирует ритмический рисунок по списку интервалов между ударами (в мс).
    Первый удар звучит в момент t=0, далее — через накопленные интервалы.
    """
    sample_rate = config.SAMPLE_RATE
    total_duration_ms = sum(pattern_intervals_ms) + click_duration_ms + 200
    total_samples = int(sample_rate * total_duration_ms / 1000.0)
    track = np.zeros(total_samples, dtype=np.float32)

    click = synth_click(click_duration_ms)
    current_ms = 0
    for interval in [0] + pattern_intervals_ms:
        current_ms += interval
        start_sample = int(sample_rate * current_ms / 1000.0)
        end_sample = min(start_sample + len(click), total_samples)
        track[start_sample:end_sample] += click[: end_sample - start_sample]

    return track


async def save_as_voice_ogg(samples: np.ndarray, sample_rate: int = None) -> str:
    """
    Сохраняет numpy-массив как OGG (Opus) файл, готовый к отправке как voice в Telegram.
    Возвращает путь к временному файлу. Вызывающий код должен удалить файл после отправки.
    """
    import asyncio
    return await asyncio.to_thread(_save_as_voice_ogg_sync, samples, sample_rate)


def _save_as_voice_ogg_sync(samples: np.ndarray, sample_rate: int = None) -> str:
    sample_rate = sample_rate or config.SAMPLE_RATE
    wav_path = temp_path("em", ".wav")
    ogg_path = temp_path("em", ".ogg")

    # нормализация в int16 диапазон для записи WAV
    samples_clipped = np.clip(samples, -1.0, 1.0)
    sf.write(wav_path, samples_clipped, sample_rate, subtype="PCM_16")

    # конвертация WAV -> OGG (Opus) через pydub/ffmpeg
    audio_segment = AudioSegment.from_wav(wav_path)
    audio_segment.export(ogg_path, format="ogg", codec="libopus", bitrate="32k")

    # исходный WAV больше не нужен
    try:
        os.remove(wav_path)
    except OSError:
        pass

    return ogg_path

