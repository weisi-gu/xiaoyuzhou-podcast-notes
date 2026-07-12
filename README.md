# xiaoyuzhou-podcast-notes

> 小宇宙播客笔记生成器 · Turn a Xiaoyuzhou (Chinese podcast) episode into structured Markdown notes — a Claude skill using Qwen / Fun-ASR for transcription.

把小宇宙单集播客转成结构化 Markdown 笔记的 Skill（适配 Claude Code / Codex / OpenClaw 等能读 SKILL.md + 跑 Python 的环境）。

📁 想先看效果，直接翻 [`examples/`](./examples) 里两期真实成品笔记。

## 安装
把整个 `xiaoyuzhou-podcast-notes/` 文件夹放进你的 skills 目录（如 Claude Code 的 `~/.claude/skills/`）。

## 转录后端（阿里云百炼云端，同一个 API Key）

三个云端后端共用一个 `DASHSCOPE_API_KEY`，脚本里已写死模型名：

| `--backend` | 模型 | 单价 | 免费额度 | 说话人分离 | 适合 |
|---|---|---|---|---|---|
| 官方转录 | —（页面自带） | 免费 | — | — | 页面自带转录的单集 |
| `paraformer` | `paraformer-v2` | **0.00008 元/秒** | 10h，**每月 1 号自动续** | ✅ | 日常省钱主力（纯中文清晰对谈/单人） |
| `qwen` | `qwen3-asr-flash-filetrans` | 0.00022 元/秒 | 10h，开通后 90 天一次性 | ❌ | 单人、中英混/专名多 |
| `funasr` | `fun-asr` | 0.00022 元/秒 | 10h，开通后 90 天一次性 | ✅ | 多人对谈、或要高质量的那几期 |

