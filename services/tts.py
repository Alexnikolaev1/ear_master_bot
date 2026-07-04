"""
services/tts.py
Озвучка текстовых объяснений теории через edge-tts (бесплатный TTS от Microsoft Edge).
Музыкальные примеры (ноты, интервалы) НИКОГДА не озвучиваются через TTS — только локальный синтез (audio_gen.py),
так как TTS не даёт точного контроля над частотой.
"""
import edge_tts

import config
from utils.media import temp_path


async def synthesize_speech(text: str) -> str:
    """
    Генерирует голосовое объяснение текста и сохраняет как mp3 во временный файл.
    Возвращает путь к файлу (нужно удалить после отправки через utils.media.cleanup_file).
    """
    out_path = temp_path("tts", ".mp3")
    communicate = edge_tts.Communicate(text, voice=config.TTS_VOICE)
    await communicate.save(out_path)
    return out_path
