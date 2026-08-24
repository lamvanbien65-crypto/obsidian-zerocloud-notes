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
import argparse, json, os, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_ROOT") or HERE.parent.parent.parent)
os.environ.setdefault("OBSIDIAN_VAULT_ROOT", str(VAULT_ROOT))

DL_DIR = VAULT_ROOT / "抖音剪藏" / "下载"      # 视频/分离音频
NOTE_DIR = VAULT_ROOT / "抖音剪藏" / "笔记"    # 笔记
SPEECH_RATIO_MIN = 0.15


def load(name, file):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------- 1. 下载 ----------

def ensure_cookies(browser):
    """自动提取浏览器 cookie → cookies.txt（本地解密，钥匙串授权一次后免交互）"""
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "zerocloud"
    cache.mkdir(parents=True, exist_ok=True)
    ck = cache / f"{browser}_cookies.txt"
    try:
        ce = load("cookie_extract", "cookie_extract.py")
        ce.extract_cookies(["douyin"], browser=browser, out=str(ck))
    except Exception as e:
        print(f"  ⚠ cookie 提取失败（{e}），尝试直接浏览器 cookie")
        return None
    return str(ck) if ck.is_file() else None


def download_video(url, title, cookies_browser):
    """yt-dlp 下载（自动提取浏览器登录态 cookie），返回视频路径"""
    DL_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|#]', "", title)[:40] or "抖音视频"
    tmpl = str(DL_DIR / f"{safe}.%(ext)s")
    cmd = ["yt-dlp", "--no-warnings", "-f", "b", "-o", tmpl]
    cookies_file = ensure_cookies(cookies_browser)
    if cookies_file:
        cmd += ["--cookies", cookies_file]
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


# ---------- 3. 剪藏 ----------

def clip(url, cookies_browser, min_speech):
    print("▶ 解析链接…")
    # 短链展开 + 拿标题（先 yt-dlp 探测，同样用提取的 cookies.txt）
    cookies_file = ensure_cookies(cookies_browser)
    probe = subprocess.run(
        ["yt-dlp", "--no-warnings", "--print", "%(title)s\t%(duration)s",
         *(["--cookies", cookies_file] if cookies_file else []), url],
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
        clip(args.url, args.cookies_from_browser, args.min_speech)
    except RuntimeError as e:
        print(f"✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
