#!/usr/bin/env python3
"""
make_notes.py — 用【任意 OpenAI 兼容的 LLM】把逐字稿整理成分类型 Markdown 笔记。

让"写笔记"这一步不绑定某一个 AI：DeepSeek、通义千问(百炼兼容模式)、Kimi、GPT、
智谱 GLM 等，只要是 OpenAI 兼容接口都能用。也可以不用本脚本，直接在 Claude Code /
Codex 等 agent 里让它读模板写笔记（那条路还能联网核实代码、读图表，更完整）。

配置（环境变量）：
  LLM_API_BASE   OpenAI 兼容的 base_url。例：
                 DeepSeek     https://api.deepseek.com/v1
                 通义千问百炼  https://dashscope.aliyuncs.com/compatible-mode/v1
                 Kimi(月之暗面) https://api.moonshot.cn/v1
                 智谱 GLM      https://open.bigmodel.cn/api/paas/v4
                 OpenAI       https://api.openai.com/v1
  LLM_API_KEY    对应平台的 key
  LLM_MODEL      模型名，如 deepseek-chat / qwen-plus / moonshot-v1-128k / glm-4-plus / gpt-4o
                 ⚠️ 播客逐字稿较长，请选支持长上下文的模型。

用法：
  python make_notes.py --work ./_work --type auto --out ./笔记.md
    --work   含 transcript.txt / meta.json / shownotes.md 的目录
    --type   finance / tech-business / interview / knowledge / general / auto（默认 auto，让模型判断）
    --out    输出的 md 路径（默认 ./_work/notes.md）

局限：纯 API 调用无法联网/读图，故股票代码会标"待核实"、图表只据 shownotes 文本描述。
"""
import argparse, json, os, sys, urllib.request

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(SKILL_ROOT, "templates")
TYPES = ["finance", "tech-business", "interview", "knowledge", "general"]


def llm_chat(messages, temperature=0.3, max_tokens=8000):
    base = os.environ.get("LLM_API_BASE", "").rstrip("/")
    key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")
    if not base or not key or not model:
        sys.exit("[缺配置] 请设置 LLM_API_BASE / LLM_API_KEY / LLM_MODEL（见脚本头部说明）。")
    body = json.dumps({
        "model": model, "messages": messages,
        "temperature": temperature, "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"[错误] LLM 接口 HTTP {e.code}：{e.read().decode('utf-8', 'ignore')[:300]}")
    except Exception as e:
        sys.exit(f"[错误] 调用 LLM 失败：{e}")
    return data["choices"][0]["message"]["content"]


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def classify(meta, shownotes, transcript_head):
    prompt = (
        "判断下面这期播客最贴切的类型，只回复一个词，从这五个里选："
        "finance / tech-business / interview / knowledge / general。\n"
        "标准：财经投资=finance；科技创业商业=tech-business；以嘉宾经历观点为主的对谈=interview；"
        "讲解学科/概念/心灵成长=knowledge；都不贴=general。\n\n"
        f"播客名：{meta.get('podcast_title','')}\n标题：{meta.get('title','')}\n"
        f"简介：{shownotes[:600]}\n开头：{transcript_head[:600]}"
    )
    ans = llm_chat([{"role": "user", "content": prompt}], temperature=0, max_tokens=10).strip().lower()
    for t in TYPES:
        if t in ans:
            return t
    return "general"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="./_work", help="含 transcript.txt/meta.json/shownotes.md 的目录")
    ap.add_argument("--transcript", default=None, help="单独指定逐字稿路径（默认 <work>/transcript.txt）")
    ap.add_argument("--type", default="auto", choices=["auto"] + TYPES)
    ap.add_argument("--dump-prompt", action="store_true",
                    help="不调用API，把提示词写成文件，供粘贴到任意网页版AI（免Key）；需配合 --type 指定类型")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    tpath = args.transcript or os.path.join(args.work, "transcript.txt")
    transcript = read(tpath)
    if not transcript.strip():
        sys.exit(f"[错误] 逐字稿为空或不存在：{tpath}")
    meta = {}
    try:
        meta = json.loads(read(os.path.join(args.work, "meta.json")) or "{}")
    except Exception:
        pass
    shownotes = read(os.path.join(args.work, "shownotes.md"))

    # 定类型
    typ = args.type
    if typ == "auto":
        if args.dump_prompt:
            sys.exit("[用法] --dump-prompt 时请用 --type 明确指定类型"
                     "（finance/tech-business/interview/knowledge/general），因为没有 LLM 帮你自动判类型。")
        print("[分类] 让模型判断类型...")
        typ = classify(meta, shownotes, transcript[:800])
    print(f"[类型] {typ}")
    template = read(os.path.join(TEMPLATE_DIR, f"{typ}.md"))
    if not template:
        sys.exit(f"[错误] 找不到模板 {typ}.md")

    # 组织提示词
    meta_txt = "\n".join(f"{k}: {v}" for k, v in meta.items()
                         if k in ("podcast_title", "title", "pub_date", "duration_sec",
                                  "url", "hosts", "guest_hints"))
    system = (
        "你是专业的中文播客笔记整理师。请严格按用户给出的【模板】结构与排版要求，"
        "基于【逐字稿】输出一份详尽的简体中文 Markdown 笔记。要求：\n"
        "1) 忠实于逐字稿，不编造其中没有的内容；模板里要求'若未涉及则如实标注'的地方照实写。\n"
        "2) 保留模板的 ━━━ 分节标题、表格、加粗字段、逻辑链代码块等排版。\n"
        "3) 不要把模板里的说明性文字原样保留，要输出填好的真实内容。\n"
        "4) 从 shownotes、标题、逐字稿识别主播与嘉宾的姓名及背景，填入基本信息。\n"
        "5) 你无法联网，遇到股票/基金/ETF 代码时标注'（代码待核实）'，不要编造代码。\n"
        "6) 只输出最终笔记本身，不要额外解释。"
    )
    user = (f"【元数据】\n{meta_txt}\n\n【shownotes】\n{shownotes[:4000]}\n\n"
            f"【模板】\n{template}\n\n【逐字稿】\n{transcript}")

    # 免 Key 模式：把提示词导出成文件，供粘贴到任意网页版 AI
    if args.dump_prompt:
        out = args.out or os.path.join(args.work, "note_prompt.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write("> 把下面【系统指令】和【内容】整段复制，粘贴给任意 AI"
                    "（ChatGPT / DeepSeek / Gemini / 通义 等网页版即可），就能生成笔记。\n\n"
                    "=== 系统指令 ===\n" + system + "\n\n=== 内容 ===\n" + user)
        print(f"[完成] 提示词已写入 {out}，整段粘贴到任意 AI 聊天框即可（无需 API Key）。")
        return

    print(f"[生成] 调用 LLM（模型={os.environ.get('LLM_MODEL')}）...")
    note = llm_chat([{"role": "system", "content": system},
                     {"role": "user", "content": user}])

    out = args.out or os.path.join(args.work, "notes.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(note)
    print(f"[完成] 笔记已写入 {out}")


if __name__ == "__main__":
    main()
