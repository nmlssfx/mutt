"""
mimo_tts.py — Универсальный TTS модуль.

Поддерживаемые бэкенды:
  - mimo     Xiaomi MiMo TTS  (бесплатный Token Plan / Pay-as-you-go)
  - openrouter  OpenRouter TTS (GPT-4o Mini TTS и другие)

Документация MiMo:   https://platform.xiaomimimo.com/docs/en-US/usage-guide/speech-synthesis
Документация OpenRouter: https://openrouter.ai/docs/guides/overview/multimodal/tts
"""

from __future__ import annotations

import base64
import logging
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import requests

__version__ = "1.0.0.3"
logger = logging.getLogger("mutt")


# ──────────────────────────────────────────────
#  Загрузка .env (без внешних зависимостей)
# ──────────────────────────────────────────────


def load_env(env_path: str | Path | None = None) -> None:
    """Загрузить переменные из .env файла в os.environ."""
    path = Path(env_path) if env_path else Path(__file__).resolve().parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("\"'")
        if key not in os.environ:
            os.environ[key] = val


load_env()

# ═══════════════════════════════════════════════════════════════════
#  Бэкенды
# ═══════════════════════════════════════════════════════════════════

BACKEND_MIMO = "mimo"
BACKEND_OPENROUTER = "openrouter"
BACKEND_GROQ = "groq"

BACKENDS: dict[str, str] = {
    BACKEND_MIMO: "🎙 MiMo (бесплатный Token Plan)",
    BACKEND_OPENROUTER: "🌐 OpenRouter (мультимодельный)",
    BACKEND_GROQ: "⚡ Groq (Orpheus, бесплатно)",
    "openai": "🤖 OpenAI TTS (прямой доступ)",
    "elevenlabs": "🗣 ElevenLabs (8 голосов)",
    "mistral": "🔮 Mistral Voxtral TTS",
}

# ── MiMo ─────────────────────────────────────────────────────────

DEFAULT_MODEL = "mimo-v2-tts"

API_BASE_URLS: dict[str, str] = {
    "payg": "https://api.xiaomimimo.com/v1",
    "token-cn": "https://token-plan-cn.xiaomimimo.com/v1",
    "token-sgp": "https://token-plan-sgp.xiaomimimo.com/v1",
    "token-ams": "https://token-plan-ams.xiaomimimo.com/v1",
}

AUTH_MODES: dict[str, str] = {
    "payg": "☁️ Pay-as-you-go (sk-...)",
    "token-cn": "🔑 Token Plan — Китай (tp-...)",
    "token-sgp": "🔑 Token Plan — Сингапур (tp-...)",
    "token-ams": "🔑 Token Plan — Европа (tp-...)",
    "auto": "🤖 Определить автоматически",
}

# MiMo голоса (из документации)
MIMO_VOICES: dict[str, str] = {
    "MiMo-Default (авто)": "mimo_default",
    "Китайский женский": "default_zh",
    "Английский женский": "default_en",
}

# MiMo стили (из документации)
MIMO_STYLES: list[str] = [
    "", "Happy", "Sad", "Angry", "Whisper",
    "Speed up", "Slow down", "Singing/Sing",
    "Northeastern dialect", "Sichuan dialect", "Cantonese",
    "Taiwanese accent", "Clamped voice",
    "Sun Wukong (role)", "Lin Daiyu (role)",
]

MIMO_STYLE_CATEGORIES: dict[str, list[str]] = {
    "Эмоции":    ["", "Happy", "Sad", "Angry"],
    "Скорость":  ["", "Speed up", "Slow down"],
    "Манера":    ["", "Whisper", "Clamped voice", "Taiwanese accent"],
    "Диалекты":  ["", "Northeastern dialect", "Sichuan dialect",
                    "Henan dialect", "Cantonese"],
    "Персонажи": ["", "Sun Wukong", "Lin Daiyu"],
    "Пение":     ["", "sing", "唱歌"],
}

