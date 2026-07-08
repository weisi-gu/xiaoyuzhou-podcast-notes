---
name: xiaoyuzhou-podcast-notes
description: 把小宇宙（Xiaoyuzhou FM）单集播客转成结构化的 Markdown 笔记。工作流为：解析小宇宙单集链接 → 拿到音频直链、shownotes、章节（有官方转录则直接用）→ 转录音频 → 判断内容类型（财经/科技商业/人物访谈/知识科普/通用）→ 套用对应的笔记模板 → 输出 .md 笔记文件。只要用户给出小宇宙链接（xiaoyuzhoufm.com/episode/...）、或提到"把这期播客整理成笔记""转录小宇宙""生成播客笔记""播客总结/逐字稿/shownotes 整理"，就使用本技能；即便用户没说"skill"二字也应触发。也支持用户已自备音频文件或转录文本，只需生成笔记的场景。
---

# 小宇宙播客笔记生成器

把一条小宇宙单集链接，变成一份类型匹配、可直接归档的 Markdown 笔记。

## 何时用本技能

- 用户给出小宇宙单集链接（`https://www.xiaoyuzhoufm.com/episode/<id>`），想要笔记/总结/逐字稿；
- 用户已有音频文件或转录文本，想按类型整理成结构化笔记；
- 用户想批量整理某档播客的多期内容。

## 总体流程（五步）

1. **取数据** —— 用 `scripts/fetch_episode.py` 解析链接，拿到标题、播客名、发布日期、时长、音频直链、shownotes（含图文与图表）、章节；若页面自带官方转录，一并取出。
2. **得转录** —— 若第 1 步已有官方转录，直接用；否则下载音频并用 `scripts/transcribe.py` 转录。
3. **判类型** —— 根据播客名 + shownotes + 转录开头，判断内容类型，选定模板（见下）。类型不明确时问用户一次。
4. **写笔记** —— 读取对应模板文件，用转录 + shownotes 逐块填充。**不要**照抄模板里的说明文字，要输出填好的真实内容。
5. **存文件** —— 保存为 `<播客名>-<集标题>-笔记.md`，用 `present_files`（若可用）交给用户。

---

## 第 1 步：取数据

```bash
python scripts/fetch_episode.py "<小宇宙链接或episode_id>" --out ./_work
```

脚本会在 `./_work/` 下生成：
- `meta.json` —— 结构化元数据（`title` / `podcast_title` / `pub_date` / `duration_sec` / `audio_url` / `eid` / `has_official_transcript`）
- `shownotes.md` —— shownotes 正文（已转 Markdown，保留图片链接和图表说明）
- `chapters.json` —— 章节时间戳（若有）
- `official_transcript.txt` —— 官方转录（若页面自带）

加 `--download` 会把音频存到 `./_work/audio.m4a`：

```bash
python scripts/fetch_episode.py "<链接>" --out ./_work --download
```

> 说明：本脚本只处理**公开单集**。付费或需登录的内容拿不到直链，此时提示用户改用官方 App 导出音频，再走"已自备音频"路径。

## 第 2 步：得转录（分层兜底，务必拿到真逐字稿）

**核心原则：笔记必须基于真转录稿，不能只靠 shownotes 推断。** 按下面优先级逐级尝试，前一级成功就停：

**① 官方转录**：若 `meta.json` 里 `has_official_transcript` 为真，直接用 `official_transcript.txt`。最准、零成本，跳过 ASR。

**② 云端 Qwen（长音频首选，若配了 `DASHSCOPE_API_KEY`）**：小宇宙音频直链是公网 URL，可不下载、直接转。异步长音频，支持最长 12 小时，一期约 2-5 分钟出稿：

```bash
python scripts/transcribe.py --from-meta ./_work --out ./_work --backend qwen --language zh   # 新加坡账号加 --region intl
```

> `--from-meta ./_work` 让脚本自己去读 meta.json 里的 audio_url，无需手动传链接（bash 和 PowerShell 都一样，避免引号/续行问题）。

**②b 对谈型播客（多人）建议改用 fun-asr 开说话人分离**：能给每句标 `【说话人N】`，主播/嘉宾观点不混淆，配合 finance.md 的"对谈型"分支和 interview 模板更好。开分离时音频建议 ≤2 小时、仅单声道：

