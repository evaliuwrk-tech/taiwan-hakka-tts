import { prepareText, RHYTHM_PRESETS } from "../../web/rhythm.js";

const VOICES = {
  "sixian:female": { languageCode: "hak-xi-TW", name: "hak-xi-TW-vs2-F01" },
  "sixian:male": { languageCode: "hak-xi-TW", name: "hak-xi-TW-vs2-M01" },
  "hailu:female": { languageCode: "hak-hoi-TW", name: "hak-hoi-TW-vs2-F01" },
  "hailu:male": { languageCode: "hak-hoi-TW", name: "hak-hoi-TW-vs2-M01" },
  "dapu:female": { languageCode: "hak-thai-TW", name: "hak-thai-TW-vs2-F01" },
};

let tokenCache = null;
let modelCache = null;

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...headers },
  });
}

function allowedOrigin(request, env) {
  const origin = request.headers.get("Origin") || "";
  const allowed = String(env.ALLOWED_ORIGINS || "")
    .split(",")
    .map((value) => value.trim().replace(/\/$/, ""))
    .filter(Boolean);
  if (allowed.includes(origin.replace(/\/$/, ""))) return origin;
  if (env.ENVIRONMENT !== "production" && /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) {
    return origin;
  }
  return "";
}

function corsHeaders(origin) {
  return origin
    ? {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "Content-Type, X-App-Key",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Expose-Headers": "Content-Disposition",
        Vary: "Origin",
      }
    : {};
}

function requireEnvironment(env) {
  for (const key of ["HAKKA_TTS_BASE_URL", "HAKKA_TTS_USERNAME", "HAKKA_TTS_PASSWORD", "APP_ACCESS_KEY"]) {
    if (!env[key]) throw new Error(`後端尚未設定 ${key}`);
  }
}

async function apiJson(env, path, init = {}) {
  const response = await fetch(`${String(env.HAKKA_TTS_BASE_URL).replace(/\/$/, "")}${path}`, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok || (body.code != null && ![200, 202].includes(body.code))) {
    const error = new Error(body.error || body.message || "客語語音服務暫時無法回應");
    error.status = response.status;
    error.code = body.code;
    throw error;
  }
  return body;
}

async function login(env, force = false) {
  const now = Date.now();
  if (!force && tokenCache?.token && tokenCache.expiresAt > now + 60_000) return tokenCache.token;
  const body = await apiJson(env, "/api/v1/tts/login", {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify({
      username: env.HAKKA_TTS_USERNAME,
      password: env.HAKKA_TTS_PASSWORD,
      rememberMe: 1,
    }),
  });
  if (!body.token) throw new Error("客語語音服務登入回應不完整");
  tokenCache = {
    token: body.token,
    expiresAt: now + Math.max(60, Number(body.expiration || 3600)) * 1000,
  };
  return tokenCache.token;
}

async function authorizedFetch(env, path, init = {}, retry = true) {
  const token = await login(env);
  const response = await fetch(`${String(env.HAKKA_TTS_BASE_URL).replace(/\/$/, "")}${path}`, {
    ...init,
    headers: { ...(init.headers || {}), Authorization: `Bearer ${token}` },
  });
  if (response.status === 401 && retry) {
    tokenCache = null;
    await login(env, true);
    return authorizedFetch(env, path, init, false);
  }
  return response;
}

