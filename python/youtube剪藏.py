#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  YouTube 剪藏：本地下载 + 字幕（CC 优先 / whisper 兜底）+ 本地翻译
#
#  零云原则：全本地处理，不调用任何云 API
#    · 下载：yt-dlp（--proxy 走本机代理）
#    · 字幕：官方 CC 自动字幕优先（快）；无字幕 → whisper + demucs 链路
#    · 翻译：英文内容本地 Ollama 翻译成中文（原文+译文双语）
#
#  用法：
#    python3 youtube剪藏.py "https://youtu.be/xxxx" [--proxy http://127.0.0.1:7897]
# ============================================================
import argparse, json, os, re, subprocess, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_ROOT") or HERE.parent.parent.parent)
os.environ.setdefault("OBSIDIAN_VAULT_ROOT", str(VAULT_ROOT))

DL_DIR = VAULT_ROOT / "Link to Notes" / "下载"
NOTE_DIR = VAULT_ROOT / "Link to Notes" / "笔记"
PROXY = "http://127.0.0.1:7897"    # 本机 Clash 代理


def load(name, file):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


import time as _time

YT_COOKIES = None   # 缓存路径（首次提取后复用，避免频繁钥匙串弹窗）


def ensure_cookies(force=False):
    """YouTube cookie 缓存：12 小时复用，只首次弹钥匙串"""
    global YT_COOKIES
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "zerocloud"
    cache.mkdir(parents=True, exist_ok=True)
    ck = cache / "youtube_cookies.txt"
    fresh = ck.is_file() and (_time.time() - ck.stat().st_mtime) < 12 * 3600
    if not (fresh and not force):
        try:
            ce = load("cookie_extract", "cookie_extract.py")
            ce.extract_cookies(["youtube.com", ".google.com"], browser="chrome", out=str(ck))
            print("  · cookie 已提取（首次，弹窗请点允许/输入密码）")
        except Exception as e:
            print(f"  ⚠ cookie 提取失败（{e}）")
    YT_COOKIES = str(ck) if ck.is_file() else None
    return YT_COOKIES


def yt(url, *args):
    cmd = ["yt-dlp", "--no-warnings", "--proxy", PROXY, "--socket-timeout", "20"]
    ck = ensure_cookies()
    if ck:
        cmd += ["--cookies", ck]
    cmd += list(args) + [url]
    return subprocess.run(cmd, capture_output=True, text=True)


def parse_srt(srt_text):
    """srt/vtt → [{"from_ms", "to_ms", "text"}]（兼容 vtt 无序号、align 参数）"""
    segs = []
    for block in re.split(r"\n\s*\n", srt_text.strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        # vtt 头部跳过；时间行可能在 lines[0]（vtt）或 lines[1]（srt 有序号）
        if lines[0].strip().upper() == "WEBVTT":
            lines = lines[1:]
        if len(lines) < 2:
            continue
        m = None
        for li in (0, 1):
            m = re.match(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})", lines[li])
            if m:
                text_lines = lines[li + 1:]
                break
        if not m:
            continue
        def ms(a, b, c, d):
            return (int(a) * 3600 + int(b) * 60 + int(c)) * 1000 + int(d)
        text = " ".join(text_lines).strip()
        if text:
            segs.append({"from": ms(*m.groups()[:4]), "to": ms(*m.groups()[4:]),
                         "text": re.sub(r"<[^>]+>", "", text)})
    return segs


def translate_lines_ollama(lines, model="qwen3:8b"):
    """逐行翻译（本地 Ollama），强制行数对应，返回与输入等长的译文列表"""
    import urllib.request
    numbered = "\n".join(f"L{i}: {t}" for i, t in enumerate(lines))
    prompt = ("You are a professional translator. Translate each line to Simplified Chinese. "
              "CRITICAL: output exactly the same number of lines, one translation per line, "
              "keep the 'L{n}:' prefix. Output ONLY translations, no explanation.\n\n" + numbered)
    body = json.dumps({"model": model, "prompt": prompt,
                       "stream": False, "temperature": 0.3}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=300).read())
    out = {}
    for line in (resp.get("response") or "").split("\n"):
        m = re.match(r"L(\d+):\s*(.*)", line.strip())
        if m:
            out[int(m.group(1))] = m.group(2).strip()
    return [out.get(i, "") for i in range(len(lines))]


