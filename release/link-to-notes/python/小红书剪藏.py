#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  小红书剪藏：图文笔记 → 图文 Markdown；视频笔记 → 本地下载 + 口播字幕
#
#  零云原则：全本地处理，不调用任何云 API
#    · 图文笔记：展开短链 → 解析页面 __INITIAL_STATE__ → 标题/正文/标签/图片下载
#    · 视频笔记：yt-dlp 本地下载 → silero VAD 检测语音占比
#        - 纯 BGM（语音占比 < 阈值）→ 跳过转录，笔记只带视频+简介
#        - 有口播 → whisper 转录 → natural 断句（停顿≥0.6s，单点时间戳）
#
#  用法：
#    python3 小红书剪藏.py "https://xhslink.cn/o/xxxxx"
#    python3 小红书剪藏.py "https://www.xiaohongshu.com/explore/xxxx"
#    python3 小红书剪藏.py 链接 --min-speech 0.1   # 语音占比阈值（默认0.15）
# ============================================================
import argparse, json, os, re, subprocess, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_ROOT") or HERE.parent.parent.parent)
os.environ.setdefault("OBSIDIAN_VAULT_ROOT", str(VAULT_ROOT))

DL_DIR = VAULT_ROOT / "Link to Notes" / "下载"    # 视频/图片
NOTE_DIR = VAULT_ROOT / "Link to Notes" / "笔记"    # 笔记
SPEECH_RATIO_MIN = 0.15                          # 语音占比低于此 → 纯BGM，跳过转录

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


def load(name, file):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


# ---------- 1. 短链展开 + 笔记解析 ----------

def note_id_from(url):
    """返回 (note_id, 完整分享URL)。完整 URL 带 xsec_token，抓取页面必需"""
    m = re.search(r"/explore/([0-9a-f]+)", url) or re.search(r"/discovery/item/([0-9a-f]+)", url)
    if m:
        return m.group(1), url
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        final = r.geturl()               # urllib 已跟随重定向，geturl 即最终页
    m = re.search(r"/explore/([0-9a-f]+)", final) or re.search(r"/discovery/item/([0-9a-f]+)", final)
    return (m.group(1), final) if m else (None, None)


def fetch_note(note_url):
    """抓取笔记页面（带 xsec_token 的完整分享 URL）→ note dict"""
    html = fetch(note_url)
    idx = html.find("window.__INITIAL_STATE__")
    if idx < 0:
        raise RuntimeError("页面无 __INITIAL_STATE__（可能被反爬拦截）")
    start = html.find("{", idx)
    depth, i, in_str, esc = 0, start, False, False
    while i < len(html):
        c = html[i]
        if in_str:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': in_str = False
        else:
            if c == '"': in_str = True
            elif c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0: break
        i += 1
    js = re.sub(r",\s*}", "}", re.sub(r"undefined", "null", html[start:i + 1]))
    js = re.sub(r",\s*]", "]", js)
    state = json.loads(js)
    return state["noteData"]["data"]["noteData"]


def note_title(note, fallback="小红书笔记"):
    """标题：优先 title 字段；为空时从 desc 提取第一句（去掉话题标记）"""
    t = (note.get("title") or "").strip()
    if t:
        return t[:60]
    desc = re.sub(r"#[^#\s]+\[话题\]#", "", note.get("desc") or "").strip()
    desc = re.sub(r"@[^#\s]+", "", desc).strip()   # 去掉 @作者
    m = re.split(r"[。！？!?\n]", desc)
    t = m[0].strip() if m and m[0].strip() else desc[:40]
    return t[:60] or fallback


# ---------- 2. 语音检测 ----------

def speech_ratio(wav_path):
    """silero VAD：语音时长占比（0~1）；失败返回 None（降级为直接转录）"""
    try:
        import wave
        import numpy as np
        import torch
        from silero_vad import load_silero_vad, get_speech_timestamps
        with wave.open(str(wav_path), "rb") as w:
            data = w.readframes(w.getnframes())
            audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        model = load_silero_vad()
        ts = get_speech_timestamps(torch.from_numpy(audio), model, threshold=0.5)
        total = len(audio) / 16000.0
        # ts 的 start/end 单位为毫秒（silero-vad 默认）
        voice = sum(float(t["end"] - t["start"]) for t in ts) / 1000.0
        return min(1.0, voice / max(total, 1e-6))
    except Exception as e:
        print(f"  ⚠ VAD 检测失败（{e}），降级为直接转录")
        return None


