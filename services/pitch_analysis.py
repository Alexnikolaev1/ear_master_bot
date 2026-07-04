"""
services/pitch_analysis.py
Анализ высоты тона (интонирования) голоса пользователя.

Пайплайн:
1. Входной файл (обычно .ogg/.oga от Telegram) конвертируется в WAV моно через pydub.
2. Ресемплинг вниз до ANALYSIS_SAMPLE_RATE (11025 Гц) — экономия CPU на Railway free tier.
3. librosa.pyin ищет основной тон (f0) по времени.
4. Берём медиану по стабильному (не NaN) участку — это надёжнее среднего при выбросах.
5. Переводим в центы относительно эталонной частоты.

Всё оборачивается в try/except с понятным fallback-сообщением, так как librosa —
самая "тяжёлая" и потенциально хрупкая зависимость в проекте.
"""
import os
import asyncio
import numpy as np

import config


class PitchAnalysisError(Exception):
    """Специальное исключение для читаемой обработки ошибок анализа в хендлерах."""
    pass


def _convert_to_wav_mono_sync(input_path: str, target_sr: int) -> str:
    from pydub import AudioSegment
    audio = AudioSegment.from_file(input_path)

    # обрезаем слишком длинные записи, чтобы не перегружать анализ
    max_ms = config.MAX_VOICE_DURATION_SEC * 1000
    if len(audio) > max_ms:
        audio = audio[:max_ms]

    audio = audio.set_channels(1).set_frame_rate(target_sr)
    wav_path = input_path + "_conv.wav"
    audio.export(wav_path, format="wav")
    return wav_path


def _analyze_pitch_sync(input_path: str, target_freq_hz: float) -> dict:
    """
    Синхронная (тяжёлая) часть анализа. Выполняется в отдельном потоке через to_thread.
    Возвращает словарь: {median_hz, deviation_cents, voiced_ratio}
    """
    import librosa
    import soundfile as sf

    target_sr = config.ANALYSIS_SAMPLE_RATE
    wav_path = None
    try:
        wav_path = _convert_to_wav_mono_sync(input_path, target_sr)
        y, sr = sf.read(wav_path, dtype="float32")

        if y.ndim > 1:
            y = np.mean(y, axis=1)

        if len(y) < sr * 0.1:
            raise PitchAnalysisError("Аудио слишком короткое для анализа.")

        f0, voiced_flag, voiced_probs = librosa.pyin(
            y,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
            sr=sr,
        )

        voiced_f0 = f0[~np.isnan(f0)] if f0 is not None else np.array([])
        voiced_ratio = len(voiced_f0) / len(f0) if f0 is not None and len(f0) else 0.0

        if len(voiced_f0) == 0:
            raise PitchAnalysisError(
                "Не удалось определить высоту тона — похоже, запись тихая или содержит только шум."
            )

        median_hz = float(np.median(voiced_f0))
        from utils.helpers import freq_to_cents_diff
        deviation_cents = freq_to_cents_diff(median_hz, target_freq_hz)

        return {
            "median_hz": median_hz,
            "deviation_cents": deviation_cents,
            "voiced_ratio": voiced_ratio,
        }
    finally:
        for p in (wav_path,):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


async def analyze_pitch(input_path: str, target_freq_hz: float) -> dict:
    """
    Публичная асинхронная точка входа. Гарантированно не блокирует event loop —
    вся тяжёлая работа librosa уходит в отдельный поток.
    """
    try:
        return await asyncio.to_thread(_analyze_pitch_sync, input_path, target_freq_hz)
    except PitchAnalysisError:
        raise
    except Exception as e:
        # librosa/soundfile могут падать по разным причинам (битый файл, нет кодека и т.п.)
        raise PitchAnalysisError(f"Сервис анализа тона временно недоступен: {e}")
