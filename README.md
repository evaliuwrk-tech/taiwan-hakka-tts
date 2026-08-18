# 臺灣客語 TTS × Codex

這個專案將客家委員會「臺灣客語語音資料庫」的語音合成 API 包成：

- 可直接測試的 Python 命令列工具
- 可由 Codex 桌面版呼叫的本機 MCP 工具
- 可由 GitHub Pages 發布的客語朗讀網頁
- 可安全保管 API 帳密的 Cloudflare Worker 代理
- 產生 16 kHz、單聲道、S16LE PCM 的 WAV 音檔

## 支援內容

| 腔調 | 語者代碼 | 聲別 |
|---|---|---|
| 四縣腔 | `hak-xi-TW-vs2-M01` / `hak-xi-TW-vs2-F01` | 男 / 女 |
| 海陸腔 | `hak-hoi-TW-vs2-M01` / `hak-hoi-TW-vs2-F01` | 男 / 女 |
| 大埔腔 | `hak-thai-TW-vs2-F01` | 女 |

文字格式支援 `common`（中文）、`characters`（客語漢字）、`roma`（羅馬拼音）；語速範圍為 0.25–4.0。

## 私密設定

API 網址、帳號與密碼存放在根目錄 `.env`，且已由 `.gitignore` 排除。原始 API 文件則放在 `.private/`，不會加入 Git。請勿把這兩個位置的內容貼到 Issue、Commit 或公開訊息。

必要環境變數：

```text
HAKKA_TTS_BASE_URL=...
HAKKA_TTS_USERNAME=...
HAKKA_TTS_PASSWORD=...
```

## 命令列使用

以下範例使用 Codex 工作區內附的 Python；也可使用任何 Python 3.11 以上版本。

```powershell
python -m hakka_tts.cli status
python -m hakka_tts.cli catalog
python -m hakka_tts.cli synthesize "食飽吂？" --dialect sixian --gender female --text-type characters
python -m hakka_tts.cli synthesize "食飽吂？" --dialect sixian --gender female --tone warm
python -m hakka_tts.cli synthesize "食飽吂？今晡日愛去哪位尞？" --rhythm conversation
```

預設音檔會寫到 `output/audio/hakka-speech.wav`。

### 聲線預設

`--tone` 支援 `natural`（自然）、`deep`（低沉）、`young`（年輕）、`child`（兒童）、`warm`（溫暖）、`bright`（明亮）、`soft`（柔和）。也可以用 `--pitch-semitones -4` 到 `+4` 覆寫預設音高。聲線處理由標準 Python 完成，不需安裝 FFmpeg；程式會反向調整 API 語速，以補償音高處理造成的速度變化。

`child` 是由現有語者提高音高、減少低頻並增加清晰度所模擬的兒童聲線；原始 API 並未提供真正的兒童錄音語者，因此效果會保留所選男聲或女聲的部分音色特徵。

除 `natural` 保留 API 原聲外，其餘聲線使用強化音高、低／高頻、語音存在感與防爆音處理，以拉大不同預設之間的聽感差異。

### 朗讀節奏預設

`--rhythm` 支援：

| 選項 | 用途 | 短／長停頓 |
|---|---|---|
| `human` | 真人口語，短氣口與較密語意分句 | 70 / 240 ms |
| `natural` | 一般自然朗讀（預設） | 100 / 300 ms |
| `conversation` | 日常對話 | 85 / 260 ms |
| `narration` | 故事、導覽 | 140 / 420 ms |
| `news` | 公告、播報 | 105 / 340 ms |
| `original` | 不整理文字，使用 API 預設 | 未指定 |

自然節奏會移除客語漢字間不必要的空格、把換行轉成句尾停頓，並替過長且沒有標點的內容加入柔和斷句。羅馬拼音的詞間空格會保留。使用 `--short-pause-ms` 或 `--long-pause-ms` 可以覆寫預設。

## 在 Codex 使用

專案已建立 `.codex/config.toml`，註冊 `hakka_tts` 本機 STDIO MCP server。重新啟動 Codex 或重新載入 MCP 後，可用 `/mcp` 確認連線，接著直接說：

> 用四縣腔女聲念「食飽吂？」

也可以指定聲線，例如：

> 用四縣腔女聲、溫暖聲線念「食飽吂？」

工具包含：

- `hakka_tts_status`：驗證登入狀態
- `hakka_tts_catalog`：列出腔調、語者、文字格式與聲線預設
- `hakka_tts_synthesize`：套用指定聲線並回傳可播放的 WAV

## GitHub Pages 網頁

網頁位於 `web/`，提供：

- 四縣、海陸、大埔腔選擇
- 男、女聲（大埔腔依 API 限制只有女聲）
- 自然、對話、敘事、播報節奏
- 聲線、語速、長短停頓調整
- 實際斷句預覽、線上播放與 WAV 下載
- 手機與桌面版面

GitHub Pages 只能放公開的靜態網頁，因此**絕對不能**把 `.env` 或 API 帳密寫進 `web/`。本專案使用 `worker/` 內的 Cloudflare Worker 當安全代理；網頁只需填代理網址與自訂的頁面存取碼。

### 1. 發布安全代理

先將 `worker/wrangler.toml` 的 `ALLOWED_ORIGINS` 改成你的 GitHub Pages 網址，再執行：

```powershell
cd worker
npm install
npx wrangler login
npx wrangler secret put HAKKA_TTS_BASE_URL
npx wrangler secret put HAKKA_TTS_USERNAME
npx wrangler secret put HAKKA_TTS_PASSWORD
npx wrangler secret put APP_ACCESS_KEY
npm run deploy
```

`APP_ACCESS_KEY` 請自行設定一組夠長的隨機字串，避免公開頁面被他人濫用。所有值都會成為 Worker 的加密秘密，不會提交到 GitHub。

### 2. 發布 GitHub Pages

將專案推送到 GitHub 的 `main` 分支後，到儲存庫的 **Settings → Pages → Source** 選擇 **GitHub Actions**。專案內的 `.github/workflows/pages.yml` 會自動發布 `web/`。

第一次開啟網頁時，按右上角「服務設定」，填入 Worker 網址及 `APP_ACCESS_KEY`，連線成功後即可使用。Worker 網址也可預先填在 `web/config.js`；存取碼不可寫入該檔案。

### 本機預覽網頁

```powershell
python -m http.server 8000 --directory web
```

開啟 `http://localhost:8000`。若要連接本機 Worker，將 `worker/.dev.vars.example` 複製成 `worker/.dev.vars` 並填值，再從 `worker/` 執行 `npm run dev`。

## 測試

```powershell
python -m unittest discover -s tests -v
```

前端與 Worker 的節奏測試：

```powershell
node --test worker/test/*.test.js
```

登入文件所列的原始使用期限為 2025-12-04 至 2026-03-04；2026-08-17 實測仍可登入，伺服器核發的 Token 有效期為 30 天，表示帳號目前已展延或重新啟用。若日後 API 回傳 `42212`，代表帳號已過期，需向 API 提供單位申請展延或換發帳號；程式本身不需修改。
