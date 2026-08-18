import test from "node:test";
import assert from "node:assert/strict";

import { prepareText } from "../../web/rhythm.js";
import worker, { validatePayload } from "../src/index.js";

test("自然節奏移除漢字之間的空格", () => {
  assert.equal(prepareText("食 飽 吂？", "characters", "natural"), "食飽吂？");
});

test("羅馬拼音保留詞間空格", () => {
  assert.equal(prepareText("siiid bauˋ mangˇ", "roma", "natural"), "siiid bauˋ mangˇ");
});

test("真人口語會替過長語句加入較密的語意分句", () => {
  const prepared = prepareText(
    "今晡日𠊎想愛摎你講一段溫暖个故事分你聽",
    "characters",
    "human",
  );
  assert.match(prepared, /，/);
});

test("大埔腔拒絕未提供的男聲", () => {
  assert.throws(
    () => validatePayload({ text: "食飽吂？", dialect: "dapu", gender: "male" }),
    /沒有這個聲音/,
  );
});

test("安全代理拒絕錯誤的頁面存取碼", async () => {
  const response = await worker.fetch(
    new Request("https://worker.example/api/status", {
      headers: { Origin: "https://owner.github.io", "X-App-Key": "wrong" },
    }),
    {
      HAKKA_TTS_BASE_URL: "https://api.example",
      HAKKA_TTS_USERNAME: "user",
      HAKKA_TTS_PASSWORD: "password",
      APP_ACCESS_KEY: "correct",
      ALLOWED_ORIGINS: "https://owner.github.io",
      ENVIRONMENT: "production",
    },
  );
  assert.equal(response.status, 401);
  assert.equal(response.headers.get("Access-Control-Allow-Origin"), "https://owner.github.io");
});

test("安全代理接受允許網站的預檢請求", async () => {
  const response = await worker.fetch(
    new Request("https://worker.example/api/synthesize", {
      method: "OPTIONS",
      headers: { Origin: "https://owner.github.io" },
    }),
    { ALLOWED_ORIGINS: "https://owner.github.io", ENVIRONMENT: "production" },
  );
  assert.equal(response.status, 204);
});