def fetch_cc(url, safe):
    """抓取字幕：英文 + 中文（手动 + 自动翻译，零云）
    返回 (en_text, zh_text)；缺失的为 None"""
    r = yt(url, "--skip-download", "--write-subs", "--write-auto-subs",
           "--sub-langs", "en.*,zh-Hans,zh-CN,zh", "--sub-format", "srt/vtt",
           "-o", str(DL_DIR / f"{safe}.%(ext)s"))
    en_text = zh_text = None
    for ext in (".en.srt", ".en.vtt", ".srt", ".vtt"):
        p = DL_DIR / f"{safe}{ext}"
        if p.is_file():
            en_text = p.read_text(encoding="utf-8", errors="ignore")
            p.unlink(missing_ok=True)
    for ext in (".zh-Hans.srt", ".zh-Hans.vtt", ".zh-CN.srt", ".zh-CN.vtt",
                ".zh.srt", ".zh.vtt"):
        p = DL_DIR / f"{safe}{ext}"
        if p.is_file():
            zh_text = p.read_text(encoding="utf-8", errors="ignore")
            p.unlink(missing_ok=True)
    return en_text, zh_text


def download_video(url, safe):
    r = yt(url, "-f", "b", "-o", str(DL_DIR / f"{safe}.%(ext)s"))
    if r.returncode != 0:
        raise RuntimeError(f"下载失败（{r.stderr.strip()[-200:]}）")
    for ext in (".mp4", ".webm", ".mkv", ".mov"):
        p = DL_DIR / f"{safe}{ext}"
        if p.is_file():
            return p
    raise RuntimeError("下载后未找到视频")


