from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import HakkaTTSClient, HakkaTTSError, VOICES
from .effects import (
    TONE_PRESETS,
    compensated_speaking_rate,
    process_wav,
    resolve_tone,
)
from .rhythm import RHYTHM_PRESETS, prepare_speech


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV = PROJECT_ROOT / ".env"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="客家委員會臺灣客語語音合成 API")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="驗證 API 登入狀態")
    subparsers.add_parser("catalog", help="顯示手冊列出的腔調與語者")
    subparsers.add_parser("models", help="取得 API 模型清單")
    subparsers.add_parser("text-types", help="取得 API 文字格式清單")

    synthesize = subparsers.add_parser("synthesize", help="合成客語 WAV 音檔")
    synthesize.add_argument("text")
    synthesize.add_argument("--dialect", default="sixian")
    synthesize.add_argument("--gender", default="female")
    synthesize.add_argument("--text-type", default="common")
    synthesize.add_argument("--rate", type=float, default=1.0)
    synthesize.add_argument("--tone", choices=tuple(TONE_PRESETS), default="natural")
    synthesize.add_argument(
        "--rhythm", choices=tuple(RHYTHM_PRESETS), default="natural"
    )
    synthesize.add_argument("--pitch-semitones", type=float)
    synthesize.add_argument("--model")
    synthesize.add_argument("--short-pause-ms", type=int)
    synthesize.add_argument("--long-pause-ms", type=int)
    synthesize.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "output" / "audio" / "hakka-speech.wav"
    )
    return parser


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "catalog":
            print_json(
                {
                    "voices": [voice.__dict__ for voice in VOICES],
                    "tonePresets": [preset.__dict__ for preset in TONE_PRESETS.values()],
                    "rhythmPresets": [
                        preset.__dict__ for preset in RHYTHM_PRESETS.values()
                    ],
                }
            )
            return 0

        client = HakkaTTSClient.from_env(args.env_file)
        if args.command == "status":
            client.login()
            print_json({"status": "ok", "expirationSeconds": client.expiration_seconds})
        elif args.command == "models":
            print_json(client.list_models())
        elif args.command == "text-types":
            print_json(client.text_type_options())
        elif args.command == "synthesize":
            tone = resolve_tone(args.tone, args.pitch_semitones)
            api_rate = compensated_speaking_rate(args.rate, tone)
            speech = prepare_speech(
                args.text,
                text_type=args.text_type,
                rhythm=args.rhythm,
                short_pause_ms=args.short_pause_ms,
                long_pause_ms=args.long_pause_ms,
            )
            raw_audio = client.synthesize(
                speech.text,
                dialect=args.dialect,
                gender=args.gender,
                text_type=args.text_type,
                speaking_rate=api_rate,
                model=args.model,
                short_pause_ms=speech.short_pause_ms,
                long_pause_ms=speech.long_pause_ms,
            )
            audio = process_wav(raw_audio, tone)
            output = args.output.resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(audio)
            print_json(
                {
                    "status": "ok",
                    "path": str(output),
                    "bytes": len(audio),
                    "tone": tone.name,
                    "rhythm": speech.rhythm.name,
                    "preparedText": speech.text,
                    "pitchSemitones": tone.pitch_semitones,
                    "requestedSpeakingRate": args.rate,
                    "apiSpeakingRate": round(api_rate, 6),
                }
            )
        return 0
    except HakkaTTSError as error:
        print_json({"status": "error", "message": str(error), "code": error.code})
        return 1


if __name__ == "__main__":
    sys.exit(main())
