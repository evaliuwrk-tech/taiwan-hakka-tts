from __future__ import annotations

import io
import math
import sys
import wave
from array import array
from dataclasses import dataclass, replace

from .client import HakkaTTSError


@dataclass(frozen=True)
class TonePreset:
    name: str
    display_name: str
    description: str
    pitch_semitones: float = 0.0
    low_shelf_db: float = 0.0
    high_shelf_db: float = 0.0
    output_gain_db: float = 0.0
    presence_db: float = 0.0


TONE_PRESETS: dict[str, TonePreset] = {
    "natural": TonePreset("natural", "自然", "保留 API 原始聲音"),
    "deep": TonePreset(
        "deep", "低沉", "大幅降低音高、強化低頻並壓低明亮度", -4.9, 10.0, -8.0, -5.0, -5.0
    ),
    "young": TonePreset(
        "young", "年輕", "明顯提高音高、減少厚重感並增加清脆感", 3.8, -6.0, 8.0, -5.5, 5.0
    ),
    "child": TonePreset(
        "child", "兒童", "大幅提高音高、削弱低頻並塑造高亮童聲", 7.0, -10.0, 11.0, -8.0, 7.0
    ),
    "warm": TonePreset(
        "warm", "溫暖", "降低音高、明顯增加厚度並柔化高頻", -1.8, 8.0, -7.0, -4.5, 1.5
    ),
    "bright": TonePreset(
        "bright", "明亮", "提高音高並大幅增加高頻與語音穿透力", 1.8, -7.0, 11.0, -8.0, 7.0
    ),
    "soft": TonePreset(
        "soft", "柔和", "稍降音高並強烈收斂高頻與存在感", -0.9, 3.0, -12.0, -3.5, -6.0
    ),
}

TONE_ALIASES = {
    "自然": "natural",
    "低沉": "deep",
    "年輕": "young",
    "兒童": "child",
    "溫暖": "warm",
    "明亮": "bright",
    "柔和": "soft",
}


def resolve_tone(name: str = "natural", pitch_semitones: float | None = None) -> TonePreset:
    key = TONE_ALIASES.get(name.strip(), name.strip().lower())
    preset = TONE_PRESETS.get(key)
    if preset is None:
        raise HakkaTTSError(f"不支援的聲線預設：{name}")
    if pitch_semitones is None:
        return preset
    if not -4.0 <= pitch_semitones <= 4.0:
        raise HakkaTTSError("自訂音高必須介於 -4 與 +4 個半音之間")
    return replace(preset, pitch_semitones=float(pitch_semitones))


def pitch_ratio(semitones: float) -> float:
    return 2.0 ** (semitones / 12.0)


def compensated_speaking_rate(requested_rate: float, tone: TonePreset) -> float:
    if not 0.25 <= requested_rate <= 4.0:
        raise HakkaTTSError("語速必須介於 0.25 與 4.0 之間")
    api_rate = requested_rate / pitch_ratio(tone.pitch_semitones)
    if not 0.25 <= api_rate <= 4.0:
        raise HakkaTTSError(
            "此語速與音高組合超出 API 可接受範圍；請降低語速或音高變化"
        )
    return api_rate


def _decode_pcm16_mono(wav_bytes: bytes) -> tuple[int, array]:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as reader:
            if reader.getnchannels() != 1:
                raise HakkaTTSError("聲線處理目前只支援單聲道 WAV")
            if reader.getsampwidth() != 2:
                raise HakkaTTSError("聲線處理目前只支援 16-bit PCM WAV")
            if reader.getcomptype() != "NONE":
                raise HakkaTTSError("聲線處理目前只支援未壓縮 PCM WAV")
            sample_rate = reader.getframerate()
            raw_frames = reader.readframes(reader.getnframes())
    except (wave.Error, EOFError) as error:
        raise HakkaTTSError("無法解析 TTS 回傳的 WAV 音檔") from error
    samples = array("h")
    samples.frombytes(raw_frames)
    if sys.byteorder != "little":
        samples.byteswap()
    return sample_rate, samples


def _encode_pcm16_mono(sample_rate: int, samples: array) -> bytes:
    encoded = array("h", samples)
    if sys.byteorder != "little":
        encoded.byteswap()
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(encoded.tobytes())
    return output.getvalue()


def _resample_for_pitch(samples: list[float], ratio: float) -> list[float]:
    if math.isclose(ratio, 1.0, abs_tol=1e-9) or len(samples) < 2:
        return samples.copy()
    output_length = max(1, round(len(samples) / ratio))
    output: list[float] = []
    last_index = len(samples) - 1
    for output_index in range(output_length):
        source_position = output_index * ratio
        left = min(int(source_position), last_index)
        right = min(left + 1, last_index)
        fraction = source_position - left
        output.append(samples[left] + (samples[right] - samples[left]) * fraction)
    return output


