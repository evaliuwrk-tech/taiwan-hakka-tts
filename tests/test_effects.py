from __future__ import annotations

import io
import math
import unittest
import wave
from array import array
from dataclasses import replace

from hakka_tts.client import HakkaTTSError
from hakka_tts.effects import (
    TONE_PRESETS,
    compensated_speaking_rate,
    process_wav,
    resolve_tone,
)


def sine_wav(*, frequency: float = 220.0, seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    samples = array(
        "h",
        (
            round(12000 * math.sin(2 * math.pi * frequency * index / sample_rate))
            for index in range(round(seconds * sample_rate))
        ),
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(samples.tobytes())
    return output.getvalue()


def wav_info(data: bytes) -> tuple[int, int, int, int]:
    with wave.open(io.BytesIO(data), "rb") as reader:
        return (
            reader.getnchannels(),
            reader.getsampwidth(),
            reader.getframerate(),
            reader.getnframes(),
        )


class EffectsTests(unittest.TestCase):
    def test_natural_preset_preserves_original_bytes(self):
        original = sine_wav()
        self.assertEqual(process_wav(original, TONE_PRESETS["natural"]), original)

    def test_pitch_shift_changes_frame_count_but_preserves_wav_format(self):
        original = sine_wav()
        octave_up = replace(TONE_PRESETS["natural"], pitch_semitones=12.0)
        processed = process_wav(original, octave_up)
        channels, width, rate, frames = wav_info(processed)
        self.assertEqual((channels, width, rate), (1, 2, 16000))
        self.assertAlmostEqual(frames, 8000, delta=1)

    def test_rate_compensation_offsets_pitch_resampling(self):
        octave_up = replace(TONE_PRESETS["natural"], pitch_semitones=12.0)
        self.assertAlmostEqual(compensated_speaking_rate(1.0, octave_up), 0.5)

    def test_all_presets_produce_valid_pcm_wav(self):
        original = sine_wav()
        for preset in TONE_PRESETS.values():
            with self.subTest(preset=preset.name):
                channels, width, rate, frames = wav_info(process_wav(original, preset))
                self.assertEqual((channels, width, rate), (1, 2, 16000))
                self.assertGreater(frames, 0)

    def test_alias_and_custom_pitch_validation(self):
        self.assertEqual(resolve_tone("溫暖").name, "warm")
        self.assertEqual(resolve_tone("兒童").name, "child")
        self.assertEqual(resolve_tone("child").pitch_semitones, 5.0)
        self.assertEqual(resolve_tone("deep", -3.0).pitch_semitones, -3.0)
        with self.assertRaises(HakkaTTSError):
            resolve_tone("deep", -5.0)


if __name__ == "__main__":
    unittest.main()
