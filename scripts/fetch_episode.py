#!/usr/bin/env python3
"""
fetch_episode.py — 解析小宇宙(Xiaoyuzhou FM)单集公开页面。

用法:
    python fetch_episode.py "<url_or_episode_id>" --out ./_work [--download]

产物 (写入 --out 目录):
    meta.json               元数据 (title / podcast_title / pub_date / duration_sec / audio_url / eid / has_official_transcript)
    shownotes.md            shownotes 正文 (HTML -> Markdown, 保留图片链接)
    chapters.json           章节 (若有)
    official_transcript.txt 官方转录 (若页面自带)
    audio.m4a               音频 (仅当 --download)

仅支持公开单集; 付费/需登录内容拿不到直链。纯标准库, 无第三方依赖。
"""
import argparse, json, os, re, sys, html, urllib.request, urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def episode_url(arg: str) -> str:
    arg = arg.strip()
    if arg.startswith("http"):
        return arg.split("?")[0]
    # 只给了 id
    return f"https://www.xiaoyuzhoufm.com/episode/{arg}"


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "zh-CN,zh;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        sys.exit(f"[错误] 页面请求失败 HTTP {e.code}: {url}\n"
                 f"       若是付费/需登录内容，请在小宇宙 App 内导出音频后走'已自备音频'路径。")
    except Exception as e:
        sys.exit(f"[错误] 无法访问 {url}: {e}")


def extract_next_data(page: str) -> dict:
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def og_meta(page: str, prop: str) -> str:
    m = re.search(
        rf'<meta[^>]+property=["\']og:{prop}["\'][^>]+content=["\'](.*?)["\']',
        page)
    return html.unescape(m.group(1)) if m else ""


def html_to_md(raw: str) -> str:
    """极简 HTML -> Markdown, 保留段落、列表、图片、链接。"""
    if not raw:
        return ""
    s = raw
    s = re.sub(r'<br\s*/?>', '\n', s, flags=re.I)
    s = re.sub(r'</p>', '\n\n', s, flags=re.I)
    s = re.sub(r'<p[^>]*>', '', s, flags=re.I)
    s = re.sub(r'<li[^>]*>', '- ', s, flags=re.I)
    s = re.sub(r'</li>', '\n', s, flags=re.I)
    # 图片 -> Markdown, 保留 alt
    s = re.sub(r'<img[^>]*?alt=["\'](.*?)["\'][^>]*?src=["\'](.*?)["\'][^>]*?>',
               r'\n![\1](\2)\n', s, flags=re.I)
    s = re.sub(r'<img[^>]*?src=["\'](.*?)["\'][^>]*?>',
               r'\n![](\1)\n', s, flags=re.I)
    # 链接 -> Markdown
    s = re.sub(r'<a[^>]*?href=["\'](.*?)["\'][^>]*?>(.*?)</a>',
               r'[\2](\1)', s, flags=re.I | re.S)
    s = re.sub(r'<[^>]+>', '', s)          # 去掉其余标签
    s = html.unescape(s)
    s = re.sub(r'\n{3,}', '\n\n', s).strip()
    return s


def find_episode(next_data: dict) -> dict:
    """从 __NEXT_DATA__ 中定位 episode 对象。结构随版本可能变化, 做多路径兜底。"""
    try:
        pp = next_data["props"]["pageProps"]
    except Exception:
        return {}
    for key in ("episode", "data", "detail"):
        v = pp.get(key)
        if isinstance(v, dict) and ("enclosure" in v or "title" in v):
            return v
    # 深搜: 找第一个含 enclosure.url 的 dict
    stack = [pp]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            enc = cur.get("enclosure")
            if isinstance(enc, dict) and enc.get("url"):
                return cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return {}


