#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  抖音剪藏：本地下载 + 口播字幕（BGM 人声分离）
#
#  零云原则：全本地处理，不调用任何云 API
#    · 下载：yt-dlp Douyin extractor + 浏览器登录态（--cookies-from-browser chrome）
#    · 口播提取：silero VAD 检测语音占比
#        - 纯 BGM → 跳过转录，笔记只带视频
#        - 有口播 → demucs 人声分离 → whisper 转录纯人声轨 → natural 断句
#
#  用法：
#    python3 抖音剪藏.py "https://v.douyin.com/xxxx" [--cookies-from-browser chrome] [--min-speech 0.15]
# ============================================================
import argparse, json, os, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_ROOT") or HERE.parent.parent.parent)
os.environ.setdefault("OBSIDIAN_VAULT_ROOT", str(VAULT_ROOT))

DL_DIR = VAULT_ROOT / "Link to Notes" / "下载"    # 视频/分离音频
NOTE_DIR = VAULT_ROOT / "Link to Notes" / "笔记"    # 笔记
SPEECH_RATIO_MIN = 0.15


def load(name, file):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------- 1. 下载 ----------

COOKIE_MAX_AGE = 12 * 3600   # cookie 缓存有效期（12 小时）


def ensure_cookies(browser, force=False):
    """cookie 缓存复用：12 小时内直接用缓存文件，不触发钥匙串弹窗；
    过期/失效时才重新提取（钥匙串弹窗仅此场景出现）"""
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "zerocloud"
    cache.mkdir(parents=True, exist_ok=True)
    ck = cache / f"{browser}_cookies.txt"          # 原始提取文件（完整，含风控 cookie）
    fresh = ck.is_file() and (time.time() - ck.stat().st_mtime) < COOKIE_MAX_AGE
    if fresh:
        # 关键 cookie 校验：缓存缺风控/登录 cookie 视为失效，强制重新提取
        try:
            txt = ck.read_text(encoding="utf-8")
            need = ("sid_tt" in txt and "passport_auth_mix_state" in txt and "sessionid" in txt)
            fresh = need
        except Exception:
            fresh = False
    if not (fresh and not force):
        try:
            ce = load("cookie_extract", "cookie_extract.py")
            ce.extract_cookies(["douyin"], browser=browser, out=str(ck))
        except Exception as e:
            print(f"  ⚠ cookie 提取失败（{e}），可能钥匙串未授权或未登录抖音")
            if not ck.is_file():
                return None
    # 供 yt-dlp 使用的副本（yt-dlp 会重写该文件并丢弃部分 cookie，副本隔离污染）
    yt_ck = cache / f"{browser}_ytdlp.txt"
    try:
        shutil.copy2(ck, yt_ck)
    except Exception:
        pass
    return str(ck) if ck.is_file() else None


def download_video(url, title, cookies_browser):
    """yt-dlp 下载（自动提取浏览器登录态 cookie），返回视频路径"""
    DL_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|#]', "", title)[:40] or "抖音视频"
    tmpl = str(DL_DIR / f"{safe}.%(ext)s")
    cmd = ["yt-dlp", "--no-warnings", "-f", "b", "-o", tmpl]
    cookies_file = ensure_cookies(cookies_browser)
    if cookies_file:
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "zerocloud"
        yt_ck = cache / f"{cookies_browser}_ytdlp.txt"
        cmd += ["--cookies", str(yt_ck) if yt_ck.is_file() else cookies_file]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"下载失败（{r.stderr.strip()[-200:]}）")
    for ext in (".mp4", ".mov", ".webm", ".mkv"):
        p = DL_DIR / f"{safe}{ext}"
        if p.is_file():
            return p
    raise RuntimeError("下载后未找到视频文件")


# ---------- 2. 语音检测 + 人声分离 ----------

def speech_ratio(wav_path):
    """silero VAD：语音时长占比（复用小红书剪藏.py 的实现）"""
    xhs = load("小红书剪藏", "小红书剪藏.py")
    return xhs.speech_ratio(wav_path)


def to_wav(media, wav):
    subprocess.run(["ffmpeg", "-y", "-i", str(media), "-ac", "1", "-ar", "16000",
                    str(wav)], capture_output=True, check=True)