def to_wav(media, wav):
    subprocess.run(["ffmpeg", "-y", "-i", str(media), "-ac", "1", "-ar", "16000",
                    str(wav)], capture_output=True, check=True)


# ---------- 3. 图文笔记 ----------

def download_image(url, dest, referer):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    dest.write_bytes(data)
    return dest


def clip_image(note, note_url, out_dir):
    title = note_title(note, "无标题小红书笔记")
    desc = re.sub(r"#[^#\s]+\[话题\]#", "", note.get("desc") or "").strip()
    tags = [t.get("name") for t in (note.get("tagList") or []) if t.get("name")]
    user = (note.get("user") or {})
    nickname = user.get("nickName") or user.get("nickname") or "未知作者"
    interact = note.get("interactInfo") or {}
    liked = interact.get("likedCount") or "0"
    collected = interact.get("collectedCount") or "0"
    imgs = note.get("imageList") or []
    # 下载图片
    img_paths, vid_paths = [], []
    for i, img in enumerate(imgs):
        u = img.get("urlDefault") or img.get("url") or ""
        if not u:
            continue
        # urlDefault 可能是 webp 缩略，试转原图：常见字段 infoList[0].url
        if img.get("infoList"):
            u = img["infoList"][0].get("url") or u
        ext = (".gif" if "gif" in u.lower() else
               ".webp" if "webp" in u.lower() else
               ".png" if "png" in u.lower() else
               ".jpg")   # 动图（gif/webp）按真实格式保存，Obsidian 嵌入可播放
        dest = DL_DIR / f"{title[:30]}-{i + 1}{ext}"
        try:
            download_image(u, dest, note_url)
            img_paths.append(dest)
        except Exception as e:
            print(f"  ⚠ 图片{i + 1}下载失败：{e}")
        # 实况图（Live Photo）：stream.h264 带动效视频 → 一并下载嵌入
        if img.get("livePhoto"):
            vsrc = ""
            for b in ((img.get("stream") or {}).get("h264") or []):
                vsrc = b.get("url") or b.get("urlApi") or ""
                if not vsrc:
                    vsrc = (b.get("backupUrls") or [""])[0]
                if vsrc:
                    break
            if vsrc:
                vdest = DL_DIR / f"{title[:30]}-{i + 1}.mp4"
                try:
                    download_image(vsrc, vdest, note_url)
                    vid_paths.append(vdest)
                    print(f"  📹 实况动效已下载：{vdest.name}")
                except Exception as e:
                    print(f"  ⚠ 实况动效{i + 1}下载失败：{e}")
    # 生成笔记
    safe = re.sub(r'[\\/:*?"<>|#]', "", title)[:50] or "小红书笔记"
    out = out_dir / f"{safe}.md"
    lines = [
        f"# {title}",
        "",
        f"> 小红书图文笔记 · {nickname} · ❤️{liked} ⭐{collected}",
        "",
    ]
    if desc:
        lines += [desc, ""]
    for p in img_paths:
        rel = p.relative_to(VAULT_ROOT).as_posix()
        lines.append(f"![[{rel}]]")
        lines.append("")
        for vp in vid_paths:
            if vp.stem == p.stem:          # 图片配对应动效 → 图下方嵌视频
                lines.append(f"![[{vp.relative_to(VAULT_ROOT).as_posix()}]]")
                lines.append("")
    if tags:
        lines.append("标签：" + " ".join(f"#{t}" for t in tags))
        lines.append("")
    lines.append(f"原文：[{note_url}]({note_url})")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out, len(img_paths), len(vid_paths)


# ---------- 4. 视频笔记 ----------

def download_video(note_url, title):
    """yt-dlp 下载（无 cookie，无水印优先），返回视频路径"""
    DL_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|#]', "", title)[:40] or "小红书视频"
    tmpl = str(DL_DIR / f"{safe}.%(ext)s")
    subprocess.run(["yt-dlp", "--no-warnings", "-f", "b", "-o", tmpl, note_url],
                   capture_output=True, check=True)
    for ext in (".mp4", ".mov", ".webm", ".mkv"):
        p = DL_DIR / f"{safe}{ext}"
        if p.is_file():
            return p
    raise RuntimeError("视频下载后未找到文件")