```bash
python scripts/transcribe.py --from-meta ./_work --out ./_work --backend funasr --diarize --speaker-count 2 --language zh
# 想让嘉宾名/术语更准，可在百炼控制台建热词表后加 --vocabulary-id vocab-xxx
```

**③（可选）其它 OpenAI 兼容 ASR**：`--backend api`（配 `ASR_API_BASE`/`ASR_API_KEY`），需先 `--download` 下载音频为本地文件。一般用不到。

**决策建议**：有官方转录用①；否则默认走②（qwen 单人 / funasr 对谈），需配 `DASHSCOPE_API_KEY`（百炼，新账号有免费额度、单期成本几分钱）。

产物：`./_work/transcript.txt`（纯文本）与 `./_work/transcript.srt`（带时间戳）。

> ⚠️ 若都失败（付费内容/无 Key），**不要**用 shownotes 硬凑成"逐字稿笔记"。应如实告知用户没拿到转录，并让其在 front-matter 标注"整理依据：仅 shownotes（未转录）"。

## 第 3 步：判断内容类型并选模板

看 `podcast_title` + `shownotes.md` + 转录前 ~500 字，选一个最贴切的类型：

| 类型 | 触发信号 | 模板文件 |
|---|---|---|
| **财经/投资** | 谈宏观、股市、利率、基金、ETF、财报、投资策略 | `templates/finance.md`（内含子分支：**行情/研报型** 与 **理念/对谈型**，进模板后先按其顶部⓪判定再填） |
| **科技/商业/创投** | 产品、创业、AI、行业分析、公司战略、融资 | `templates/tech-business.md` |
| **人物/访谈/对谈** | 以嘉宾经历、观点、故事为主，弱结论强叙事 | `templates/interview.md` |
| **知识/科普/文史** | 讲解某学科、历史、概念、方法论 | `templates/knowledge.md` |
| **通用/其它** | 以上都不贴切 | `templates/general.md` |

类型明显就直接用；**若在两类之间拿不准，用一句话问用户确认一次**，别硬猜。用户也可以指定"就用财经模板"。

## 第 4 步：写笔记

> 写笔记不绑定 Claude：由当前 agent 直接按模板写即可；也可让用户用 `scripts/make_notes.py` 配任意 OpenAI 兼容 LLM（DeepSeek/通义/Kimi/GLM/GPT 等）离线生成。以下是 agent 直接写的要点。

1. `view` 选定的模板文件，按它的结构和逐块说明填写。
2. 每一块都要**输出填好的真实内容**，不能用"详见原文""同上"占位，也不要把模板里的方括号说明原样留在成品里。
3. 所有笔记统一在文件开头加 YAML front-matter：

```yaml
---
播客: <podcast_title>
单集: <title>
发布日期: <pub_date>
时长: <duration 分钟>
链接: <小宇宙链接>
类型: <财经/科技商业/人物访谈/知识科普/通用>
整理日期: <今天>
---
```

4. **财经类的两条硬性要求**（见 `templates/finance.md`，务必执行）：
   - **金融代码必须联网核实**：笔记中出现的每一支股票/基金/ETF，都要通过网络搜索确认最新代码及交易所，格式 `名称（代码·交易所）`，例：沪深300ETF（510300·上交所）。核实不了就注明"代码待核实"，不许瞎编。
   - **图表必须逐一解读**：shownotes / 图文页里的每张图表（K线、趋势图、数据表、结构图）都要分析：①图表类型与核心变量；②关键趋势/拐点/异常值；③与本集论点的关联；④数据来源与时间范围。

5. 忠实于音频，**不要脑补**主讲人没说的判断或数据。模板里要求"若未涉及则如实标注"的地方，就照实写"本集未涉及"。

## 第 5 步：输出

保存为 `<播客名>-<集标题>-笔记.md`（文件名去掉非法字符）。若有 `present_files` 工具就用它把 md 交给用户；否则告诉用户文件路径。

---

## 已自备音频 / 转录文本的情况

- 用户直接给音频文件：跳过第 1 步，从第 2 步转录开始；元数据向用户补问（节目名、集标题、链接）。
- 用户直接给转录文本或逐字稿：跳过第 1–2 步，从第 3 步选模板开始。

## 批量整理

用户给多条链接时，对每条依次跑完整流程，每期一个 md 文件，最后可另生成一个 `索引.md` 汇总各期标题、类型、一句话主旨和文件名。