def separate_vocals(media):
    """demucs 人声分离 → vocals.wav 路径；失败返回 None（降级混音直转）"""
    try:
        out_dir = DL_DIR / "separated"
        subprocess.run(["python3", "-m", "demucs", "--two-stems", "vocals",
                        "-o", str(out_dir), str(media)],
                       capture_output=True, timeout=1800, check=True)
        vocals = out_dir / "htdemucs" / media.stem / "vocals.wav"
        if vocals.is_file():
            return vocals
    except Exception as e:
        print(f"  ⚠ demucs 分离失败（{e}），降级为混音直转")
    return None


# ---------- 2.5 图文笔记（/note/ 类型） ----------

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def expand_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.geturl()


def fetch_with_cookies(url, cookies_file):
    cmd = ["curl", "-s", "-A", UA]
    if cookies_file:
        cmd += ["--cookie", cookies_file]
    cmd.append(url)
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def parse_pace_f(html):
    """解析 __pace_f → aweme.detail（desc/author/images）"""
    for m in re.finditer(r'__pace_f\.push\(\[(\d+),"((?:[^"\\]|\\.)*)"\]\)', html):
        try:
            unescaped = json.loads('"' + m.group(2) + '"')
        except Exception:
            continue
        m2 = re.match(r'^\d+:[A-Z]?(.*)$', unescaped, re.S)
        if not m2:
            continue
        try:
            data = json.loads(m2.group(1))
        except Exception:
            continue
        if not isinstance(data, list) or len(data) < 4:
            continue
        det = (data[3].get('aweme') or {}).get('detail') if isinstance(data[3], dict) else None
        if det and det.get('desc'):
            return det
    return None


def clip_note(url, cookies_browser):
    """抖音图文笔记：标题/正文/图片下载 → Markdown 笔记"""
    print("▶ 图文笔记…")
    final = expand_url(url)
    note_id = re.search(r"/note/(\d+)", final)
    if not note_id:
        raise RuntimeError(f"无法解析图文 note_id：{final}")
    cookies_file = ensure_cookies(cookies_browser)
    html = fetch_with_cookies(final, cookies_file)
    det = parse_pace_f(html)
    if not det:
        raise RuntimeError("图文页面解析失败：请在浏览器打开 douyin.com 刷新几次后重试（风控 cookie 需浏览器生成）")
    desc = re.sub(r"#\S+", "", det.get("desc") or "").strip()
    title = re.split(r"[。！？!?\n]", desc)[0][:60] or "抖音图文笔记"
    author = ((det.get("authorInfo") or {}).get("nickname")) or "未知作者"
    imgs = det.get("images") or []
    print(f"  标题：{title}（作者 {author}，图片 {len(imgs)} 张）")
    img_paths, vid_paths = [], []
    for i, img in enumerate(imgs):
        u = (img.get("urlList") or img.get("downloadUrlList") or [""])[0]
        if not u:
            continue
        safe = re.sub(r'[\/:*?"<>|#]', "", title)[:30] or "图文"
        ext = (".gif" if "gif" in u.lower() else
               ".webp" if "webp" in u.lower() else
               ".png" if "png" in u.lower() else ".jpg")
        dest = DL_DIR / f"{safe}-{i + 1}{ext}"
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": final})
            dest.write_bytes(urllib.request.urlopen(req, timeout=60).read())
            img_paths.append(dest)
        except Exception as e:
            print(f"  ⚠ 图片{i + 1}下载失败：{e}")
        # 实况图（Live Photo）：images[].video 带动效视频 → 一并下载嵌入
        lv = (img.get("video") or {})
        pa = lv.get("playAddr") or []
        if pa:
            src = pa[-1].get("src", "") or pa[0].get("src", "")   # 末位通常码率更高
            if src:
                vdest = DL_DIR / f"{safe}-{i + 1}.mp4"
                try:
                    req = urllib.request.Request(src, headers={"User-Agent": UA, "Referer": final})
                    vdest.write_bytes(urllib.request.urlopen(req, timeout=60).read())
                    vid_paths.append(vdest)
                    print(f"  📹 实况动效已下载：{vdest.name}")
                except Exception as e:
                    print(f"  ⚠ 实况动效{i + 1}下载失败：{e}")
    NOTE_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", "", f"> 抖音图文笔记 · {author}", ""]
    if desc:
        lines += [desc, ""]
    for pth in img_paths:
        lines.append(f"![[{pth.relative_to(VAULT_ROOT).as_posix()}]]")
        lines.append("")
        for vp in vid_paths:
            if vp.stem == pth.stem:          # 图片配对应动效 → 图下方嵌视频
                lines.append(f"![[{vp.relative_to(VAULT_ROOT).as_posix()}]]")
                lines.append("")
    lines.append(f"原文：[{final}]({final})")
    out = NOTE_DIR / f"{re.sub(r'[\/:*?"<>|#]', '', title)[:50]}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ 笔记已生成：{out}（图片 {len(img_paths)} 张，实况动效 {len(vid_paths)} 条）")