MIMO_AUDIO_TAGS: list[dict] = [
    {"label": "💨 Вздох",     "tag": " _long sigh_ "},
    {"label": "🤧 Кашель",    "tag": " \\[cough\\] "},
    {"label": "😮‍💨 Тяж.дых.", "tag": " \\[heavy breathing\\] "},
    {"label": "😭 Рыдания",   "tag": " (sobbing) "},
    {"label": "😆 Смех",      "tag": " (sudden laugh) "},
    {"label": "🤫 Шёпот",     "tag": " \\[whisper\\] "},
    {"label": "⏸ Пауза",     "tag": " ... "},
    {"label": "🗣 Чёткость",  "tag": " \\[clear\\] "},
]

# ── OpenRouter ────────────────────────────────────────────────────

OR_DEFAULT_MODEL = "openai/gpt-4o-mini-tts-2025-12-15"
OR_API_BASE = "https://openrouter.ai/api/v1"

# Модели с ценами (отсортированы по цене за 1M символов)
# Данные из документации OpenRouter (май 2026)
OR_MODELS_INFO: list[dict] = [
    {
        "id": "openai/gpt-4o-mini-tts-2025-12-15",
        "label": "OpenAI GPT-4o Mini TTS",
        "price": "$0.60/1M симв.",
        "price_sort": 0.60,
        "voices": {
            "Alloy (нейтр.)": "alloy",
            "Echo (тёплый)": "echo",
            "Fable (брит.)": "fable",
            "Onyx (увер.)": "onyx",
            "Nova (жен.)": "nova",
            "Shimmer (эмоц.)": "shimmer",
        },
        "lang": "мультиязычный (вкл. русский)",
    },
    {
        "id": "hexgrad/kokoro-82m",
        "label": "Kokoro 82M (open-weight)",
        "price": "$0.62/1M симв.",
        "price_sort": 0.62,
        "voices": {
            "Default (авто)": "alloy",
        },
        "lang": "8 языков (без русского)",
    },
    {
        "id": "google/gemini-3.1-flash-tts-preview",
        "label": "Google Gemini 3.1 Flash TTS",
        "price": "$1 + $20/1M ток.",
        "price_sort": 1.0,
        "voices": {
            "Default (авто)": "alloy",
        },
        "lang": "70+ языков (вкл. русский)",
    },
    {
        "id": "sesame/csm-1b",
        "label": "Sesame CSM 1B (conv.)",
        "price": "$7/1M ток.",
        "price_sort": 7.0,
        "voices": {
            "Default (авто)": "alloy",
        },
        "lang": "английский",
    },
    {
        "id": "canopylabs/orpheus-3b-0.1-ft",
        "label": "Orpheus 3B (Canopy)",
        "price": "$7/1M ток.",
        "price_sort": 7.0,
        "voices": {
            "Default (авто)": "alloy",
        },
        "lang": "английский",
    },
    {
        "id": "zyphra/zonos-v0.1-hybrid",
        "label": "Zonos v0.1 Hybrid (Zyphra)",
        "price": "$7/1M ток.",
        "price_sort": 7.0,
        "voices": {
            "Default (авто)": "alloy",
        },
        "lang": "английский",
    },
    {
        "id": "mistralai/voxtral-mini-tts-2603",
        "label": "Mistral Voxtral Mini TTS",
        "price": "$16/1M симв.",
        "price_sort": 16.0,
        "voices": {
            "Default (авто)": "alloy",
        },
        "lang": "мультиязычный",
    },
]

# Комбобокс: метка → id модели
OR_MODEL_CHOICES: list[str] = [
    f"{m['label']}  ({m['price']})" for m in OR_MODELS_INFO
]
OR_MODEL_IDS: list[str] = [m["id"] for m in OR_MODELS_INFO]

