import { prepareText, RHYTHM_PRESETS } from "./rhythm.js";

const TONES = {
  natural: { label: "自然原聲", pitch: 0, low: 0, high: 0, gain: 0 },
  deep: { label: "低沉", pitch: -2, low: 3, high: -1.5, gain: -1 },
  young: { label: "年輕", pitch: 1.5, low: -1, high: 2, gain: -1 },
  child: { label: "兒童", pitch: 3.5, low: -2, high: 2.5, gain: -1.5 },
  warm: { label: "溫暖", pitch: -0.5, low: 2, high: -1, gain: -0.5 },
  bright: { label: "明亮", pitch: 0, low: -0.5, high: 3, gain: -1.5 },
  soft: { label: "柔和", pitch: 0, low: 1, high: -2.5, gain: -0.5 },
};

const DIALECTS = { sixian: "四縣腔", hailu: "海陸腔", dapu: "大埔腔" };
const GENDERS = { female: "女聲", male: "男聲" };
const storage = window.localStorage;
const session = window.sessionStorage;
const defaultApiUrl = window.HAKKA_TTS_CONFIG?.apiUrl || "";

const elements = {
  form: document.querySelector("#tts-form"),
  text: document.querySelector("#speech-text"),
  count: document.querySelector("#character-count"),
  preview: document.querySelector("#prepared-preview"),
  dialect: document.querySelector("#dialect"),
  gender: document.querySelector("#gender"),
  tone: document.querySelector("#tone"),
  rate: document.querySelector("#rate"),
  rateOutput: document.querySelector("#rate-output"),
  shortPause: document.querySelector("#short-pause"),
  shortOutput: document.querySelector("#short-pause-output"),
  longPause: document.querySelector("#long-pause"),
  longOutput: document.querySelector("#long-pause-output"),
  submit: document.querySelector("#synthesize-button"),
  message: document.querySelector("#form-message"),
  result: document.querySelector("#result-panel"),
  resultDescription: document.querySelector("#result-description"),
  audio: document.querySelector("#audio-player"),
  download: document.querySelector("#download-audio"),
  dialog: document.querySelector("#settings-dialog"),
  settingsForm: document.querySelector("#settings-form"),
  apiUrl: document.querySelector("#api-url"),
  appKey: document.querySelector("#app-key"),
  remember: document.querySelector("#remember-settings"),
  settingsMessage: document.querySelector("#settings-message"),
  connectionDot: document.querySelector("#connection-dot"),
};

let currentAudioUrl = "";

function getTextType() {
  return document.querySelector('input[name="text-type"]:checked').value;
}

function getRhythm() {
  return document.querySelector('input[name="rhythm"]:checked').value;
}

function getSettings() {
  return {
    apiUrl: session.getItem("hakka_api_url") || storage.getItem("hakka_api_url") || defaultApiUrl,
    appKey: session.getItem("hakka_app_key") || storage.getItem("hakka_app_key") || "",
  };
}

function normalizeApiUrl(value) {
  return value.trim().replace(/\/$/, "");
}

function setConnectionState(state) {
  elements.connectionDot.dataset.state = state;
}

function setMessage(target, message, kind = "") {
  target.textContent = message;
  target.dataset.kind = kind;
}

function updatePreview() {
  const text = elements.text.value;
  elements.count.textContent = [...text].length;
  try {
    elements.preview.textContent = text
      ? prepareText(text, getTextType(), getRhythm())
      : "輸入文字後，這裡會顯示實際送去朗讀的斷句。";
  } catch (error) {
    elements.preview.textContent = error.message;
  }
}

function applyRhythmDefaults() {
  const preset = RHYTHM_PRESETS[getRhythm()];
  if (preset.shortPauseMs != null) elements.shortPause.value = preset.shortPauseMs;
  if (preset.longPauseMs != null) elements.longPause.value = preset.longPauseMs;
  updateRanges();
  updatePreview();
}

function updateRanges() {
  elements.rateOutput.textContent = `${Number(elements.rate.value).toFixed(2)}×`;
  elements.shortOutput.textContent = `${elements.shortPause.value} ms`;
  elements.longOutput.textContent = `${elements.longPause.value} ms`;
}

function updateVoiceOptions() {
  const male = elements.gender.querySelector('option[value="male"]');
  const isDapu = elements.dialect.value === "dapu";
  male.disabled = isDapu;
  if (isDapu && elements.gender.value === "male") elements.gender.value = "female";
}

