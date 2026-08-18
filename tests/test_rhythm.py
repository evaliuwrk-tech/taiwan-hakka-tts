import unittest

from hakka_tts.client import HakkaTTSError
from hakka_tts.rhythm import prepare_speech, prepare_text, resolve_rhythm


class RhythmTests(unittest.TestCase):
    def test_natural_removes_spaces_between_han_characters(self) -> None:
        value = prepare_text("食 飽 吂？", "characters", resolve_rhythm("natural"))
        self.assertEqual(value, "食飽吂？")

    def test_romanization_keeps_word_spaces(self) -> None:
        value = prepare_text("siiid bauˋ mangˇ", "roma", resolve_rhythm("natural"))
        self.assertEqual(value, "siiid bauˋ mangˇ")

    def test_line_breaks_become_sentence_breaks(self) -> None:
        value = prepare_text("第一句\n第二句", "characters", resolve_rhythm("natural"))
        self.assertEqual(value, "第一句。第二句")

    def test_preset_pause_defaults_can_be_overridden(self) -> None:
        speech = prepare_speech(
            "食飽吂？",
            text_type="characters",
            rhythm="自然",
            short_pause_ms=75,
        )
        self.assertEqual(speech.short_pause_ms, 75)
        self.assertEqual(speech.long_pause_ms, 300)

    def test_human_rhythm_uses_shorter_breath_pauses(self) -> None:
        speech = prepare_speech(
            "今晡日𠊎想愛摎你講一段溫暖个故事分你聽",
            text_type="characters",
            rhythm="真人口語",
        )
        self.assertEqual(speech.rhythm.name, "human")
        self.assertEqual(speech.short_pause_ms, 70)
        self.assertEqual(speech.long_pause_ms, 240)
        self.assertIn("，", speech.text)

    def test_unknown_rhythm_is_rejected(self) -> None:
        with self.assertRaises(HakkaTTSError):
            resolve_rhythm("robot")


if __name__ == "__main__":
    unittest.main()
