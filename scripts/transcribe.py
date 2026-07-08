#!/usr/bin/env python3
"""
transcribe.py — 把音频转成文字。云端后端（阿里云百炼 DashScope，同一个 DASHSCOPE_API_KEY）：

  qwen    (模型 qwen3-asr-flash-filetrans，单人口播、长音频、便宜；不区分说话人)
      export DASHSCOPE_API_KEY="sk-xxx"
      python transcribe.py --from-meta ./_work --out ./_work --backend qwen [--region cn|intl]

  funasr  (模型 fun-asr，对谈型首选：支持说话人分离 + 热词)
      python transcribe.py --from-meta ./_work --out ./_work --backend funasr --diarize [--speaker-count 2] [--vocabulary-id vocab-xxx]

  api     (可选：其它 OpenAI 兼容的语音转写接口，需先下载音频为本地文件)
      export ASR_API_BASE=...; export ASR_API_KEY=...
      python transcribe.py ./_work/audio.m4a --out ./_work --backend api --model whisper-large-v3

音频来源：云端后端用公网 URL（推荐 --from-meta 自动读 meta.json 的 audio_url，无需下载）。
产物：transcript.txt（纯文本；开分离时带【说话人N】标注）、transcript.srt（带时间戳）。
"""
import argparse, os, sys, json, time, urllib.request