# Голоса для текущей модели (или дефолт)
OR_DEFAULT_VOICES: dict[str, str] = {
    "Alloy (нейтр.)": "alloy",
    "Echo (тёплый)": "echo",
    "Fable (брит.)": "fable",
    "Onyx (увер.)": "onyx",
    "Nova (жен.)": "nova",
    "Shimmer (эмоц.)": "shimmer",
}


def get_voices_for_model(model_id: str) -> dict[str, str]:
    """Получить список голосов для конкретной модели."""
    for m in OR_MODELS_INFO:
        if m["id"] == model_id:
            return m.get("voices", OR_DEFAULT_VOICES)
    return OR_DEFAULT_VOICES


def get_model_info(model_id: str) -> dict | None:
    """Получить полную информацию о модели."""
    for m in OR_MODELS_INFO:
        if m["id"] == model_id:
            return m
    return None


# ── Groq ─────────────────────────────────────────────────────────

GROQ_API_BASE = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "canopylabs/orpheus-v1-english"
# Формат: только WAV! response_format не поддерживает mp3
GROQ_RESPONSE_FORMAT = "wav"

GROQ_VOICES_EN: dict[str, str] = {
    "Autumn (жен.)": "autumn", "Diana (жен.)": "diana",
    "Hannah (жен.)": "hannah", "Austin (муж.)": "austin",
    "Daniel (муж.)": "daniel", "Troy (муж.)": "troy",
}
GROQ_VOICES_AR: dict[str, str] = {
    "Abdullah (муж.)": "abdullah", "Fahad (муж.)": "fahad",
    "Sultan (муж.)": "sultan", "Lulwa (жен.)": "lulwa",
    "Noura (жен.)": "noura", "Aisha (жен.)": "aisha",
}
GROQ_VOICES: dict[str, str] = {**GROQ_VOICES_EN, **GROQ_VOICES_AR}

GROQ_MODELS_INFO: list[dict] = [
    {"id": "canopylabs/orpheus-v1-english", "label": "Orpheus English", "price": "$22/1M симв.", "price_sort": 22,
     "voices": GROQ_VOICES_EN, "lang": "английский", "limit": 200},
    {"id": "canopylabs/orpheus-arabic-saudi", "label": "Orpheus Arabic Saudi", "price": "$40/1M симв.", "price_sort": 40,
     "voices": GROQ_VOICES_AR, "lang": "арабский (сауд.)", "limit": 200},
]


# ── OpenAI Direct ────────────────────────────────────────────────

OPENAI_API_BASE = "https://api.openai.com/v1"
OPENAI_DEFAULT_MODEL = "tts-1"  # или tts-1-hd
OPENAI_VOICES: dict[str, str] = {
    "Alloy (нейтр.)": "alloy", "Echo (тёплый)": "echo",
    "Fable (брит.)": "fable", "Onyx (увер.)": "onyx",
    "Nova (жен.)": "nova", "Shimmer (эмоц.)": "shimmer",
}


# ── ElevenLabs ───────────────────────────────────────────────────

ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
ELEVENLABS_DEFAULT_VOICE = "pNInz6obpgDQGcFmaJgB"
ELEVENLABS_DEFAULT_MODEL = "eleven_multilingual_v2"
# 8 premade voices из документации (voice_id)
ELEVENLABS_VOICES: dict[str, str] = {
    "Rachel (жен., амер.)": "21m00Tcm4TlvDq8ikWAM",
    "Adam (муж., амер.)": "pNInz6obpgDQGcFmaJgB",
    "Antoni (муж., брит.)": "ErXwobaYiN019PkySvjV",
    "Bella (жен., амер.)": "EXAVITQu4vrRVY0wG7P2",
    "Domi (жен., амер.)": "AZnzlk1XvdvUeBnXmlld",
    "Elli (жен., амер.)": "MF3mGyEYCl7XYWbV9V6O",
    "Josh (муж., амер.)": "TxGEqnHWrfWFTfGW9XjX",
    "Sam (муж., амер.)": "yoZ06aMxZJJ28mfd3POQ",
}


