from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from hakka_tts.client import HakkaTTSClient, HakkaTTSError, load_env_file


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200, content_type: str = "application/json"):
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self) -> bytes:
        return self._body


class SequenceOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ClientTests(unittest.TestCase):
    def test_load_env_file_handles_quoted_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('A="hello"\nB=world\n', encoding="utf-8")
            self.assertEqual(load_env_file(path), {"A": "hello", "B": "world"})

    def test_resolve_voice(self):
        voice = HakkaTTSClient.resolve_voice("四縣", "女聲")
        self.assertEqual(voice.language_code, "hak-xi-TW")
        self.assertEqual(voice.name, "hak-xi-TW-vs2-F01")
        with self.assertRaises(HakkaTTSError):
            HakkaTTSClient.resolve_voice("大埔", "男聲")

    def test_synthesize_builds_expected_payload_and_validates_wav(self):
        opener = SequenceOpener(
            [
                FakeResponse(json.dumps({"code": 200, "token": "token", "expiration": 60}).encode()),
                FakeResponse(
                    json.dumps(
                        {"code": 200, "data": [{"name": "melotts", "isDefault": True}]}
                    ).encode()
                ),
                FakeResponse(b"RIFF\x00\x00\x00\x00WAVEdata", content_type="audio/wav"),
            ]
        )
        client = HakkaTTSClient("https://example.test", "user", "pass", opener=opener)
        wav = client.synthesize("食飽吂？", dialect="hailu", gender="male", text_type="characters")
        self.assertTrue(wav.startswith(b"RIFF"))
        request = opener.requests[-1][0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["voice"]["model"], "melotts")
        self.assertEqual(payload["voice"]["languageCode"], "hak-hoi-TW")
        self.assertEqual(payload["voice"]["name"], "hak-hoi-TW-vs2-M01")
        self.assertEqual(payload["input"]["textType"], "characters")

    def test_http_json_error_is_safely_reported(self):
        body = json.dumps({"code": 42212, "error": "account expired"}).encode()
        error = urllib.error.HTTPError(
            "https://example.test/api/v1/tts/login", 422, "Unprocessable", {}, io.BytesIO(body)
        )
        client = HakkaTTSClient(
            "https://example.test", "user", "pass", opener=SequenceOpener([error])
        )
        with self.assertRaises(HakkaTTSError) as context:
            client.login()
        self.assertEqual(context.exception.code, 42212)
        self.assertNotIn("pass", str(context.exception))

    def test_model_list_accepts_empty_202_response(self):
        opener = SequenceOpener(
            [
                FakeResponse(json.dumps({"code": 200, "token": "token", "expiration": 60}).encode()),
                FakeResponse(json.dumps({"code": 202, "data": []}).encode()),
            ]
        )
        client = HakkaTTSClient("https://example.test", "user", "pass", opener=opener)
        self.assertEqual(client.list_models(), [])


if __name__ == "__main__":
    unittest.main()
