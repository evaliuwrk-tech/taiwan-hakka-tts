export const RHYTHM_PRESETS = {
  original: {
    label: "原始",
    description: "保留原文與系統預設停頓",
    shortPauseMs: null,
    longPauseMs: null,
    maxClauseChars: null,
  },
  natural: {
    label: "自然",
    description: "語意斷句柔和，適合一般朗讀",
    shortPauseMs: 100,
    longPauseMs: 300,
    maxClauseChars: 20,
  },
  conversation: {
    label: "對話",
    description: "停頓俐落，接近日常說話",
    shortPauseMs: 85,
    longPauseMs: 260,
    maxClauseChars: 18,
  },
  narration: {
    label: "敘事",
    description: "句尾較從容，適合故事與導覽",
    shortPauseMs: 140,
    longPauseMs: 420,
    maxClauseChars: 24,
  },
  news: {
    label: "播報",
    description: "節奏穩定清楚，適合公告內容",
    shortPauseMs: 105,
    longPauseMs: 340,
    maxClauseChars: 22,
  },
};

const punctuation = "，。！？；：、,.!?;:";
const connectors = ["所以", "因為", "毋過", "但是", "然後", "另外", "假使", "若係", "還有"];
const softBoundaries = new Set("个兜咧啊哦呢嗎吂也就係會愛毋有在到過來去做講看聽時前後");
const han = "\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff";

function normalizeSpacing(text, textType) {
  const lines = text
    .replace(/\r\n?/g, "\n")
    .trim()
    .split("\n")
    .map((line) => line.replace(/[ \t]+/g, " ").trim())
    .filter(Boolean)
    .map((line) => line.replace(/。+$/g, ""));
  let value = lines.join("。").replace(/。{2,}/g, "。");
  if (textType !== "roma") {
    value = value.replace(new RegExp(`(?<=[${han}])\\s+(?=[${han}])`, "gu"), "");
  }
  return value;
}

function addConnectorPauses(clause) {
  let result = clause;
  for (const connector of connectors) {
    let start = 0;
    while (start < result.length) {
      const index = result.indexOf(connector, start);
      if (index < 4) break;
      if (!punctuation.includes(result[index - 1])) {
        result = `${result.slice(0, index)}，${result.slice(index)}`;
        start = index + connector.length + 1;
      } else {
        start = index + connector.length;
      }
    }
  }
  return result;
}

function splitLongClause(clause, maximum) {
  if (clause.length <= maximum || [...clause].some((char) => punctuation.includes(char))) {
    return clause;
  }
  const chunks = [];
  let remainder = clause;
  while (remainder.length > maximum) {
    const lower = Math.max(1, Math.floor(maximum * 0.6));
    let breakAt = maximum;
    for (let index = maximum - 1; index >= lower; index -= 1) {
      if (softBoundaries.has(remainder[index])) {
        breakAt = index + 1;
        break;
      }
    }
    chunks.push(remainder.slice(0, breakAt));
    remainder = remainder.slice(breakAt);
  }
  chunks.push(remainder);
  return chunks.filter(Boolean).join("，");
}

export function prepareText(text, textType = "characters", rhythm = "natural") {
  const preset = RHYTHM_PRESETS[rhythm];
  if (!preset) throw new Error("不支援的朗讀節奏");
  if (rhythm === "original") return text.trim();

  const value = normalizeSpacing(text, textType);
  if (textType === "roma" || !preset.maxClauseChars) return value;

  const parts = value.split(/([。！？!?；;])/u);
  return parts
    .map((part) => {
      if (!part || "。！？!?；;".includes(part)) return part;
      return addConnectorPauses(part)
        .split("，")
        .map((clause) => splitLongClause(clause, preset.maxClauseChars))
        .join("，");
    })
    .join("");
}