# ── Mistral ──────────────────────────────────────────────────────

MISTRAL_API_BASE = "https://api.mistral.ai/v1"
MISTRAL_DEFAULT_MODEL = "mistral-voxtral-tts-26-03"
MISTRAL_VOICES: dict[str, str] = {"Default (авто)": "default"}  # 20 пресетов через voice cloning API


# ═══════════════════════════════════════════════════════════════════
#  Модели данных
# ═══════════════════════════════════════════════════════════════════

SUPPORTED_AUDIO_FORMATS = ["wav", "pcm16"]


@dataclass
class TTSConfig:
    """Параметры синтеза речи."""

    backend: str = BACKEND_MIMO  # mimo | openrouter | groq | openai | elevenlabs | mistral

    # MiMo
    api_key: str = ""
    model: str = DEFAULT_MODEL
    voice: str = "mimo_default"
    style: str = ""
    auth_mode: str = "auto"

    # OpenRouter
    or_api_key: str = ""
    or_model: str = OR_DEFAULT_MODEL
    or_voice: str = "alloy"

    # Groq
    groq_api_key: str = ""
    groq_model: str = GROQ_DEFAULT_MODEL
    groq_voice: str = "default"

    # OpenAI Direct
    oai_api_key: str = ""
    oai_voice: str = "alloy"

    # ElevenLabs
    el_api_key: str = ""
    el_voice: str = ELEVENLABS_DEFAULT_VOICE
    el_model: str = ELEVENLABS_DEFAULT_MODEL

    # Mistral
    mistral_api_key: str = ""
    mistral_voice: str = "default"

    # Общие
    audio_format: Literal["wav", "pcm16"] = "wav"
    user_context: str = ""
    text: str = ""

    @property
    def base_url(self) -> str:
        if self.backend == BACKEND_MIMO:
            return resolve_base_url(self.api_key, self.auth_mode)
        if self.backend == BACKEND_OPENROUTER:
            return OR_API_BASE
        if self.backend == BACKEND_GROQ:
            return GROQ_API_BASE
        return ""


@dataclass
class TTSResult:
    """Результат синтеза."""

    audio_data: bytes
    audio_format: str
    output_path: Path | None = None
    duration_ms: int = 0
    request_id: str = ""


# ═══════════════════════════════════════════════════════════════════
#  Вспомогательные функции (MiMo)
# ═══════════════════════════════════════════════════════════════════


def detect_mode(api_key: str) -> str:
    key = api_key.strip().lower()
    if key.startswith("tp-"):
        return "token-sgp"
    return "payg"


def resolve_base_url(api_key: str, mode: str | None = None) -> str:
    if mode and mode != "auto":
        return API_BASE_URLS[mode]
    return API_BASE_URLS[detect_mode(api_key)]


# ═══════════════════════════════════════════════════════════════════
#  Синтез: диспетчеризация по бэкенду
# ═══════════════════════════════════════════════════════════════════


def synthesize_tts(config: TTSConfig) -> TTSResult:
    """Синтезировать речь — вызывает нужный бэкенд."""
    if config.backend == BACKEND_OPENROUTER:
        return _synthesize_openrouter(config)
    if config.backend == BACKEND_GROQ:
        return _synthesize_groq(config)
    if config.backend == "openai":
        return _synthesize_openai(config)
    if config.backend == "elevenlabs":
        return _synthesize_elevenlabs(config)
    if config.backend == "mistral":
        return _synthesize_mistral(config)
    return _synthesize_mimo(config)


# ───── MiMo ───────────────────────────────────────────────────────


