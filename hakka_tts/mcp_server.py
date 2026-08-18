from __future__ import annotations

import base64
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .client import HakkaTTSClient, HakkaTTSError, VOICES, safe_filename
from .effects import (
    TONE_PRESETS,
    compensated_speaking_rate,
    process_wav,
    resolve_tone,
)
from .rhythm import RHYTHM_PRESETS, prepare_speech


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
OUTPUT_DIR = PROJECT_ROOT / "output" / "audio"
SERVER_NAME = "taiwan-hakka-tts"
SERVER_VERSION = "0.5.0"


TOOLS: list[dict[str, Any]] = [
    {
        "name": "hakka_tts_status",
        "description": "驗證臺灣客語語音資料庫 TTS API 的登入狀態，不會揭露帳號或密碼。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True},
    },
    {
        "name": "hakka_tts_catalog",
        "description": "列出 API 支援的客語腔調、男女聲、文字格式與本機聲線預設。此工具不呼叫外部 API。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "hakka_tts_synthesize",
        "description": (
            "將文字合成臺灣客語 WAV 音檔。預設四縣腔女聲；海陸腔有男女聲，大埔腔只有女聲。"
            "可套用自然、低沉、年輕、兒童、溫暖、明亮或柔和聲線。"
            "可使用自然、真人口語、對話、敘事或播報節奏，自動整理斷句與停頓。"
            "會呼叫外部 API 並將音檔寫入專案 output/audio。"
        ),
        "inputSchema": {
            "type": "object",
            "required": ["text"],
            "additionalProperties": False,
            "properties": {
                "text": {"type": "string", "minLength": 1, "description": "要朗讀的文字"},
                "dialect": {
                    "type": "string",
                    "enum": ["sixian", "hailu", "dapu"],
                    "default": "sixian",
                    "description": "sixian=四縣、hailu=海陸、dapu=大埔",
                },
                "gender": {
                    "type": "string",
                    "enum": ["female", "male"],
                    "default": "female",
                },
                "text_type": {
                    "type": "string",
                    "enum": ["common", "characters", "roma"],
                    "default": "common",
                    "description": "common=中文、characters=客語漢字、roma=羅馬拼音",
                },
                "speaking_rate": {
                    "type": "number",
                    "minimum": 0.25,
                    "maximum": 4.0,
                    "default": 1.0,
                },
                "tone": {
                    "type": "string",
                    "enum": ["natural", "deep", "young", "child", "warm", "bright", "soft"],
                    "default": "natural",
                    "description": "聲線預設：自然、低沉、年輕、兒童、溫暖、明亮、柔和",
                },
                "rhythm": {
                    "type": "string",
                    "enum": ["original", "natural", "human", "conversation", "narration", "news"],
                    "default": "natural",
                    "description": "節奏預設：原始、自然、真人口語、對話、敘事、播報",
                },
                "pitch_semitones": {
                    "type": "number",
                    "minimum": -4.0,
                    "maximum": 4.0,
                    "description": "選填；覆寫聲線預設的音高，單位為半音",
                },
                "model": {"type": "string", "description": "選填；未填時自動使用預設模型"},
                "short_pause_ms": {"type": "integer", "minimum": 0},
                "long_pause_ms": {"type": "integer", "minimum": 0},
            },
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
    },
]


def emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def result(message_id: Any, value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": value}


def error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "hakka_tts_catalog":
        catalog = {
            "voices": [voice.__dict__ for voice in VOICES],
            "textTypes": {"common": "中文", "characters": "客語漢字", "roma": "羅馬拼音"},
            "tonePresets": [preset.__dict__ for preset in TONE_PRESETS.values()],
            "rhythmPresets": [preset.__dict__ for preset in RHYTHM_PRESETS.values()],
            "audio": {"format": "WAV", "sampleRate": 16000, "channels": 1, "encoding": "S16LE PCM"},
        }
        return {
            "content": [{"type": "text", "text": json.dumps(catalog, ensure_ascii=False, indent=2)}],
            "structuredContent": catalog,
        }

    client = HakkaTTSClient.from_env(ENV_FILE)
    if name == "hakka_tts_status":
        client.login()
        status = {"status": "ok", "expirationSeconds": client.expiration_seconds}
        return {
            "content": [{"type": "text", "text": "客語 TTS API 登入成功。"}],
            "structuredContent": status,
        }

    if name == "hakka_tts_synthesize":
        text = str(arguments.get("text", ""))
        dialect = str(arguments.get("dialect", "sixian"))
        gender = str(arguments.get("gender", "female"))
        tone = resolve_tone(
            str(arguments.get("tone", "natural")), arguments.get("pitch_semitones")
        )
        requested_rate = float(arguments.get("speaking_rate", 1.0))
        api_rate = compensated_speaking_rate(requested_rate, tone)
        text_type = str(arguments.get("text_type", "common"))
        speech = prepare_speech(
            text,
            text_type=text_type,
            rhythm=str(arguments.get("rhythm", "natural")),
            short_pause_ms=arguments.get("short_pause_ms"),
            long_pause_ms=arguments.get("long_pause_ms"),
        )
        raw_audio = client.synthesize(
            speech.text,
            dialect=dialect,
            gender=gender,
            text_type=text_type,
            speaking_rate=api_rate,
            model=arguments.get("model"),
            short_pause_ms=speech.short_pause_ms,
            long_pause_ms=speech.long_pause_ms,
        )
        audio = process_wav(raw_audio, tone)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        filename = safe_filename(f"hakka-{dialect}-{gender}-{tone.name}-{timestamp}") + ".wav"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = (OUTPUT_DIR / filename).resolve()
        output_path.write_bytes(audio)
        metadata = {
            "path": str(output_path),
            "bytes": len(audio),
            "dialect": dialect,
            "gender": gender,
            "tone": tone.name,
            "rhythm": speech.rhythm.name,
            "preparedText": speech.text,
            "pitchSemitones": tone.pitch_semitones,
            "requestedSpeakingRate": requested_rate,
            "apiSpeakingRate": round(api_rate, 6),
            "mimeType": "audio/wav",
        }
        return {
            "content": [
                {"type": "text", "text": f"客語音檔已產生：{output_path}"},
                {"type": "audio", "data": base64.b64encode(audio).decode("ascii"), "mimeType": "audio/wav"},
            ],
            "structuredContent": metadata,
        }

    raise HakkaTTSError(f"未知工具：{name}")


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        params = message.get("params") or {}
        requested_version = params.get("protocolVersion", "2025-06-18")
        return result(
            message_id,
            {
                "protocolVersion": requested_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "當使用者要求客語發音、朗讀或語音合成時，呼叫 hakka_tts_synthesize。"
                    "未指定時使用四縣腔女聲、common 文字格式與 1.0 語速。"
                    "聲線可選 natural、deep、young、child、warm、bright、soft；未指定使用 natural。"
                    "節奏可選 original、natural、human、conversation、narration、news；未指定使用 natural。"
                    "工具會回傳可播放的 WAV 與本機路徑；若 API 帳號過期，清楚回報 API 錯誤碼。"
                ),
            },
        )
    if method == "ping":
        return result(message_id, {})
    if method == "tools/list":
        return result(message_id, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            return result(message_id, call_tool(str(name), dict(arguments)))
        except HakkaTTSError as exc:
            return result(
                message_id,
                {
                    "content": [{"type": "text", "text": f"客語 TTS 呼叫失敗：{exc}"}],
                    "isError": True,
                },
            )
        except Exception as exc:
            return result(
                message_id,
                {
                    "content": [{"type": "text", "text": f"客語 TTS 工具發生未預期錯誤：{exc}"}],
                    "isError": True,
                },
            )
    if message_id is None:
        return None
    return error(message_id, -32601, f"Method not found: {method}")


def main() -> None:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = handle(message)
        except json.JSONDecodeError:
            response = error(None, -32700, "Parse error")
        except Exception as exc:
            response = error(message.get("id") if isinstance(message, dict) else None, -32603, str(exc))
        if response is not None:
            emit(response)


if __name__ == "__main__":
    main()
