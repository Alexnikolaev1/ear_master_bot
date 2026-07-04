# 🎧 EAR MASTER AI

Персональный AI-тренер по музыкальному слуху, теории музыки, ритму и нотной грамоте — в Telegram.

Полностью на бесплатных технологиях: локальный синтез звука (numpy/scipy), анализ голоса
(librosa), бесплатные лимиты Google Gemini и Groq, бесплатный хостинг Railway.

## Возможности

- 🎯 **Урок дня** — готовая сессия на 5–7 минут (интонация → интервал → ступень → ритм)
- 💪 **Слабые места** — spaced repetition по реальным ошибкам
- 🎵 **Интервалы** — мелодические/гармонические, с уклоном в слабые места
- 🎼 **Ступени** — функциональный слух в тональности (I–III–V–I → ступень)
- 🎹 **Аккорды** — типы трезвучий и септаккордов
- 🏛 **Гармония** — обращения трезвучий и каденции (V–I, IV–I, V–VI…)
- 🥁 **Ритм** — повтор рисунка + определение размера (3/4, 4/4)
- 🎤 **Пение** — спой интервал или ступень (активный слух)
- 📖 **Ноты** — чтение с листа + озвучка
- ✍️ **Диктант** — мелодический контур по ступеням
- 📚 **Теория** — Gemini + TTS
- 📊 **Прогресс** — уровень, XP, слабые места, графики, AI-советы

## Быстрый старт (локально, через polling)

```bash
git clone <репозиторий>
cd ear_master_bot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# ffmpeg обязателен для pydub (конвертация WAV <-> OGG)
# Ubuntu/Debian: sudo apt install ffmpeg
# macOS: brew install ffmpeg
# Windows: https://ffmpeg.org/download.html

cp .env.example .env
# заполните TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, GROQ_API_KEY в .env

python run_polling.py
```

## Деплой на Railway (вебхук-режим)

1. Создайте новый проект на [Railway](https://railway.app), подключите репозиторий.
2. Railway автоматически распознает `nixpacks.toml`, который добавит `ffmpeg`.
3. Задайте переменные окружения:
   - `TELEGRAM_BOT_TOKEN`
   - `GEMINI_API_KEY`
   - `GROQ_API_KEY`
   - `WEBHOOK_HOST` — публичный домен без `https://`
   - `WEBHOOK_SECRET` — секретная строка для пути вебхука
4. `Procfile` запускает `python bot.py`.
5. Проверьте `/start` в Telegram.

## Структура проекта

```
ear_master_bot/
├── bot.py                 # webhook-режим (Railway)
├── run_polling.py         # polling для локальной разработки
├── config.py              # конфигурация из env
├── database.py            # SQLite: пользователи, XP, лог, кэш, достижения
├── handlers/
│   ├── common.py          # Стоп / Повторить
│   ├── start.py           # /start, /help, /menu
│   ├── lesson.py          # урок дня
│   ├── weakspots.py       # работа над ошибками
│   ├── intervals.py       # интервалы
│   ├── degrees.py         # функциональный слух (ступени)
│   ├── chords.py          # аккорды
│   ├── harmony.py         # обращения и каденции
│   ├── rhythm.py          # ритм + размер такта
│   ├── singing.py         # активное пение
│   ├── intonation.py      # интонация
│   ├── notation.py        # нотная грамота
│   ├── dictation.py       # мелодический диктант
│   ├── theory.py          # теория (Gemini + TTS)
│   ├── stats.py           # прогресс
│   └── settings.py        # настройки + голосовые команды
├── services/
│   ├── exercise.py        # единый движок: XP, уровень, достижения
│   ├── music_theory.py    # тональности, ступени, каденции, диктант
│   ├── audio_gen.py       # синтез тонов/аккордов/ритмов/контекста
│   ├── pitch_analysis.py  # высота тона
│   ├── rhythm_analysis.py # onset detection
│   ├── notation_gen.py    # нотный стан
│   ├── gemini_service.py  # теория и рекомендации
│   ├── groq_service.py    # Whisper-команды
│   └── tts.py             # edge-tts
├── middlewares/
│   ├── user.py            # авто-регистрация пользователя
│   └── errors.py          # глобальная обработка ошибок
├── utils/
│   ├── media.py           # скачивание/отправка/очистка медиа
│   ├── keyboards.py       # клавиатуры
│   ├── helpers.py         # ноты, интервалы, адаптивная сложность
│   ├── states.py          # FSM
│   └── rate_limiter.py    # лимиты API
└── data/
    └── note_freqs.json
```

## Архитектура

- **FSM** для всех тренировок (вместо in-memory `_pending`) — корректные сессии и повтор звука.
- **Единый движок упражнений** (`services/exercise.py`) — логирование, XP, уровень, достижения.
- **Адаптивная сложность** — пулы интервалов/аккордов/ритмов зависят от уровня пользователя.
- **Middleware** — регистрация пользователя и перехват необработанных ошибок.
- **Общий media-слой** — скачивание голоса, отправка voice/photo, очистка temp-файлов.

## Технические детали

- Синтез: 22050 Гц; анализ голоса: 11025 Гц.
- Голосовые сообщения ограничены 10 секундами.
- Тяжёлые операции (librosa, matplotlib, pydub) — через `asyncio.to_thread`.
- Ответы Gemini кэшируются в SQLite на 30 дней.
- Rate limiter in-memory (один инстанс).
- `TMP_DIR` кроссплатформенный (Windows / Linux / Railway).

## Известные ограничения

- На нотном стане — только натуральные ноты (без диезов/бемолей).
- Rate limiter и FSM — in-memory; для нескольких инстансов нужен Redis.