def _synthesize_mimo(config: TTSConfig) -> TTSResult:
    if not config.api_key:
        raise ValueError("Укажите API-ключ MiMo.")

    content = config.text
    if config.style:
        content = f"<style>{config.style}</style>{config.text}"

    messages: list[dict] = [{"role": "assistant", "content": content}]
    if config.user_context.strip():
        messages.insert(0, {"role": "user", "content": config.user_context.strip()})

    payload: dict = {
        "model": config.model,
        "messages": messages,
        "audio": {"format": config.audio_format, "voice": config.voice},
    }

    headers = {"api-key": config.api_key, "Content-Type": "application/json"}
    url = f"{config.base_url}/chat/completions"

    logger.debug("→ [MiMo] POST %s  model=%s  voice=%s", url, config.model, config.voice)
    t0 = time.perf_counter()
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    elapsed = time.perf_counter() - t0

    if resp.status_code != 200:
        raise RuntimeError(f"MiMo API {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    audio_b64 = data["choices"][0]["message"]["audio"]["data"]
    audio_bytes = base64.b64decode(audio_b64)
    rid = data.get("id", "")

    logger.info("✓ [MiMo] %d байт за %.1fс  id=%s", len(audio_bytes), elapsed, rid)
    return TTSResult(audio_data=audio_bytes, audio_format=config.audio_format, request_id=rid)


# ───── OpenRouter ─────────────────────────────────────────────────


def _synthesize_openrouter(config: TTSConfig) -> TTSResult:
    key = config.or_api_key or os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise ValueError("Укажите API-ключ OpenRouter.")

    payload = {
        "model": config.or_model,
        "input": config.text,
        "voice": config.or_voice,
        "response_format": "mp3",
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    url = f"{OR_API_BASE}/audio/speech"

    logger.debug("→ [OpenRouter] POST %s  model=%s  voice=%s",
                 url, config.or_model, config.or_voice)
    t0 = time.perf_counter()
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    elapsed = time.perf_counter() - t0

    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter API {resp.status_code}: {resp.text[:500]}")

    audio_bytes = resp.content
    logger.info("✓ [OpenRouter] %d байт за %.1fс", len(audio_bytes), elapsed)

    # OpenRouter всегда отдаёт MP3 — возвращаем как pcm16+заголовок
    # чтобы save_as_wav работал, сохраняем как есть (MP3 данные)
    return TTSResult(audio_data=audio_bytes, audio_format="mp3", request_id="")


# ───── Groq ───────────────────────────────────────────────────────


def _synthesize_groq(config: TTSConfig) -> TTSResult:
    key = config.groq_api_key or os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise ValueError("Укажите API-ключ Groq.")
    if len(config.text) > 200:
        raise ValueError(f"Groq Orpheus: максимум 200 символов (у вас {len(config.text)})")
    payload = {"model": config.groq_model, "input": config.text,
               "voice": config.groq_voice, "response_format": GROQ_RESPONSE_FORMAT}
    resp = requests.post(f"{GROQ_API_BASE}/audio/speech",
                         json=payload, headers={"Authorization": f"Bearer {key}",
                                                "Content-Type": "application/json"}, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Groq API {resp.status_code}: {resp.text[:300]}")
    logger.info("✓ [Groq] %d байт", len(resp.content))
    return TTSResult(audio_data=resp.content, audio_format="wav")


# ───── OpenAI Direct ──────────────────────────────────────────────


def _synthesize_openai(config: TTSConfig) -> TTSResult:
    key = config.oai_api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("Укажите API-ключ OpenAI.")
    payload = {"model": "tts-1", "input": config.text,
               "voice": config.oai_voice, "response_format": "mp3"}
    resp = requests.post(f"{OPENAI_API_BASE}/audio/speech",
                         json=payload, headers={"Authorization": f"Bearer {key}",
                                                "Content-Type": "application/json"}, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI API {resp.status_code}: {resp.text[:300]}")
    logger.info("✓ [OpenAI] %d байт", len(resp.content))
    return TTSResult(audio_data=resp.content, audio_format="mp3")


# ───── ElevenLabs ─────────────────────────────────────────────────


def _synthesize_elevenlabs(config: TTSConfig) -> TTSResult:
    key = config.el_api_key or os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise ValueError("Укажите API-ключ ElevenLabs.")
    voice_id = config.el_voice
    url = f"{ELEVENLABS_API_BASE}/text-to-speech/{voice_id}"
    payload = {"text": config.text, "model_id": config.el_model,
               "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
    headers = {"xi-api-key": key, "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs API {resp.status_code}: {resp.text[:300]}")
    logger.info("✓ [ElevenLabs] %d байт", len(resp.content))
    return TTSResult(audio_data=resp.content, audio_format="mp3")


# ───── Mistral ────────────────────────────────────────────────────


def _synthesize_mistral(config: TTSConfig) -> TTSResult:
    key = config.mistral_api_key or os.environ.get("MISTRAL_API_KEY", "")
    if not key:
        raise ValueError("Укажите API-ключ Mistral.")
    payload = {"model": MISTRAL_DEFAULT_MODEL, "input": config.text,
               "voice": config.mistral_voice, "response_format": "mp3"}
    resp = requests.post(f"{MISTRAL_API_BASE}/audio/speech",
                         json=payload, headers={"Authorization": f"Bearer {key}",
                                                "Content-Type": "application/json"}, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Mistral API {resp.status_code}: {resp.text[:300]}")
    logger.info("✓ [Mistral] %d байт", len(resp.content))
    return TTSResult(audio_data=resp.content, audio_format="mp3")


# ═══════════════════════════════════════════════════════════════════
#  Сохранение / конвертация
# ═══════════════════════════════════════════════════════════════════


def _ensure_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def save_audio(result: TTSResult, path: str | Path) -> Path:
    """
    Сохранить аудио-данные в файл.

    Для MiMo (WAV/PCM16) — пишет WAV.
    Для OpenRouter (MP3) — пишет MP3.
    """
    path = Path(path)
    data = result.audio_data

    if result.audio_format == "mp3":
        path.write_bytes(data)
        logger.info("✓ Сохранено: %s  (%d байт)", path, len(data))
        return path

    # WAV / PCM16
    if result.audio_format == "pcm16":
        sample_rate = 24000
        bits = 16
        ch = 1
        data_size = len(data)
        header = struct.pack(
            "<4sI4s4sIHHIIHH",
            b"RIFF", 36 + data_size, b"WAVE",
            b"fmt ", 16, 1, ch, sample_rate,
            sample_rate * ch * bits // 8,
            ch * bits // 8, bits,
        )
        data = header + data

    path.write_bytes(data)
    logger.info("✓ Сохранено: %s  (%d байт)", path, len(data))
    return path


def convert_to_mp3(
    input_path: str | Path,
    output_path: str | Path | None = None,
    bitrate: str = "192k",
) -> Path | None:
    if not _ensure_ffmpeg():
        logger.warning("ffmpeg не найден.")
        return None
    inp = Path(input_path)
    out = Path(output_path) if output_path else inp.with_suffix(".mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(inp), "-codec:a", "libmp3lame", "-b:a", bitrate, str(out)],
        capture_output=True, check=True,
    )
    logger.info("✓ Конвертировано в MP3: %s", out)
    return out


def synthesize_and_save(config: TTSConfig, output_path: str | Path) -> Path:
    """Синтезировать и сохранить в файл."""
    result = synthesize_tts(config)
    out = Path(output_path)

    is_mp3 = result.audio_format == "mp3"
    no_ffmpeg = not _ensure_ffmpeg()

    if out.suffix.lower() == ".mp3" and no_ffmpeg and not is_mp3:
        out = out.with_suffix(".wav")
        logger.info("ffmpeg не найден → .wav")

    saved = save_audio(result, out)

    if is_mp3:
        return saved  # уже MP3
    if no_ffmpeg:
        return saved  # WAV

    mp3 = convert_to_mp3(saved, output_path)
    return mp3 or saved


# ═══════════════════════════════════════════════════════════════════
#  Калькулятор стоимости
# ═══════════════════════════════════════════════════════════════════


def estimate_cost(text_len: int, backend: str, model_id: str = "",
                  or_model_idx: int = 0, groq_model: str = "") -> tuple[str, str]:
    """
    Рассчитать примерную стоимость запроса.
    Возвращает (стоимость_строкой, лимиты_строкой).
    """
    if backend == BACKEND_MIMO:
        return ("бесплатно (Token Plan)", "")

    if backend == BACKEND_OPENROUTER:
        if 0 <= or_model_idx < len(OR_MODELS_INFO):
            info = OR_MODELS_INFO[or_model_idx]
            price_str = info["price"]
            raw = price_str.replace("$", "").replace(",", "").strip()
            try:
                # Берём первое число из строки (цена input-токенов/символов)
                match = re.search(r"[\d.]+", raw)
                if match:
                    cost_per_1m = float(match.group())
                else:
                    return (price_str, f"{text_len} симв.")
                cost = cost_per_1m * text_len / 1_000_000
                limit_info = info.get("limit", 0)
                if limit_info and text_len > limit_info:
                    return (f"≈ ${cost:.6f}" if cost < 0.001 else f"≈ ${cost:.4f}",
                            f"❌ лимит {limit_info} симв.")
                return (f"≈ ${cost:.6f}" if cost < 0.001 else f"≈ ${cost:.4f}", f"{text_len} симв.")
            except:
                return (price_str, f"{text_len} симв.")

    if backend == BACKEND_GROQ:
        is_ar = "arabic" in groq_model.lower() if groq_model else False
        price_per_1m = 40 if is_ar else 22
        cost = price_per_1m * text_len / 1_000_000
        limit = f"макс 200 симв. [{text_len}/200]"
        if text_len > 200:
            return (f"≈ ${cost:.4f}" if cost >= 0.001 else f"≈ ${cost:.6f}", f"❌ превышен лимит! {limit}")
        return (f"≈ ${cost:.4f}" if cost >= 0.001 else f"≈ ${cost:.6f}", limit)

    if backend == "openai":
        cost = 15 * text_len / 1_000_000
        return (f"≈ ${cost:.6f}" if cost < 0.001 else f"≈ ${cost:.4f}", f"{text_len} симв.")

    if backend == "elevenlabs":
        return (f"~{text_len} кредитов", f"бесплатно 10K/мес")

    if backend == "mistral":
        cost = 16 * text_len / 1_000_000
        return (f"≈ ${cost:.6f}" if cost < 0.001 else f"≈ ${cost:.4f}", f"{text_len} симв.")

    return ("—", f"{text_len} симв.")


# ═══════════════════════════════════════════════════════════════════
#  Preview
# ═══════════════════════════════════════════════════════════════════

PREVIEW_DIR = Path(tempfile.gettempdir()) / "mutt_preview"


def synthesize_preview(config: TTSConfig) -> Path:
    """Синтезировать во временный файл для прослушивания."""
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    is_or = config.backend == BACKEND_OPENROUTER
    preview_path = PREVIEW_DIR / ("preview.mp3" if is_or else "preview.wav")

    result = synthesize_tts(config)
    save_audio(result, preview_path)
    logger.info("🎧 Preview: %s (%d байт)", preview_path, preview_path.stat().st_size)
    return preview_path


def open_in_player(path: str | Path) -> None:
    """Открыть в системном плеере."""
    p = Path(path)
    logger.info("▶ Открываю в плеере: %s", p)
    try:
        if os.name == "nt":
            os.startfile(str(p))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])
    except Exception as exc:
        logger.error("Не удалось открыть плеер: %s", exc)
        raise