async function selectedModel(env) {
  if (modelCache?.name && modelCache.expiresAt > Date.now()) return modelCache.name;
  const response = await authorizedFetch(env, "/api/v1/tts/models", {
    headers: { Accept: "application/json" },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || (body.code != null && ![200, 202].includes(body.code))) {
    throw new Error(body.error || body.message || "無法取得語音模型");
  }
  const models = Array.isArray(body.data) ? body.data : [];
  const model = models.find((item) => item?.isDefault && item?.name) || models.find((item) => item?.name);
  if (!model) throw new Error("語音服務目前沒有可用模型");
  modelCache = { name: model.name, expiresAt: Date.now() + 60 * 60 * 1000 };
  return model.name;
}

function validatePayload(body) {
  const text = String(body.text || "").trim();
  const textType = ["common", "characters", "roma"].includes(body.textType) ? body.textType : "characters";
  const rhythm = RHYTHM_PRESETS[body.rhythm] ? body.rhythm : "natural";
  if (!text) throw new Error("請輸入要朗讀的文字");
  if ([...text].length > 500) throw new Error("每次最多可朗讀 500 個字元");

  const dialect = ["sixian", "hailu", "dapu"].includes(body.dialect) ? body.dialect : "sixian";
  const gender = ["female", "male"].includes(body.gender) ? body.gender : "female";
  const voice = VOICES[`${dialect}:${gender}`];
  if (!voice) throw new Error("所選腔調沒有這個聲音");

  const speakingRate = Number(body.speakingRate ?? 1);
  if (!Number.isFinite(speakingRate) || speakingRate < 0.25 || speakingRate > 4) {
    throw new Error("語速設定超出可用範圍");
  }
  const preset = RHYTHM_PRESETS[rhythm];
  const shortPause = body.shortPauseMs == null ? preset.shortPauseMs : Number(body.shortPauseMs);
  const longPause = body.longPauseMs == null ? preset.longPauseMs : Number(body.longPauseMs);
  for (const value of [shortPause, longPause]) {
    if (value != null && (!Number.isInteger(value) || value < 0 || value > 3000)) {
      throw new Error("停頓時間必須介於 0 到 3000 毫秒");
    }
  }
  return {
    text: prepareText(text, textType, rhythm),
    textType,
    voice,
    speakingRate,
    shortPause,
    longPause,
  };
}

async function synthesize(request, env, headers) {
  const body = await request.json().catch(() => {
    throw new Error("請求內容格式不正確");
  });
  const input = validatePayload(body);
  const model = await selectedModel(env);
  const outputConfig = { streamMode: 0 };
  if (input.shortPause != null) outputConfig.shortPauseDuration = input.shortPause;
  if (input.longPause != null) outputConfig.longPauseDuration = input.longPause;

  const response = await authorizedFetch(env, "/api/v1/tts/synthesize", {
    method: "POST",
    headers: {
      Accept: "audio/wav, application/json",
      "Content-Type": "application/json; charset=utf-8",
    },
    body: JSON.stringify({
      input: { text: input.text, textType: input.textType },
      voice: { model, ...input.voice },
      audioConfig: { speakingRate: input.speakingRate },
      outputConfig,
    }),
  });
  const contentType = response.headers.get("Content-Type") || "";
  if (!response.ok || contentType.includes("json")) {
    const errorBody = await response.json().catch(() => ({}));
    const error = new Error(errorBody.error || errorBody.message || "語音合成失敗");
    error.status = response.status;
    error.code = errorBody.code;
    throw error;
  }
  return new Response(response.body, {
    status: 200,
    headers: {
      ...headers,
      "Content-Type": "audio/wav",
      "Content-Disposition": 'attachment; filename="hakka-speech.wav"',
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export default {
  async fetch(request, env) {
    const origin = allowedOrigin(request, env);
    const headers = corsHeaders(origin);
    if (request.method === "OPTIONS") {
      return origin ? new Response(null, { status: 204, headers }) : json({ error: "不允許的網站來源" }, 403);
    }

    try {
      requireEnvironment(env);
      if (request.headers.get("Origin") && !origin) return json({ error: "不允許的網站來源" }, 403);
      if (request.headers.get("X-App-Key") !== env.APP_ACCESS_KEY) {
        return json({ error: "存取碼不正確" }, 401, headers);
      }

      const url = new URL(request.url);
      if (url.pathname === "/api/status" && request.method === "GET") {
        await login(env);
        return json({ status: "ok" }, 200, headers);
      }
      if (url.pathname === "/api/synthesize" && request.method === "POST") {
        return await synthesize(request, env, headers);
      }
      return json({ error: "找不到此服務" }, 404, headers);
    } catch (error) {
      const status = Number(error.status) >= 400 && Number(error.status) < 600 ? Number(error.status) : 500;
      return json(
        { error: error.message || "服務暫時無法使用", code: error.code ?? null },
        status,
        headers,
      );
    }
  },
};

export { validatePayload };