# ---------------- 通用输出 ----------------
def fmt_ts(sec: float) -> str:
    h = int(sec // 3600); m = int(sec % 3600 // 60)
    s = int(sec % 60); ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_outputs(out_dir, segments):
    """segments: list of (start_sec, end_sec, text)"""
    txt = os.path.join(out_dir, "transcript.txt")
    srt = os.path.join(out_dir, "transcript.srt")
    with open(txt, "w", encoding="utf-8") as ft, open(srt, "w", encoding="utf-8") as fs:
        for i, (start, end, text) in enumerate(segments, 1):
            text = (text or "").strip()
            if not text:
                continue
            ft.write(text + "\n")
            fs.write(f"{i}\n{fmt_ts(start)} --> {fmt_ts(end)}\n{text}\n\n")
    print(f"[完成] 转录文本 -> {txt}")
    print(f"       字幕     -> {srt}")


def _http_json(url, headers, data=None, method=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------- DashScope 异步任务：提交 / 轮询 / 解析（qwen 与 funasr 共用） ----------
def _dashscope_urls(region):
    if region == "intl":
        return ("https://dashscope-intl.aliyuncs.com/api/v1/services/audio/asr/transcription",
                "https://dashscope-intl.aliyuncs.com/api/v1/tasks/")
    return ("https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription",
            "https://dashscope.aliyuncs.com/api/v1/tasks/")


def _submit_and_poll(submit_url, task_base, key, payload, out_dir):
    print("    提交异步任务...")
    submit = _http_json(submit_url,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "X-DashScope-Async": "enable"},
        data=json.dumps(payload).encode(), method="POST", timeout=60)
    task_id = (submit.get("output") or {}).get("task_id")
    if not task_id:
        sys.exit(f"[错误] 未拿到 task_id：{json.dumps(submit, ensure_ascii=False)[:400]}")
    print(f"    task_id = {task_id}，轮询中（长音频约 2-5 分钟）...")
    for _ in range(360):
        time.sleep(10)
        q = _http_json(task_base + task_id,
                       headers={"Authorization": f"Bearer {key}"}, timeout=30)
        st = (q.get("output") or {}).get("task_status")
        print(f"\r    状态: {st}   ", end="", flush=True)
        if st == "SUCCEEDED":
            print(); return q
        if st in ("FAILED", "CANCELED", "UNKNOWN"):
            sys.exit(f"\n[错误] 任务 {st}：{json.dumps(q, ensure_ascii=False)[:500]}")
    sys.exit("\n[错误] 轮询超时（>1 小时）。")


def _extract_segments(result, out_dir, want_speaker):
    """从任务结果里取 transcription_url -> transcripts[].sentences[]。
    兼容两种外层结构：output.result(单数, qwen filetrans) 与 output.results(复数数组, fun-asr)。
    want_speaker=True 时，说话人变化处给文本加【说话人N】前缀。"""
    segments, last_spk = [], None
    out = result.get("output", {})
    # 单数 result（qwen3-asr-flash-filetrans）或 复数 results（fun-asr）
    results = out.get("results")
    if results is None:
        single = out.get("result")
        results = [single] if single else []
    if isinstance(results, dict):
        results = [results]
    for item in results:
        if not isinstance(item, dict):
            continue
        if item.get("subtask_status") == "FAILED":
            print(f"    [警告] 子任务失败：{item.get('code')} {item.get('message')}")
            continue
        trans_url = item.get("transcription_url") or item.get("url")
        data = None
        if trans_url:
            try:
                data = _http_json(trans_url, headers={}, timeout=60)
            except Exception as e:
                print(f"    [警告] 拉取转写结果失败：{e}")
        else:
            data = item
        if not data:
            continue
        for tr in (data.get("transcripts") or []):
            sents = tr.get("sentences") or []
            for s in sents:
                text = s.get("text") or s.get("Text") or ""
                spk = s.get("speaker_id", s.get("speakerId"))
                if want_speaker and spk is not None and spk != last_spk:
                    text = f"【说话人{spk}】{text}"
                    last_spk = spk
                bt = s.get("begin_time", s.get("beginTime", 0)) or 0
                et = s.get("end_time", s.get("endTime", 0)) or 0
                segments.append((bt / 1000.0, et / 1000.0, text))
            if not sents and tr.get("text"):
                segments.append((0, 0, tr["text"]))
    if not segments:
        raw = os.path.join(out_dir, "dashscope_raw_result.json")
        with open(raw, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        inner = os.path.join(out_dir, "dashscope_transcription.json")
        # 若拿到了内层 JSON 但没解析出，也存一份便于排查
        try:
            if trans_url and data:
                with open(inner, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                sys.exit(f"[错误] 拿到结果但未解析出文本，已存 {inner} 供排查（把它发给我即可）。")
        except Exception:
            pass
        sys.exit(f"[错误] 未解析出文本，已存原始返回到 {raw} 供排查。")
    return segments


def _check_url_and_key(audio_url):
    key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not key:
        sys.exit("[缺配置] 请设置 DASHSCOPE_API_KEY（百炼 API Key）。\n"
                 "         获取：https://bailian.console.aliyun.com/ -> API-KEY")
    if not audio_url.lower().startswith("http"):
        sys.exit("[用法错误] 云端后端需要【公网音频 URL】。请用 --from-meta ./_work "
                 "自动读取 meta.json 里的 audio_url。")
    return key


# ---------------- 后端：qwen（qwen3-asr-flash-filetrans） ----------------
def run_qwen(audio_url, out_dir, model, language, region):
    key = _check_url_and_key(audio_url)
    submit_url, task_base = _dashscope_urls(region)
    params = {"channel_id": [0], "enable_itn": True, "enable_words": True}
    if language:
        params["language"] = language
    payload = {"model": model, "input": {"file_url": audio_url}, "parameters": params}
    print(f"[转录] Qwen {model} ({region})")
    result = _submit_and_poll(submit_url, task_base, key, payload, out_dir)
    write_outputs(out_dir, _extract_segments(result, out_dir, want_speaker=False))


# ---------------- 后端：funasr（fun-asr，说话人分离 + 热词） ----------------
def run_funasr(audio_url, out_dir, model, language, region, diarize, speaker_count, vocabulary_id):
    key = _check_url_and_key(audio_url)
    submit_url, task_base = _dashscope_urls(region)
    params = {"channel_id": [0]}
    if diarize:
        params["diarization_enabled"] = True
        if speaker_count:
            params["speaker_count"] = speaker_count
    if vocabulary_id:
        params["vocabulary_id"] = vocabulary_id
    if language:
        params["language_hints"] = [language]
    payload = {"model": model, "input": {"file_urls": [audio_url]}, "parameters": params}
    print(f"[转录] Fun-ASR {model} ({region})，说话人分离={'开' if diarize else '关'}")
    if diarize:
        print("    注意：开启说话人分离建议音频≤2小时，且仅支持单声道。")
    result = _submit_and_poll(submit_url, task_base, key, payload, out_dir)
    write_outputs(out_dir, _extract_segments(result, out_dir, want_speaker=diarize))


# ---------------- 后端：通用 OpenAI 兼容 API ----------------
def run_api(audio, out_dir, model, language):
    base = os.environ.get("ASR_API_BASE", "").rstrip("/")
    key = os.environ.get("ASR_API_KEY", "")
    if not base or not key:
        sys.exit("[缺配置] 请设置 ASR_API_BASE 和 ASR_API_KEY")
    if audio.lower().startswith("http"):
        sys.exit("[用法错误] 该后端需本地文件，请先下载音频。")
    url = f"{base}/audio/transcriptions"
    print(f"[转录] API 后端 {url}, model={model}")
    boundary = "----xyznote" + str(int(time.time()))
    with open(audio, "rb") as f:
        audio_bytes = f.read()
    parts = []
    def field(name, value):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                     f'name="{name}"\r\n\r\n{value}\r\n'.encode())
    field("model", model)
    if language:
        field("language", language)
    field("response_format", "verbose_json")
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f'filename="{os.path.basename(audio)}"\r\nContent-Type: audio/m4a\r\n\r\n'.encode()
        + audio_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(url, data=b"".join(parts),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    segs = data.get("segments")
    collected = ([(s.get("start", 0), s.get("end", 0), s.get("text", "")) for s in segs]
                 if segs else [(0, 0, data.get("text", ""))])
    write_outputs(out_dir, collected)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", nargs="?", default=None,
                    help="本地音频路径，或（qwen/funasr）公网音频 URL；也可用 --from-meta 自动读取")
    ap.add_argument("--from-meta", default=None,
                    help="给出含 meta.json 的目录（如 ./_work），自动读取其中的 audio_url，无需手动传链接")
    ap.add_argument("--from-raw", default=None,
                    help="从已保存的 dashscope_raw_result.json 恢复解析（任务已成功、不重新转录、不重复计费）")
    ap.add_argument("--out", default="./_work")
    ap.add_argument("--backend", choices=["qwen", "funasr", "api"],
                    default="qwen")
    ap.add_argument("--model", default=None,
                    help="qwen默认 qwen3-asr-flash-filetrans；funasr默认 fun-asr；api默认 whisper-large-v3")
    ap.add_argument("--language", default="zh")
    ap.add_argument("--region", choices=["cn", "intl"], default="cn",
                    help="云端地域：cn=北京，intl=新加坡（API Key 不同）")
    # fun-asr 专用
    ap.add_argument("--diarize", action="store_true", help="funasr: 开启说话人分离")
    ap.add_argument("--speaker-count", type=int, default=None, help="funasr: 说话人数量提示(2-100)")
    ap.add_argument("--vocabulary-id", default=None, help="funasr: 热词表ID(vocabulary_id)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    # 恢复模式：从已成功的 raw 结果解析，不重新转录
    if args.from_raw:
        try:
            with open(args.from_raw, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            sys.exit(f"[错误] 读取 {args.from_raw} 失败：{e}")
        print(f"[恢复] 从 {args.from_raw} 解析已完成的转录结果...")
        write_outputs(args.out, _extract_segments(raw, args.out, want_speaker=args.diarize))
        return

    # 解析音频来源：--from-meta 优先（自动读 meta.json 的 audio_url）
    audio = args.audio
    if args.from_meta:
        meta_path = os.path.join(args.from_meta, "meta.json")
        try:
            with open(meta_path, encoding="utf-8") as f:
                audio = json.load(f).get("audio_url")
        except Exception as e:
            sys.exit(f"[错误] 读取 {meta_path} 失败：{e}")
        if not audio:
            sys.exit(f"[错误] {meta_path} 里没有 audio_url（可能是付费/需登录单集）。")
    if not audio:
        sys.exit("[用法] 需给出音频：本地路径、公网URL，或 --from-meta ./_work")

    if args.backend == "qwen":
        run_qwen(audio, args.out, args.model or "qwen3-asr-flash-filetrans",
                 args.language, args.region)
    elif args.backend == "funasr":
        run_funasr(audio, args.out, args.model or "fun-asr", args.language,
                   args.region, args.diarize, args.speaker_count, args.vocabulary_id)
    else:
        run_api(audio, args.out, args.model or "whisper-large-v3", args.language)


if __name__ == "__main__":
    main()