def clip_video(note, note_url, out_dir, min_speech):
    title = note_title(note, "无标题小红书视频")
    desc = re.sub(r"#[^#\s]+\[话题\]#", "", note.get("desc") or "").strip()
    user = (note.get("user") or {})
    nickname = user.get("nickName") or user.get("nickname") or "未知作者"
    video_path = download_video(note_url, title)
    # VAD 检测
    tmp_wav = DL_DIR / f"{video_path.stem}-vad.wav"
    to_wav(video_path, tmp_wav)
    ratio = speech_ratio(tmp_wav)
    tmp_wav.unlink(missing_ok=True)
    if ratio is not None and ratio < min_speech:
        out = out_dir / f"{video_path.stem}.md"
        out.write_text(
            f"# {title}\n\n> 小红书视频笔记 · {nickname} · 纯背景音乐（无人声），未转录\n\n"
            f"![[{video_path.relative_to(VAULT_ROOT).as_posix()}]]\n\n"
            + (f"{desc}\n\n" if desc else "")
            + f"原文：[{note_url}]({note_url})\n", encoding="utf-8")
        print(f"  · 语音占比 {ratio:.0%} < {min_speech:.0%} → 纯BGM，跳过转录")
        return out, None, ratio
    # 转录 + natural 断句
    vt = load("视频转录", "视频转录.py")
    jp = video_path.with_suffix(".json")
    if not jp.is_file():
        print("  · whisper 转写中…")
        vt.transcribe(video_path, lang="zh")
    cc = load("标准字幕剪藏", "标准字幕剪藏.py")
    segs = json.load(open(jp, encoding="utf-8"))["transcription"]
    sub = cc.resegment_natural(segs, video_path, min_w=15.0, max_w=50.0, pause_s=0.6)
    widths = [cc.width(s["text"]) for s in sub]
    total_ms = max(s["to"] for s in sub) if sub else 0
    media_name = video_path.name
    lines = [
        f"# {title}",
        "",
        f"![[{media_name}]]",
        "",
        f"> 视频时长 {cc.fmt(total_ms)} · 标准字幕 {len(sub)} 条"
        f"（最短 {min(widths):.0f} / 平均 {sum(widths)/len(widths):.1f} / 最长 {max(widths):.0f} 字）"
        f"· whisper 转写 + 自然断句（停顿 ≥0.6s）",
        "",
        "## 标准字幕",
        "",
    ]
    for s in sub:
        lines.append(f"[{cc.fmt(s['from'])}] {s['text']}")
    out = out_dir / f"{video_path.stem}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out, len(sub), ratio


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="小红书链接（xhslink 短链 / explore 链接）")
    ap.add_argument("--min-speech", type=float, default=SPEECH_RATIO_MIN,
                    help=f"语音占比阈值（默认 {SPEECH_RATIO_MIN}，低于则判纯BGM跳过转录）")
    ap.add_argument("--out-dir", help="笔记输出目录（默认 小红书剪藏/笔记）")
    args = ap.parse_args()

    print(f"▶ 解析链接…")
    nid, note_url = note_id_from(args.url)
    if not nid:
        print("✗ 无法解析 note_id"); sys.exit(1)
    print(f"  note_id: {nid}")
    note = fetch_note(note_url)
    ntype = note.get("type", "normal")
    out_dir = Path(args.out_dir) if args.out_dir else NOTE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    DL_DIR.mkdir(parents=True, exist_ok=True)

    if ntype == "video":
        print(f"▶ 视频笔记：{note.get('title')}")
        out, n_sub, ratio = clip_video(note, note_url, out_dir, args.min_speech)
        tag = f"字幕 {n_sub} 条" if n_sub else "纯BGM跳过转录"
        print(f"✅ 笔记已生成：{out}（{tag}，语音占比 {ratio:.0%}）" if ratio is not None
              else f"✅ 笔记已生成：{out}（{tag}）")
    else:
        print(f"▶ 图文笔记：{note.get('title')}")
        out, n_img, n_vid = clip_image(note, note_url, out_dir)
        print(f"✅ 笔记已生成：{out}（图片 {n_img} 张，实况动效 {n_vid} 条）")


if __name__ == "__main__":
    main()
