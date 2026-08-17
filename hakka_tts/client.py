from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class Voice:
    dialect: str
    gender: str
    language_code: str
    name: str
    display_name: str


VOICES: tuple[Voice, ...] = (
    Voice("sixian", "male", "hak-xi-TW", "hak-xi-TW-vs2-M01", "四縣腔男聲"),
    Voice("sixian", "female", "hak-xi-TW", "hak-xi-TW-vs2-F01", "四縣腔女聲"),
    Voice("hailu", "male", "hak-hoi-TW", "hak-hoi-TW-vs2-M01", "海陸腔男聲"),
    Voice("hailu", "female", "hak-hoi-TW", "hak-hoi-TW-vs2-F01", "海陸腔女聲"),
    Voice("dapu", "female", "hak-thai-TW", "hak-thai-TW-vs2-F01", "大埔腔女聲"),
)

DIALECT_ALIASES = {
    "sixian": "sixian",
    "四縣": "sixian",
    "四縣腔": "sixian",
    "xi": "sixian",
    "hailu": "hailu",
    "hoi": "hailu",
    "海陸": "hailu",
    "海陸腔": "hailu",
    "dapu": "dapu",
    "thai": "dapu",
    "大埔": "dapu",
    "大埔腔": "dapu",
}

GENDER_ALIASES = {
    "female": "female",
    "f": "female",
    "女": "female",
    "女聲": "female",
    "male": "male",
    "m": "male",
    "男": "male",
    "男聲": "male",
}

TEXT_TYPE_ALIASES = {
    "common": "common",
    "中文": "common",
    "characters": "characters",
    "漢字": "characters",
    "客語漢字": "characters",
    "roma": "roma",
    "拼音": "roma",
    "羅馬拼音": "roma",
}


class HakkaTTSError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: int | str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code

    def __str__(self) -> str:
        prefix: list[str] = []
        if self.status is not None:
            prefix.append(f"HTTP {self.status}")
        if self.code is not None:
            prefix.append(f"API {self.code}")
        if prefix:
            return f"{' / '.join(prefix)}: {super().__str__()}"
        return super().__str__()


def load_env_file(path: str | Path) -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = Path(path)
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
            if raw_value.strip().startswith('"'):
                value = value.replace('\\"', '"').replace('\\\\', '\\')
        values[key] = value
    return values


class HakkaTTSClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        timeout: float = 60.0,
        opener: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen
        self.token: str | None = None
        self.expiration_seconds: int | None = None

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "HakkaTTSClient":
        file_values = load_env_file(env_file) if env_file else {}
        values: Mapping[str, str] = {**file_values, **os.environ}
        required = ("HAKKA_TTS_BASE_URL", "HAKKA_TTS_USERNAME", "HAKKA_TTS_PASSWORD")
        missing = [key for key in required if not values.get(key)]
        if missing:
            raise HakkaTTSError(f"缺少設定：{', '.join(missing)}")
        timeout = float(values.get("HAKKA_TTS_TIMEOUT", "60"))
        return cls(
            values["HAKKA_TTS_BASE_URL"],
            values["HAKKA_TTS_USERNAME"],
            values["HAKKA_TTS_PASSWORD"],
            timeout=timeout,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        authorized: bool = False,
        accept: str = "application/json",
    ) -> tuple[int, Mapping[str, str], bytes]:
        data = None
        headers = {"Accept": accept}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if authorized:
            if not self.token:
                self.login()
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                return response.status, dict(response.headers.items()), response.read()
        except urllib.error.HTTPError as error:
            body = error.read()
            self._raise_api_error(body, status=error.code)
            raise AssertionError("unreachable")
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", error)
            raise HakkaTTSError(f"無法連線至客語 TTS API：{reason}") from error
        except TimeoutError as error:
            raise HakkaTTSError("客語 TTS API 連線逾時") from error

    @staticmethod
    def _decode_json(body: bytes, *, status: int | None = None) -> dict[str, Any]:
        try:
            result = json.loads(body.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HakkaTTSError("API 回傳的 JSON 格式無法解析", status=status) from error
        if not isinstance(result, dict):
            raise HakkaTTSError("API 回傳的 JSON 不是物件", status=status)
        return result

    @classmethod
    def _raise_api_error(cls, body: bytes, *, status: int | None = None) -> None:
        try:
            result = cls._decode_json(body, status=status)
        except HakkaTTSError:
            raise HakkaTTSError("API 請求失敗", status=status)
        code = result.get("code")
        message = str(result.get("error") or result.get("message") or "API 請求失敗")
        raise HakkaTTSError(message, status=status, code=code)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        authorized: bool = False,
        accepted_codes: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        status, _, body = self._request(
            method, path, payload=payload, authorized=authorized
        )
        result = self._decode_json(body, status=status)
        code = result.get("code")
        if code is not None and code not in accepted_codes:
            message = str(result.get("error") or result.get("message") or "API 請求失敗")
            raise HakkaTTSError(message, status=status, code=code)
        return result

    def login(self, *, remember_me: bool = True) -> str:
        result = self._request_json(
            "POST",
            "/api/v1/tts/login",
            payload={
                "username": self.username,
                "password": self.password,
                "rememberMe": 1 if remember_me else 0,
            },
        )
        token = result.get("token")
        if not isinstance(token, str) or not token:
            raise HakkaTTSError("登入成功回應中沒有 Token")
        self.token = token
        expiration = result.get("expiration")
        self.expiration_seconds = int(expiration) if expiration is not None else None
        return token

    def logout(self) -> dict[str, Any]:
        result = self._request_json("POST", "/api/v1/tts/logout", authorized=True)
        self.token = None
        self.expiration_seconds = None
        return result

    def list_models(self, name: str | None = None) -> list[dict[str, Any]]:
        path = "/api/v1/tts/models"
        if name:
            from urllib.parse import urlencode

            path += "?" + urlencode({"name": name})
        result = self._request_json(
            "GET", path, authorized=True, accepted_codes=(200, 202)
        )
        data = result.get("data", [])
        if not isinstance(data, list):
            raise HakkaTTSError("模型清單格式不正確")
        return [item for item in data if isinstance(item, dict)]

    def text_type_options(self) -> list[dict[str, Any]]:
        result = self._request_json(
            "GET", "/api/v1/tts/synthesize/text-type-options", authorized=True
        )
        data = result.get("data", [])
        if not isinstance(data, list):
            raise HakkaTTSError("文字格式清單格式不正確")
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def resolve_voice(dialect: str = "sixian", gender: str = "female") -> Voice:
        normalized_dialect = DIALECT_ALIASES.get(dialect.strip().lower())
        normalized_gender = GENDER_ALIASES.get(gender.strip().lower())
        if not normalized_dialect:
            raise HakkaTTSError(f"不支援的腔調：{dialect}")
        if not normalized_gender:
            raise HakkaTTSError(f"不支援的聲別：{gender}")
        for voice in VOICES:
            if voice.dialect == normalized_dialect and voice.gender == normalized_gender:
                return voice
        raise HakkaTTSError(f"API 沒有提供 {dialect} {gender} 的語者")

    @staticmethod
    def normalize_text_type(text_type: str) -> str:
        normalized = TEXT_TYPE_ALIASES.get(text_type.strip().lower())
        if not normalized:
            raise HakkaTTSError(f"不支援的文字格式：{text_type}")
        return normalized

    @staticmethod
    def pick_model(models: list[dict[str, Any]], requested: str | None = None) -> str:
        if requested:
            for model in models:
                if model.get("name") == requested:
                    return requested
            raise HakkaTTSError(f"找不到模型：{requested}")
        for model in models:
            if model.get("isDefault") is True and isinstance(model.get("name"), str):
                return model["name"]
        for model in models:
            if isinstance(model.get("name"), str) and model["name"]:
                return model["name"]
        raise HakkaTTSError("API 未提供可用的語音模型")

    def synthesize(
        self,
        text: str,
        *,
        dialect: str = "sixian",
        gender: str = "female",
        text_type: str = "common",
        speaking_rate: float = 1.0,
        model: str | None = None,
        short_pause_ms: int | None = None,
        long_pause_ms: int | None = None,
    ) -> bytes:
        if not text.strip():
            raise HakkaTTSError("合成文字不可為空白")
        if not 0.25 <= speaking_rate <= 4.0:
            raise HakkaTTSError("語速必須介於 0.25 與 4.0 之間")
        voice = self.resolve_voice(dialect, gender)
        resolved_text_type = self.normalize_text_type(text_type)
        selected_model = self.pick_model(self.list_models(), model)

        output_config: dict[str, Any] = {"streamMode": 0}
        if short_pause_ms is not None:
            output_config["shortPauseDuration"] = int(short_pause_ms)
        if long_pause_ms is not None:
            output_config["longPauseDuration"] = int(long_pause_ms)
        payload = {
            "input": {"text": text, "textType": resolved_text_type},
            "voice": {
                "model": selected_model,
                "languageCode": voice.language_code,
                "name": voice.name,
            },
            "audioConfig": {"speakingRate": float(speaking_rate)},
            "outputConfig": output_config,
        }
        status, headers, body = self._request(
            "POST",
            "/api/v1/tts/synthesize",
            payload=payload,
            authorized=True,
            accept="audio/wav, application/json",
        )
        content_type = next(
            (value for key, value in headers.items() if key.lower() == "content-type"), ""
        ).lower()
        if "json" in content_type or body.lstrip().startswith(b"{"):
            self._raise_api_error(body, status=status)
        if len(body) < 12 or not body.startswith(b"RIFF") or body[8:12] != b"WAVE":
            raise HakkaTTSError("API 回傳內容不是有效的 WAV 音檔", status=status)
        return body


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", value).strip("-._")
    return cleaned or "hakka-speech"