def clip(url, out_dir=None, proxy=None, no_translate=False):
    global PROXY
    if proxy:
        PROXY = proxy
    print("▶ YouTube 视频…")
    # 探测
    r = yt(url, "--print", "%(title)s\t%(duration)s\t%(uploader)s")
    if r.returncode != 0:
        raise RuntimeError(f"链接解析失败（{r.stderr.strip()[-200:]}）")
    title, dur, uploader = r.stdout.strip().split("\t")
    title = re.sub(r"#\S+", "", title).strip() or "YouTube 视频"
    print(f"  标题：{title}（{dur}s，UP主 {uploader}）")
    safe = re.sub(r'[\\/:*?"<>|#]', "", title)[:40] or "YouTube视频"

    # 1) CC 字幕（英文 + 中文官方翻译，零云）
    en_cc, zh_cc = fetch_cc(url, safe)
    # 2) 下载视频（嵌入用）
    video = download_video(url, safe)

    out_dir = Path(out_dir) if out_dir else NOTE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if en_cc:
        # 英文视频规则：>30 分钟（1800s）为长视频 → 自动跳过翻译（省时）
        if not no_translate and int(dur) > 1800:
            no_translate = True
            print("  · 长视频（>30min）自动跳过翻译，仅英文")
        en_segs = parse_srt(en_cc)
        print(f"  · 抓到英文字幕 {len(en_segs)} 条")
        note_tag = "英文原文" if no_translate else "英文原文 + 本地 Ollama 中文"
        lines = [f"# {title}", "", f"![[{video.name}]]", "",
                 f"> YouTube 视频笔记 · {uploader} · 时长 {dur}s · CC 字幕 {len(en_segs)} 条 · {note_tag}",
                 "", "## 字幕", ""]
        # 本地 Ollama 翻译生成双语 srt（零云；--no-translate 跳过翻译仅英文）
        bilingual = []
        if no_translate:
            print("  · --no-translate：跳过翻译，仅英文")
            for s in en_segs:
                bilingual.append((s["from"], s["to"], s["text"], ""))
        else:
            chunks, cur = [], []
            for s in en_segs:
                cur.append(s)
                if sum(len(x["text"]) for x in cur) > 1000:
                    chunks.append(cur)
                    cur = []
            if cur:
                chunks.append(cur)
            print(f"  · 本地 Ollama 逐行翻译中（{len(chunks)} 块）…")
            try:
                for i, ch in enumerate(chunks):
                    tlines = translate_lines_ollama([x["text"] for x in ch])
                    for j, s in enumerate(ch):
                        t = tlines[j] if j < len(tlines) else ""
                        bilingual.append((s["from"], s["to"], s["text"], t))
            except Exception as e:
                print(f"  ⚠ 翻译失败（{e}），生成仅英文 srt")
                for s in en_segs:
                    bilingual.append((s["from"], s["to"], s["text"], ""))
        for s in en_segs:
            lines.append(f"[{fmt(s['from'])}] {s['text']}")
            lines.append("")
        # 双语 srt（与视频同名，播放器自动加载）
        srt_path = DL_DIR / f"{safe}.srt"
        srt_lines = []
        for idx, (f_, t_, en_t, zh_t) in enumerate(bilingual, 1):
            srt_lines.append(str(idx))
            srt_lines.append(f"{srt_ts(f_)} --> {srt_ts(t_)}")
            srt_lines.append(en_t)
            if zh_t:
                srt_lines.append(zh_t)
            srt_lines.append("")
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
        print(f"  · {'英文' if no_translate else '双语'}字幕已生成：{srt_path.name}（播放器加载即{'仅英文' if no_translate else '中英双行'}）")
    elif zh_cc:
        # 中文视频：直接用中文 CC 字幕，不翻译
        zh_segs = parse_srt(zh_cc)
        print(f"  · 抓到中文字幕 {len(zh_segs)} 条（中文视频，不翻译）")
        lines = [f"# {title}", "", f"![[{video.name}]]", "",
                 f"> YouTube 视频笔记 · {uploader} · 时长 {dur}s · CC 字幕 {len(zh_segs)} 条 · 中文原文",
                 "", "## 字幕", ""]
        for s in zh_segs:
            lines.append(f"[{fmt(s['from'])}] {s['text']}")
            lines.append("")
        srt_path = DL_DIR / f"{safe}.srt"
        srt_lines = []
        for idx, s in enumerate(zh_segs, 1):
            srt_lines.append(str(idx))
            srt_lines.append(f"{srt_ts(s['from'])} --> {srt_ts(s['to'])}")
            srt_lines.append(s["text"])
            srt_lines.append("")
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
        print(f"  · 中文字幕已生成：{srt_path.name}")
    else:
        # 无字幕：whisper 链路（语言按标题自动判断：中文标题→zh，否则 en）
        lang = "zh" if re.search(r'[一-鿿]', title) else "en"
        print(f"  · 无 CC 字幕，走 whisper 转录（lang={lang}）…")
        dy = load("抖音剪藏", "抖音剪藏.py")
        vocals = dy.separate_vocals(video)
        src = vocals if vocals else video
        vt = load("视频转录", "视频转录.py")
        jp = src.with_suffix(".json")
        if not jp.is_file():
            vt.transcribe(src, lang=lang)
        cc2 = load("标准字幕剪藏", "标准字幕剪藏.py")
        segs = json.load(open(jp, encoding="utf-8"))["transcription"]
        sub = cc2.resegment_natural(segs, src, min_w=15.0, max_w=50.0, pause_s=0.6)
        widths = [cc2.width(s["text"]) for s in sub]
        lines = [f"# {title}", "", f"![[{video.name}]]", "",
                 f"> YouTube 视频笔记 · {uploader} · 时长 {dur}s · whisper 转写 {len(sub)} 条"
                 + ("（demucs 人声分离）" if vocals else ""),
                 "", "## 字幕", ""]
        for s in sub:
            lines.append(f"[{fmt(s['from'])}] {s['text']}")
        print(f"  · 转录 {len(sub)} 条")

    out = out_dir / f"{re.sub(r'[\\/:*?"<>|#]', '', title)[:50]}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ 笔记已生成：{out}")


def srt_ts(ms):
    ms = max(0, int(ms))
    h, rem = divmod(ms // 1000, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms % 1000:03d}"


def fmt(ms):
    ms = max(0, int(ms))
    return f"{ms // 60000:02d}:{ms % 60000 // 1000:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="YouTube 链接（youtube.com/watch 或 youtu.be）")
    ap.add_argument("--out-dir", help="笔记输出目录（默认 Link to Notes/笔记）")
    ap.add_argument("--proxy", default=PROXY, help="代理地址（默认 127.0.0.1:7897）")
    ap.add_argument("--no-translate", action="store_true",
                    help="长视频英文不翻译，仅剪藏英文字幕（省时，零云）")
    args = ap.parse_args()
    try:
        clip(args.url, args.out_dir, args.proxy, args.no_translate)
    except RuntimeError as e:
        print(f"✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