def _shelf_coefficients(
    sample_rate: int, frequency: float, gain_db: float, *, high: bool
) -> tuple[float, float, float, float, float]:
    amplitude = 10.0 ** (gain_db / 40.0)
    omega = 2.0 * math.pi * frequency / sample_rate
    cosine = math.cos(omega)
    sine = math.sin(omega)
    alpha = sine / 2.0 * math.sqrt(2.0)
    root_term = 2.0 * math.sqrt(amplitude) * alpha

    if high:
        b0 = amplitude * ((amplitude + 1) + (amplitude - 1) * cosine + root_term)
        b1 = -2 * amplitude * ((amplitude - 1) + (amplitude + 1) * cosine)
        b2 = amplitude * ((amplitude + 1) + (amplitude - 1) * cosine - root_term)
        a0 = (amplitude + 1) - (amplitude - 1) * cosine + root_term
        a1 = 2 * ((amplitude - 1) - (amplitude + 1) * cosine)
        a2 = (amplitude + 1) - (amplitude - 1) * cosine - root_term
    else:
        b0 = amplitude * ((amplitude + 1) - (amplitude - 1) * cosine + root_term)
        b1 = 2 * amplitude * ((amplitude - 1) - (amplitude + 1) * cosine)
        b2 = amplitude * ((amplitude + 1) - (amplitude - 1) * cosine - root_term)
        a0 = (amplitude + 1) + (amplitude - 1) * cosine + root_term
        a1 = -2 * ((amplitude - 1) + (amplitude + 1) * cosine)
        a2 = (amplitude + 1) + (amplitude - 1) * cosine - root_term

    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def _peaking_coefficients(
    sample_rate: int, frequency: float, q: float, gain_db: float
) -> tuple[float, float, float, float, float]:
    amplitude = 10.0 ** (gain_db / 40.0)
    omega = 2.0 * math.pi * frequency / sample_rate
    cosine = math.cos(omega)
    alpha = math.sin(omega) / (2.0 * q)
    b0 = 1.0 + alpha * amplitude
    b1 = -2.0 * cosine
    b2 = 1.0 - alpha * amplitude
    a0 = 1.0 + alpha / amplitude
    a1 = -2.0 * cosine
    a2 = 1.0 - alpha / amplitude
    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def _apply_biquad(
    samples: list[float], coefficients: tuple[float, float, float, float, float]
) -> list[float]:
    b0, b1, b2, a1, a2 = coefficients
    x1 = x2 = y1 = y2 = 0.0
    output: list[float] = []
    for sample in samples:
        filtered = b0 * sample + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        output.append(filtered)
        x2, x1 = x1, sample
        y2, y1 = y1, filtered
    return output


def process_wav(wav_bytes: bytes, tone: TonePreset) -> bytes:
    if (
        math.isclose(tone.pitch_semitones, 0.0, abs_tol=1e-9)
        and math.isclose(tone.low_shelf_db, 0.0, abs_tol=1e-9)
        and math.isclose(tone.high_shelf_db, 0.0, abs_tol=1e-9)
        and math.isclose(tone.output_gain_db, 0.0, abs_tol=1e-9)
        and math.isclose(tone.presence_db, 0.0, abs_tol=1e-9)
    ):
        return wav_bytes

    sample_rate, pcm_samples = _decode_pcm16_mono(wav_bytes)
    samples = [float(sample) for sample in pcm_samples]
    samples = _resample_for_pitch(samples, pitch_ratio(tone.pitch_semitones))

    if not math.isclose(tone.low_shelf_db, 0.0, abs_tol=1e-9):
        samples = _apply_biquad(
            samples,
            _shelf_coefficients(sample_rate, 250.0, tone.low_shelf_db, high=False),
        )
    if not math.isclose(tone.high_shelf_db, 0.0, abs_tol=1e-9):
        samples = _apply_biquad(
            samples,
            _shelf_coefficients(sample_rate, 3000.0, tone.high_shelf_db, high=True),
        )
    if not math.isclose(tone.presence_db, 0.0, abs_tol=1e-9):
        samples = _apply_biquad(
            samples,
            _peaking_coefficients(sample_rate, 1400.0, 0.9, tone.presence_db),
        )

    gain = 10.0 ** (tone.output_gain_db / 20.0)
    samples = [sample * gain for sample in samples]
    peak = max((abs(sample) for sample in samples), default=0.0)
    if peak > 32767.0:
        limiter = 32767.0 * 0.98 / peak
        samples = [sample * limiter for sample in samples]

    encoded = array(
        "h", (max(-32768, min(32767, round(sample))) for sample in samples)
    )
    return _encode_pcm16_mono(sample_rate, encoded)
