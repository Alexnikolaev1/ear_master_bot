"""
config.py
Центральная конфигурация бота EAR MASTER AI.
Все настройки читаются из переменных окружения (для Railway) либо .env (локально).
"""
import os
import tempfile
from dotenv import load_dotenv

# Подгружаем .env, если он есть (для локальной разработки)
load_dotenv()

# --- Обязательные секреты ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# --- Вебхук ---
# Railway сам прокидывает публичный домен через переменную RAILWAY_STATIC_URL
# либо мы задаём WEBHOOK_HOST вручную.
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST") or os.getenv("RAILWAY_STATIC_URL", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_me_secret_path")
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"https://{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else ""

# Порт для aiohttp-сервера (Railway передаёт свой PORT)
PORT = int(os.getenv("PORT", "8080"))
HOST = "0.0.0.0"

# --- Пути ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "earmaster.db")
NOTE_FREQS_PATH = os.path.join(BASE_DIR, "data", "note_freqs.json")
# /tmp на Linux/Railway; на Windows — системный temp
TMP_DIR = os.getenv("TMP_DIR") or (
    "/tmp" if os.name != "nt" and os.path.isdir("/tmp") else tempfile.gettempdir()
)

# --- Аудио-параметры (подобраны для экономии CPU на бесплатном Railway) ---
SAMPLE_RATE = 22050          # частота дискретизации синтеза
ANALYSIS_SAMPLE_RATE = 11025  # частота дискретизации для анализа голоса (ресемплинг вниз)
MAX_VOICE_DURATION_SEC = 10   # ограничение длины голосового сообщения пользователя
DEFAULT_TONE_DURATION_MS = 900
DEFAULT_VOLUME = 0.35         # линейная амплитуда (0..1), чтобы не было клиппинга при сумме гармоник

# --- Параметры оценки интонации ---
CENTS_TOLERANCE_PERFECT = 15   # почти идеально
CENTS_TOLERANCE_OK = 25        # засчитывается как верно
CENTS_TOLERANCE_CLOSE = 50     # "близко, но мимо"

# --- TTS ---
TTS_VOICE = "ru-RU-DmitryNeural"

# --- Кэш ---
GEMINI_CACHE_TTL_DAYS = 30

# --- Rate limiting (защита от превышения бесплатных квот) ---
GEMINI_MAX_CALLS_PER_MIN = 10        # запас ниже реального лимита Gemini Flash free tier
GEMINI_MAX_CALLS_PER_DAY = 1000
GROQ_MAX_CALLS_PER_MIN = 15

# --- Часовой пояс по умолчанию ---
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow")

# --- Проверка обязательных переменных при старте ---
def validate_config() -> None:
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY (функции теории/адаптивного плана будут отключены)")
    if not GROQ_API_KEY:
        missing.append("GROQ_API_KEY (голосовые команды будут отключены)")
    if missing:
        print("⚠️  Внимание, не заданы переменные окружения:", ", ".join(missing))