async function testConnection(apiUrl, appKey) {
  const response = await fetch(`${apiUrl}/api/status`, { headers: { "X-App-Key": appKey } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "無法連上語音服務");
  return data;
}

function pitchRatio(semitones) {
  return 2 ** (semitones / 12);
}

function writeAscii(view, offset, value) {
  for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
}

function audioBufferToWav(audioBuffer) {
  const samples = audioBuffer.getChannelData(0);
  const output = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(output);
  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, audioBuffer.sampleRate, true);
  view.setUint32(28, audioBuffer.sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let index = 0; index < samples.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(44 + index * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
  }
  return new Blob([output], { type: "audio/wav" });
}

async function applyTone(arrayBuffer, tone) {
  if (tone.pitch === 0 && tone.low === 0 && tone.high === 0 && tone.gain === 0) {
    return new Blob([arrayBuffer], { type: "audio/wav" });
  }
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  const context = new AudioContextClass();
  const decoded = await context.decodeAudioData(arrayBuffer.slice(0));
  await context.close();

  const ratio = pitchRatio(tone.pitch);
  const frameCount = Math.max(1, Math.ceil(decoded.length / ratio));
  const offline = new OfflineAudioContext(1, frameCount, decoded.sampleRate);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.playbackRate.value = ratio;

  const low = offline.createBiquadFilter();
  low.type = "lowshelf";
  low.frequency.value = 250;
  low.gain.value = tone.low;
  const high = offline.createBiquadFilter();
  high.type = "highshelf";
  high.frequency.value = 3000;
  high.gain.value = tone.high;
  const gain = offline.createGain();
  gain.gain.value = 10 ** (tone.gain / 20);
  source.connect(low).connect(high).connect(gain).connect(offline.destination);
  source.start();
  return audioBufferToWav(await offline.startRendering());
}

async function handleSynthesis(event) {
  event.preventDefault();
  const settings = getSettings();
  if (!settings.apiUrl || !settings.appKey) {
    setMessage(elements.message, "請先完成右上角的服務設定。", "error");
    elements.dialog.showModal();
    return;
  }

  const text = elements.text.value.trim();
  if (!text) return;
  const rhythm = getRhythm();
  const tone = TONES[elements.tone.value];
  const requestedRate = Number(elements.rate.value);
  const apiRate = requestedRate / pitchRatio(tone.pitch);

  elements.submit.disabled = true;
  elements.submit.classList.add("loading");
  setMessage(elements.message, "正在整理語氣並產生聲音……");
  elements.result.hidden = true;

  try {
    const response = await fetch(`${settings.apiUrl}/api/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-App-Key": settings.appKey },
      body: JSON.stringify({
        text,
        textType: getTextType(),
        dialect: elements.dialect.value,
        gender: elements.gender.value,
        rhythm,
        speakingRate: apiRate,
        shortPauseMs: Number(elements.shortPause.value),
        longPauseMs: Number(elements.longPause.value),
      }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || "語音合成失敗，請稍後再試");
    }
    const audioBlob = await applyTone(await response.arrayBuffer(), tone);
    if (currentAudioUrl) URL.revokeObjectURL(currentAudioUrl);
    currentAudioUrl = URL.createObjectURL(audioBlob);
    elements.audio.src = currentAudioUrl;
    elements.download.href = currentAudioUrl;
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    elements.download.download = `hakka-${elements.dialect.value}-${stamp}.wav`;
    elements.resultDescription.textContent = `已套用${RHYTHM_PRESETS[rhythm].label}節奏、${DIALECTS[elements.dialect.value]}${GENDERS[elements.gender.value]}與${tone.label}聲線。`;
    elements.result.hidden = false;
    setMessage(elements.message, "聲音已經產生，可以播放或下載。", "success");
    elements.result.scrollIntoView({ behavior: "smooth", block: "center" });
    elements.audio.play().catch(() => {});
    setConnectionState("ok");
  } catch (error) {
    setMessage(elements.message, error.message || "語音合成失敗，請稍後再試。", "error");
    if (/存取碼|連上|Failed to fetch/i.test(error.message)) setConnectionState("error");
  } finally {
    elements.submit.disabled = false;
    elements.submit.classList.remove("loading");
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const apiUrl = normalizeApiUrl(elements.apiUrl.value);
  const appKey = elements.appKey.value;
  if (!apiUrl || !appKey) return;
  setMessage(elements.settingsMessage, "正在測試連線……");
  try {
    await testConnection(apiUrl, appKey);
    const target = elements.remember.checked ? storage : session;
    const other = elements.remember.checked ? session : storage;
    target.setItem("hakka_api_url", apiUrl);
    target.setItem("hakka_app_key", appKey);
    other.removeItem("hakka_api_url");
    other.removeItem("hakka_app_key");
    setConnectionState("ok");
    setMessage(elements.settingsMessage, "連線成功，設定已儲存。", "success");
    window.setTimeout(() => elements.dialog.close(), 600);
  } catch (error) {
    setConnectionState("error");
    setMessage(elements.settingsMessage, error.message || "連線測試失敗。", "error");
  }
}

document.querySelector("#open-settings").addEventListener("click", () => {
  const settings = getSettings();
  elements.apiUrl.value = settings.apiUrl;
  elements.appKey.value = settings.appKey;
  setMessage(elements.settingsMessage, "");
  elements.dialog.showModal();
});
document.querySelector("#close-settings").addEventListener("click", () => elements.dialog.close());
document.querySelector("#insert-example").addEventListener("click", () => {
  elements.text.value = "大家好，歡迎來到客語朗讀室。食飽吂？今晡日，𠊎想愛摎你講一段溫暖个故事。";
  updatePreview();
  elements.text.focus();
});
elements.text.addEventListener("input", updatePreview);
document.querySelectorAll('input[name="text-type"]').forEach((item) => item.addEventListener("change", updatePreview));
document.querySelectorAll('input[name="rhythm"]').forEach((item) => item.addEventListener("change", applyRhythmDefaults));
elements.dialect.addEventListener("change", updateVoiceOptions);
[elements.rate, elements.shortPause, elements.longPause].forEach((item) => item.addEventListener("input", updateRanges));
elements.form.addEventListener("submit", handleSynthesis);
elements.settingsForm.addEventListener("submit", saveSettings);
elements.dialog.addEventListener("click", (event) => {
  if (event.target === elements.dialog) elements.dialog.close();
});

updateVoiceOptions();
applyRhythmDefaults();
setConnectionState(getSettings().apiUrl && getSettings().appKey ? "ready" : "unset");