> ⚠️ **地域说明**：上表单价与免费额度均针对**中国内地（华北2·北京）** 地域。其他地域（如新加坡、美国）定价不同、且通常**没有免费额度**，请以[百炼官方定价页](https://help.aliyun.com/zh/model-studio/model-pricing)为准。海外账号需用对应地域的 API Key，并在命令加 `--region intl`。
>
> ⚠️ **额度用完不会自动切换模型**：若你在百炼设了"免费额度用完即停"，某模型额度耗尽后，调用它只会**报错**。默认脚本不自动降级，需手动换 `--backend` 重跑；也可用下方 `--fallback` 让脚本自动换。

**成本参考**（按秒计费，输出不计费）：一期 90 分钟 ≈ paraformer ¥0.43 / qwen·funasr ¥1.2。三笔免费额度是**独立三个池子**，低频用量基本用不完。

**选型策略（先用免费额度、再看性价比）**：
1. 有官方转录 → 直接用，零成本。
2. 日常对谈/单人 → **优先 `paraformer --diarize`**（每月白给 10h、更便宜、也能分离）。转完看脚本的**质量自检**提示：若警告"英文占比高"或你扫一眼发现专名错得多 → 用 `funasr` 重转这一期。
3. 中英混重 / 音质差 / 想要高质量的少数期 → `funasr`（对谈）或 `qwen`（单人），把它们 90 天一次性额度用在刀刃上。

> `paraformer` 与 `funasr` 用法完全一致（同接口/同参数：`--diarize`、`--speaker-count`、`--vocabulary-id`），只是 paraformer 是老一代模型、识别精度略弱。热词表在百炼控制台创建后用 `--vocabulary-id` 传入，可提升嘉宾名/术语。另有可选的通用后端 `--backend api`（其它 OpenAI 兼容 ASR，需先下载音频），一般用不到。

**自动降级 `--fallback`**：给一串后端顺序（逗号分隔），某个额度用尽/欠费时自动换下一个重试（其它错误不切、直接报错）。省钱的放前面：

```bash
python scripts/transcribe.py --from-meta ./_work --out ./_work --fallback paraformer,funasr,qwen --diarize --speaker-count 2 --language zh
```
（qwen 不支持说话人分离，若降级到它则该期无 `【说话人N】`。）

---

## 云端转录（Qwen）详细配置步骤

### 第 1 步：注册并开通阿里云百炼
1. 打开 https://bailian.console.aliyun.com/ ，用阿里云账号登录（没有就先注册，需实名认证）。
2. 首次进入会提示「开通百炼大模型服务」，点开通（开通免费；新用户通常有一笔试用免费额度）。

### 第 2 步：获取 API Key
1. 在百炼控制台右上角头像 → 「API-KEY」，或直接访问 https://bailian.console.aliyun.com/?tab=api#/api-key
2. 点「创建我的 API-KEY」，复制出来的 `sk-xxxxxxxx`（只显示一次，妥善保存）。
3. 地域说明：默认「北京」地域。若你用的是「新加坡（国际）」地域，API Key 不同，且运行时要加 `--region intl`。

### 第 3 步：把 Key 设为环境变量
- macOS / Linux（当前终端临时生效）：
  ```bash
  export DASHSCOPE_API_KEY="sk-你复制的key"
  ```
  想永久生效，把上面这行加进 `~/.bashrc` 或 `~/.zshrc`，再 `source ~/.zshrc`。
- Windows PowerShell：
  ```powershell
  setx DASHSCOPE_API_KEY "sk-你复制的key"
  ```
  （setx 需重开终端生效）

### 第 4 步：确认额度/计费（可选但建议）
- 计费（**中国内地·北京地域**）：按音频秒数（qwen ¥0.00022/秒），一期 90 分钟约 ¥1.2；paraformer 更便宜（¥0.00008/秒，约 ¥0.43/期）。新账号有免费额度（见上表）。其他地域价格不同、通常无免费额度。
- 免费额度与单价会变，以定价页为准：https://help.aliyun.com/zh/model-studio/model-pricing
- 余额/用量在百炼控制台「费用」或「资源」里查看。建议先设个「费用预警」防意外。

### 第 5 步：跑转录
无需下载音频，直接用小宇宙音频直链（`--from-meta` 自动从 meta.json 读取，bash / PowerShell 都适用）：
```bash
# 先解析拿到 meta.json（含 audio_url）
python scripts/fetch_episode.py "https://www.xiaoyuzhoufm.com/episode/xxxx" --out ./_work
# 单人口播：qwen
python scripts/transcribe.py --from-meta ./_work --out ./_work --backend qwen --language zh
# 多人对谈：fun-asr + 说话人分离（转出来每句带【说话人N】）
python scripts/transcribe.py --from-meta ./_work --out ./_work --backend funasr --diarize --speaker-count 2 --language zh
# 新加坡地域都加 --region intl
```
成功后得到 `./_work/transcript.txt` 和 `./_work/transcript.srt`。

> **Windows PowerShell 注意**：设 Key 用 `$env:DASHSCOPE_API_KEY = "sk-xxx"`（当前窗口）或 `setx DASHSCOPE_API_KEY "sk-xxx"`（永久，需重开窗口）。命令**不能用 `\` 续行**，上面每条都是单行，整行复制即可。

### 常见报错
- `缺配置 DASHSCOPE_API_KEY`：环境变量没设或没在同一个终端。
- 提交后一直 FAILED / 拿不到结果：多为音频 URL 不可公网访问、或地域与 Key 不匹配（北京 Key 配了 intl，或反之）。
- **报"未解析出文本"但任务其实成功了**：脚本会存 `./_work/dashscope_raw_result.json`。用恢复模式重新解析、**不重复计费**：
  ```bash
  python scripts/transcribe.py --from-raw ./_work/dashscope_raw_result.json --out ./_work
  ```
  （注意：结果下载链接有时效，一般约 24 小时内有效，过期需重新转录。）若仍解析不出，脚本会再存一份内层 `dashscope_transcription.json` 供排查。

---

## 用法一：交给 Claude（或任意 agent）
装好后直接说，例如：
> 把这期小宇宙整理成笔记：https://www.xiaoyuzhoufm.com/episode/xxxx （财经类）

Claude 会：解析链接 → 分层拿转录（官方转录/Qwen 云端）→ 判类型选模板 → 生成 md。
这条路的好处：agent 还能顺带联网核实股票代码、读图表，最完整。

## 用法二：用任意 LLM 写笔记（不绑定 Claude）
写笔记只是"读逐字稿 + 套模板"，任何长上下文 LLM 都能做。`make_notes.py` 走 OpenAI 兼容接口，DeepSeek / 通义千问 / Kimi / GPT / 智谱 GLM 等都行：

```bash
# 1) 配置任意 OpenAI 兼容 LLM（示例：DeepSeek）
export LLM_API_BASE="https://api.deepseek.com/v1"
export LLM_API_KEY="sk-xxx"
export LLM_MODEL="deepseek-chat"
# 2) 生成笔记（--type 可指定，或 auto 让模型自己判断）
python scripts/make_notes.py --work ./_work --type auto --out ./笔记.md
```
常见 base_url：DeepSeek `https://api.deepseek.com/v1`；通义千问百炼 `https://dashscope.aliyuncs.com/compatible-mode/v1`；Kimi `https://api.moonshot.cn/v1`；智谱 `https://open.bigmodel.cn/api/paas/v4`。

**没有 API Key？** 用 `--dump-prompt` 把提示词导成一个文件，整段复制粘贴到任意网页版 AI（ChatGPT / DeepSeek / Gemini / 通义 等）即可，免 Key：
```bash
python scripts/make_notes.py --work ./_work --type knowledge --dump-prompt
# 生成 ./_work/note_prompt.md，整段贴进任意聊天框
```
> 局限：纯 API/网页调用不能联网/读图，股票代码会标"待核实"、图表只据 shownotes 文本描述。要完整体验用「用法一」（Claude/agent 直接读模板写，还能联网核实代码、读图表）。

## 目录
- `SKILL.md`                   流程说明（技能主文件）
- `scripts/fetch_episode.py`   解析链接、下载音频、取 shownotes/章节/官方转录 + 主播嘉宾线索
- `scripts/transcribe.py`      转录（qwen=qwen3-asr-flash-filetrans / funasr=fun-asr / 通用 api）
- `scripts/make_notes.py`      用任意 OpenAI 兼容 LLM 写笔记（不绑定 Claude）
- `templates/`                 五套模板：财经(含行情型/对谈型子分支)、科技商业、人物访谈、知识科普、通用
- `examples/`                  两期真实成品笔记（demo）
