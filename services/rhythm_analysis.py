"""
services/rhythm_analysis.py
Анализ ритма, простуканного/пропетого пользователем.

Используем librosa.onset.onset_detect, чтобы найти моменты атаки звука (удары),
затем сравниваем интервалы между ударами с эталонным ритмическим рисунком.
"""
import os
import asyncio
import numpy as np

import config
from services.pitch_analysis import PitchAnalysisError, _convert_to_wav_mono_sync


class RhythmAnalysisError(Exception):
    pass


def _analyze_rhythm_sync(input_path: str, expected_intervals_ms: list[int]) -> dict:
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
            raise RhythmAnalysisError("Аудио слишком короткое для анализа ритма.")

        onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=True)

        # Отфильтровываем ложные повторные срабатывания на одном и том же ударе
        # (например, атака + быстрый "хвост" призвука распознаются как два отдельных onset).
        # Минимальный физически разумный интервал между реальными ударами — 80 мс.
        MIN_GAP_SEC = 0.08
        filtered_onsets = []
        for t in onset_frames.tolist():
            if not filtered_onsets or (t - filtered_onsets[-1]) >= MIN_GAP_SEC:
                filtered_onsets.append(t)

        if len(filtered_onsets) < 2:
            raise RhythmAnalysisError(
                "Не удалось найти достаточно ударов в записи. Постучите чётче и ближе к микрофону."
            )

        onset_times_ms = [t * 1000 for t in filtered_onsets]
        user_intervals_ms = [
            onset_times_ms[i + 1] - onset_times_ms[i] for i in range(len(onset_times_ms) - 1)
        ]

        # Сравниваем количество и относительные пропорции интервалов (нормируем по первому интервалу,
        # так как пользователь может сыграть чуть быстрее/медленнее эталонного темпа)
        n = min(len(user_intervals_ms), len(expected_intervals_ms))
        errors = []
        if n > 0 and user_intervals_ms[0] > 0:
            scale = expected_intervals_ms[0] / user_intervals_ms[0]
        else:
            scale = 1.0

        for i in range(n):
            scaled_user = user_intervals_ms[i] * scale
            expected = expected_intervals_ms[i]
            error_pct = abs(scaled_user - expected) / expected * 100 if expected else 0
            errors.append(error_pct)

        avg_error_pct = float(np.mean(errors)) if errors else 100.0
        worst_idx = int(np.argmax(errors)) if errors else -1

        return {
            "onsets_detected": len(onset_times_ms),
            "user_intervals_ms": user_intervals_ms,
            "avg_error_pct": avg_error_pct,
            "worst_beat_index": worst_idx + 2 if worst_idx >= 0 else None,  # +2: удобная нумерация для пользователя
            "is_correct": avg_error_pct <= 20.0,  # допуск ±20% по длительности интервалов
        }
    finally:
        if wav_path and os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except OSError:
                pass


async def analyze_rhythm(input_path: str, expected_intervals_ms: list[int]) -> dict:
    try:
        return await asyncio.to_thread(_analyze_rhythm_sync, input_path, expected_intervals_ms)
    except RhythmAnalysisError:
        raise
    except Exception as e:
        raise RhythmAnalysisError(f"Сервис анализа ритма временно недоступен: {e}")
