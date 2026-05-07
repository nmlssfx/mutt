#!/usr/bin/env python3
"""CLI-версия синтезатора речи Xiaomi MiMo TTS.

Поддерживает Pay-as-you-go (sk-) и Token Plan (tp-).

Примеры:
  python mimo_tts_cli.py --text "Привет мир" -o test.mp3
  python mimo_tts_cli.py --text "Hello" --voice default_en --style Happy -o hello.mp3
  echo "Текст" | python mimo_tts_cli.py -o from_stdin.mp3
  python mimo_tts_cli.py --text "Тест" --auth-mode token-cn -o test.mp3
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from mutt import (
    AUTH_MODES,
    RECOMMENDED_STYLES,
    VOICES,
    TTSConfig,
    detect_mode,
    resolve_base_url,
    synthesize_and_save,
    logger,
)


def build_parser() -> argparse.ArgumentParser:
    epilog = (
        "Примеры:\n"
        "  %(prog)s --text \"Привет\" -o out.mp3\n"
        "  %(prog)s --text Hello --voice default_en --style Happy -o out.mp3\n"
        "  %(prog)s --auth-mode token-cn --text \"Тест\" -o t.mp3\n"
        "  cat text.txt | %(prog)s -o out.mp3\n"
        "\nРежимы авторизации:\n"
    )
    for key, desc in AUTH_MODES.items():
        epilog += f"  {key:12s}  {desc}\n"

    parser = argparse.ArgumentParser(
        description="Xiaomi MiMo TTS Generator — CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )

    # Источники текста
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--text", "-t", type=str, default=None, help="Текст для синтеза")
    src.add_argument("--file", "-f", type=str, default=None, help="Файл с текстом")

    # Параметры
    parser.add_argument("--output", "-o", type=str, default="output.mp3", help="Выходной файл (.mp3 / .wav)")
    parser.add_argument("--voice", "-v", type=str, default="mimo_default", choices=list(VOICES.values()), help="Голос")
    parser.add_argument("--style", "-s", type=str, default="", help="Стиль речи (можно несколько через пробел)")
    parser.add_argument("--format", type=str, default="wav", choices=["wav", "pcm16"], help="Аудио-формат из API")
    parser.add_argument("--user-context", "-c", type=str, default="", help="Контекст (сообщение role=user)")
    parser.add_argument("--api-key", "-k", type=str, default=None, help="API-ключ (если не задан MIMO_API_KEY)")
    parser.add_argument(
        "--auth-mode", "-a", type=str, default="auto",
        choices=list(AUTH_MODES.keys()),
        help="Режим аутентификации (по умолчанию автоопределение)",
    )
    parser.add_argument("--list-voices", action="store_true", help="Показать доступные голоса")
    parser.add_argument("--list-styles", action="store_true", help="Показать рекомендуемые стили")
    parser.add_argument("--list-modes", action="store_true", help="Показать режимы авторизации")
    parser.add_argument("--verbose", action="store_true", help="Подробный лог (DEBUG)")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # ── Справка ───────────────────────────────────────────────────
    if args.list_voices:
        print("Доступные голоса:")
        for name, val in VOICES.items():
            print(f"  {val:20s}  {name}")
        sys.exit(0)

    if args.list_styles:
        print("Рекомендуемые стили (можно комбинировать):")
        for s in RECOMMENDED_STYLES:
            print(f"  {s!r}" if s else "  <пусто> — нейтральный")
        sys.exit(0)

    if args.list_modes:
        print("Режимы авторизации:")
        for key, desc in AUTH_MODES.items():
            print(f"  {key:12s}  {desc}")
        sys.exit(0)

    # ── Логирование ───────────────────────────────────────────────
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.getLogger("mutt").setLevel(level)

    # ── Текст ─────────────────────────────────────────────────────
    text: str | None = args.text
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read().strip()
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    if not text:
        parser.print_help()
        print("\nОшибка: укажите текст через --text, --file или stdin.")
        sys.exit(1)

    # ── API-ключ ──────────────────────────────────────────────────
    api_key = args.api_key or os.environ.get("MIMO_API_KEY", "")
    if not api_key:
        parser.print_help()
        print(
            "\nОшибка: API-ключ не указан.\n"
            "  Укажите через --api-key или задайте переменную MIMO_API_KEY."
        )
        sys.exit(1)

    # ── Конфиг ────────────────────────────────────────────────────
    config = TTSConfig(
        api_key=api_key,
        model="mimo-v2-tts",
        voice=args.voice,
        style=args.style,
        audio_format=args.format,
        user_context=args.user_context,
        text=text,
        auth_mode=args.auth_mode,
    )

    if args.verbose:
        print(f"🔑 Режим: {args.auth_mode}")
        print(f"🌐 Base URL: {config.base_url}")
        print(f"🗣 Голос: {config.voice}")
        if config.style:
            print(f"🎭 Стиль: {config.style}")

    # ── Запуск ────────────────────────────────────────────────────
    try:
        final = synthesize_and_save(config, args.output)
        print(f"\n✓ Готово: {final}")
    except Exception as exc:
        print(f"\n✗ Ошибка: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