# ---------- 3. 剪藏 ----------

def clip(url, cookies_browser, min_speech):
    print("▶ 解析链接…")
    # 短链展开 + 拿标题（先 yt-dlp 探测，同样用提取的 cookies.txt）
    cookies_file = ensure_cookies(cookies_browser)
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "zerocloud"
    yt_ck = (cache / f"{cookies_browser}_ytdlp.txt") if cookies_file else None
    probe = subprocess.run(
        ["yt-dlp", "--no-warnings", "--print", "%(title)s\t%(duration)s",
         *(["--cookies", str(yt_ck)] if yt_ck and yt_ck.is_file() else []), url],
        capture_output=True, text=True)
    if probe.returncode != 0:
        raise RuntimeError(f"链接解析失败（{probe.stderr.strip()[-200:]}）")
    title, dur = probe.stdout.strip().split("\t")
    title = re.sub(r"#\S+", "", title).strip() or "抖音视频"   # 去话题标签
    print(f"  标题：{title}（{dur}s）")

    video = download_video(url, title, cookies_browser)
    print(f"▶ 视频已下载：{video.name}")

    # VAD 检测
    tmp_wav = DL_DIR / f"{video.stem}-vad.wav"
    to_wav(video, tmp_wav)
    ratio = speech_ratio(tmp_wav)
    tmp_wav.unlink(missing_ok=True)
    print(f"  · 语音占比：{ratio:.0%}" if ratio is not None else "  · VAD 不可用")

    if ratio is not None and ratio < min_speech:
        out = NOTE_DIR / f"{video.stem}.md"
        NOTE_DIR.mkdir(parents=True, exist_ok=True)
        out.write_text(
            f"# {title}\n\n> 抖音视频笔记 · 纯背景音乐（无人声），未转录\n\n"
            f"![[{video.relative_to(VAULT_ROOT).as_posix()}]]\n\n原文：[{url}]({url})\n",
            encoding="utf-8")
        print(f"✅ 笔记已生成：{out}（纯BGM跳过转录）")
        return

    # 有口播：demucs 分离 → 转录人声轨
    vocals = separate_vocals(video)
    transcribe_src = vocals if vocals else video
    vt = load("视频转录", "视频转录.py")
    jp = transcribe_src.with_suffix(".json")
    if not jp.is_file():
        print("  · whisper 转录人声轨中…")
        vt.transcribe(transcribe_src, lang="zh")
    cc = load("标准字幕剪藏", "标准字幕剪藏.py")
    segs = json.load(open(jp, encoding="utf-8"))["transcription"]
    sub = cc.resegment_natural(segs, transcribe_src, min_w=15.0, max_w=50.0, pause_s=0.6)
    widths = [cc.width(s["text"]) for s in sub]
    total_ms = max(s["to"] for s in sub) if sub else 0
    NOTE_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {title}",
        "",
        f"![[{video.name}]]",
        "",
        f"> 视频时长 {cc.fmt(total_ms)} · 标准字幕 {len(sub)} 条"
        f"（最短 {min(widths):.0f} / 平均 {sum(widths)/len(widths):.1f} / 最长 {max(widths):.0f} 字）"
        f"· whisper 转写{'（demucs 人声分离）' if vocals else ''} + 自然断句（停顿 ≥0.6s）",
        "",
        "## 标准字幕",
        "",
    ]
    for s in sub:
        lines.append(f"[{cc.fmt(s['from'])}] {s['text']}")
    out = NOTE_DIR / f"{video.stem}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ 笔记已生成：{out}（字幕 {len(sub)} 条）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="抖音链接（v.douyin.com 短链 / douyin.com/video/ID）")
    ap.add_argument("--cookies-from-browser", default="chrome",
                    help="浏览器登录态（chrome/edge/arc/firefox，默认 chrome）")
    ap.add_argument("--min-speech", type=float, default=SPEECH_RATIO_MIN,
                    help=f"语音占比阈值（默认 {SPEECH_RATIO_MIN}）")
    args = ap.parse_args()
    try:
        final = expand_url(args.url)
        if "/note/" in final:
            clip_note(final, args.cookies_from_browser)
        else:
            clip(final, args.cookies_from_browser, args.min_speech)
    except RuntimeError as e:
        print(f"✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