def download(url: str, path: str):
    print(f"[下载] {url}\n    -> {path}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                print(f"\r    {pct:3d}%  {done>>20}/{total>>20} MB",
                      end="", flush=True)
        print()
    print("[完成] 音频已保存")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="小宇宙链接或 episode id")
    ap.add_argument("--out", default="./_work", help="输出目录")
    ap.add_argument("--download", action="store_true", help="同时下载音频")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    url = episode_url(args.target)
    print(f"[解析] {url}")
    page = fetch_html(url)
    nd = extract_next_data(page)
    ep = find_episode(nd)

    # ---- 组装元数据, 逐字段兜底 ----
    title = ep.get("title") or og_meta(page, "title")
    audio_url = ((ep.get("enclosure") or {}).get("url")) or og_meta(page, "audio")
    podcast = ((ep.get("podcast") or {}).get("title")) or ""
    pub_date = ep.get("pubDate") or ""
    duration = ep.get("duration") or 0
    eid = ep.get("eid") or ep.get("id") or url.rstrip("/").split("/")[-1]

    shownotes_html = ep.get("shownotes") or ep.get("description") or ""
    shownotes_md = html_to_md(shownotes_html) or og_meta(page, "description")

    # 官方转录: 字段名随版本不同, 尝试几个常见键
    transcript = ""
    for k in ("transcript", "subtitles", "captions", "textTrack"):
        v = ep.get(k)
        if isinstance(v, str) and len(v) > 200:
            transcript = v
            break
        if isinstance(v, list) and v and isinstance(v[0], dict):
            transcript = "\n".join(
                seg.get("text", "") for seg in v if seg.get("text"))
            if len(transcript) > 200:
                break

    chapters = ep.get("chapters") or []

    # 提取主播/嘉宾线索：结构化的 podcasters（主播）+ 从标题/shownotes 猜嘉宾
    hosts = []
    pod = ep.get("podcast") or {}
    for p in (pod.get("podcasters") or []):
        n = (p.get("nickname") or p.get("name") or "").strip()
        if n and n not in hosts:
            hosts.append(n)
    for p in (ep.get("podcasters") or []):  # 单集级，可能含嘉宾
        n = (p.get("nickname") or p.get("name") or "").strip()
        if n and n not in hosts:
            hosts.append(n)
    # 从标题里粗略挖嘉宾（"对话XX""对谈XX""XX：""聊聊XX"等），仅作线索供 LLM 参考
    guest_hints = re.findall(r"(?:对话|对谈|专访|访谈|聊聊|嘉宾)[：:\s]*([\u4e00-\u9fa5A-Za-z·]{2,12})", title)

    meta = {
        "eid": eid,
        "url": url,
        "title": title,
        "podcast_title": podcast,
        "hosts": hosts,                 # 结构化主播名
        "guest_hints": guest_hints,     # 从标题猜的嘉宾线索（不保证准确）
        "pub_date": pub_date,
        "duration_sec": duration,
        "audio_url": audio_url,
        "has_official_transcript": bool(transcript),
    }

    with open(os.path.join(args.out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "shownotes.md"), "w", encoding="utf-8") as f:
        f.write(shownotes_md or "(无 shownotes)")
    if chapters:
        with open(os.path.join(args.out, "chapters.json"), "w", encoding="utf-8") as f:
            json.dump(chapters, f, ensure_ascii=False, indent=2)
    if transcript:
        with open(os.path.join(args.out, "official_transcript.txt"), "w", encoding="utf-8") as f:
            f.write(transcript)

    print("\n=== 解析结果 ===")
    print(f"  节目   : {podcast}")
    print(f"  单集   : {title}")
    print(f"  主播   : {', '.join(hosts) or '(未取到，可从 shownotes 识别)'}")
    if guest_hints:
        print(f"  嘉宾线索: {', '.join(guest_hints)}（仅供参考，以 shownotes 为准）")
    print(f"  发布   : {pub_date}")
    print(f"  时长   : {duration and round(duration/60,1)} 分钟")
    print(f"  官方转录: {'有 ✅ (可跳过 ASR)' if transcript else '无 (需转录音频)'}")
    print(f"  音频   : {audio_url or '(未取到, 可能是付费/需登录内容)'}")
    print(f"  产物   : {os.path.abspath(args.out)}")

    if args.download:
        if not audio_url:
            sys.exit("[错误] 未取到音频直链, 无法下载。")
        download(audio_url, os.path.join(args.out, "audio.m4a"))


if __name__ == "__main__":
    main()
