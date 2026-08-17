from __future__ import annotations

import re
from dataclasses import dataclass

from .client import HakkaTTSError


@dataclass(frozen=True)
class RhythmPreset:
    name: str
    display_name: str
    description: str
    short_pause_ms: int | None
    long_pause_ms: int | None
    max_clause_chars: int | None


@dataclass(frozen=True)
class PreparedSpeech:
    text: str
    short_pause_ms: int | None
    long_pause_ms: int | None
    rhythm: RhythmPreset


RHYTHM_PRESETS: dict[str, RhythmPreset] = {
    "original": RhythmPreset(
        "original", "原始", "保留輸入文字與 API 預設停頓", None, None, None
    ),
    "natural": RhythmPreset(
        "natural", "自然", "清理多餘空格並依語意柔和斷句", 100, 300, 20
    ),
    "conversation": RhythmPreset(
        "conversation", "對話", "短停頓較俐落，適合日常對話", 85, 260, 18
    ),
    "narration": RhythmPreset(
        "narration", "敘事", "段落與句尾停頓較長，適合故事導覽", 140, 420, 24
    ),
    "news": RhythmPreset(
        "news", "播報", "節奏清楚穩定，適合公告與新聞稿", 105, 340, 22
    ),
}

RHYTHM_ALIASES = {
    "原始": "original",
    "自然": "natural",
    "對話": "conversation",
    "敘事": "narration",
    "播報": "news",
}

_HAN = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_PUNCTUATION = "，。！？；：、,.!?;:"
_CONNECTORS = (
    "所以",
    "因為",
    "毋過",
    "但是",
    "然後",
    "另外",
    "假使",
    "若係",
    "還有",
)
_SOFT_BOUNDARIES = set("个兜咧啊哦呢嗎吂也就係會愛毋有在到過來去做講看聽時前後")


def resolve_rhythm(name: str = "natural") -> RhythmPreset:
    key = RHYTHM_ALIASES.get(name.strip(), name.strip().lower())
    preset = RHYTHM_PRESETS.get(key)
    if preset is None:
        raise HakkaTTSError(f"不支援的節奏預設：{name}")
    return preset


def _normalize_spacing(text: str, text_type: str) -> str:
    value = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n")]
    lines = [line for line in lines if line]
    value = "。".join(line.rstrip("。") for line in lines)
    if text_type != "roma":
        value = re.sub(rf"(?<=[{_HAN}])\s+(?=[{_HAN}])", "", value)
    return re.sub(r"。{2,}", "。", value)


def _add_connector_pauses(clause: str) -> str:
    result = clause
    for connector in _CONNECTORS:
        start = 0
        while True:
            index = result.find(connector, start)
            if index < 4:
                break
            if result[index - 1] not in _PUNCTUATION:
                result = result[:index] + "，" + result[index:]
                start = index + len(connector) + 1
            else:
                start = index + len(connector)
    return result


def _split_long_han_clause(clause: str, maximum: int) -> str:
    if len(clause) <= maximum or any(char in _PUNCTUATION for char in clause):
        return clause
    chunks: list[str] = []
    remainder = clause
    while len(remainder) > maximum:
        lower = max(1, int(maximum * 0.6))
        break_at = next(
            (
                index + 1
                for index in range(maximum - 1, lower - 1, -1)
                if remainder[index] in _SOFT_BOUNDARIES
            ),
            maximum,
        )
        chunks.append(remainder[:break_at])
        remainder = remainder[break_at:]
    chunks.append(remainder)
    return "，".join(chunk for chunk in chunks if chunk)


def prepare_text(text: str, text_type: str, preset: RhythmPreset) -> str:
    if preset.name == "original":
        return text.strip()
    value = _normalize_spacing(text, text_type)
    if text_type == "roma" or preset.max_clause_chars is None:
        return value

    parts = re.split(r"([。！？!?；;])", value)
    prepared: list[str] = []
    for part in parts:
        if not part or part in "。！？!?；;":
            prepared.append(part)
            continue
        with_connectors = _add_connector_pauses(part)
        clauses = with_connectors.split("，")
        prepared.append(
            "，".join(
                _split_long_han_clause(clause, preset.max_clause_chars)
                for clause in clauses
            )
        )
    return "".join(prepared)


def prepare_speech(
    text: str,
    *,
    text_type: str,
    rhythm: str = "natural",
    short_pause_ms: int | None = None,
    long_pause_ms: int | None = None,
) -> PreparedSpeech:
    preset = resolve_rhythm(rhythm)
    prepared_text = prepare_text(text, text_type, preset)
    if not prepared_text:
        raise HakkaTTSError("合成文字不可為空白")
    return PreparedSpeech(
        text=prepared_text,
        short_pause_ms=(
            int(short_pause_ms) if short_pause_ms is not None else preset.short_pause_ms
        ),
        long_pause_ms=(
            int(long_pause_ms) if long_pause_ms is not None else preset.long_pause_ms
        ),
        rhythm=preset,
    )
