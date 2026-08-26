#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  网页剪藏：普通网页文章 → Markdown 笔记（trafilatura 本地提取）
#
#  零云原则：全本地处理，不调用任何云 API
#    · 正文提取：trafilatura（广告/导航自动剔除）
#    · 支持：普通网页文章 / 微信公众号（mp.weixin.qq.com）/ 知乎 / CSDN / 博客
#    · 图片：正文图片下载到本地（防盗链失败则保留原链接）
#
#  用法：
#    python3 网页剪藏.py "https://mp.weixin.qq.com/s/xxxx"
#    python3 网页剪藏.py "https://zhuanlan.zhihu.com/p/xxxx"
# ============================================================
import argparse, json, os, re, subprocess, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_ROOT") or HERE.parent.parent.parent)
os.environ.setdefault("OBSIDIAN_VAULT_ROOT", str(VAULT_ROOT))

DL_DIR = VAULT_ROOT / "Link to Notes" / "下载"      # 图片
NOTE_DIR = VAULT_ROOT / "Link to Notes" / "笔记"    # 笔记

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


HDRS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}


def fetch_html(url, cookies_file=None):
    """抓取网页；cookies_file 存在时用 curl（带登录态）"""
    if cookies_file:
        cmd = ["curl", "-s", "-L", "-A", UA, "--cookie", cookies_file, url]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and r.stdout:
            return r.stdout
    req = urllib.request.Request(url, headers=HDRS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"网页访问失败（HTTP {e.code}）：该站点可能反爬或需登录。"
            "如浏览器可正常打开，可先在浏览器登录该站点后重试，"
            "或复制正文内容手动保存。") from e


def try_with_cookies(url):
    """403/反爬时：尝试提取浏览器 cookie 后重抓（知乎/CSDN 等登录态站点）"""
    import urllib.error
    try:
        import cookie_extract as ce
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.split(":")[0]
        key = domain.replace("www.", "").split(".")[0]
        ck = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "zerocloud"
        ck.mkdir(parents=True, exist_ok=True)
        cf = ck / f"{key}_cookies.txt"
        ce.extract_cookies([domain], browser="chrome", out=str(cf))
        html = fetch_html(url, cookies_file=str(cf))
        print(f"  · 已使用浏览器登录态抓取（{domain}）")
        return html
    except Exception as e:
        raise RuntimeError(f"网页访问失败：{e}") from e


def download_img(src, title, referer, idx):
    """下载正文图片（防盗链失败返回 None）"""
    if not src.startswith("http"):
        return None
    try:
        req = urllib.request.Request(src, headers={"User-Agent": UA, "Referer": referer})
        data = urllib.request.urlopen(req, timeout=30).read()
        ext = ".png" if src.lower().endswith(".png") else ".jpg"
        safe = re.sub(r'[\\/:*?"<>|#]', "", title)[:30] or "网页"
        dest = DL_DIR / f"{safe}-{idx}{ext}"
        dest.write_bytes(data)
        return dest
    except Exception:
        return None


def clip(url, out_dir=None):
    """网页剪藏：抓取 → trafilatura 提取 → Markdown"""
    print(f"▶ 网页剪藏：{url}")
    import trafilatura
    try:
        html = fetch_html(url)
    except RuntimeError:
        html = try_with_cookies(url)
    # 提取元数据
    meta = trafilatura.extract_metadata(html, default_url=url)
    title = (getattr(meta, "title", None) or "网页笔记").strip()
    author = getattr(meta, "author", None) or ""
    date = getattr(meta, "date", None) or ""
    # 正文
    text = trafilatura.extract(html, include_comments=False,
                               include_tables=True, favor_precision=True)
    if not text or len(text) < 20:
        raise RuntimeError(f"正文提取失败（{url}）：页面可能是 JS 渲染或需登录，v1 仅支持静态网页")
    print(f"  标题：{title}（{len(text)} 字）")
    pairs = translate_article(text) if not is_chinese(text) else None

    # 正文图片（提取 <img> 列表）
    img_paths = []
    imgs = re.findall(r'<img[^>]+src="(https?://[^"]+)"', html)
    seen = set()
    for i, src in enumerate(imgs[:20]):
        if src in seen:
            continue
        seen.add(src)
        p = download_img(src, title, url, i + 1)
        if p:
            img_paths.append(p)

    out_dir = Path(out_dir) if out_dir else NOTE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|#]', "", title)[:50] or "网页笔记"
    out = out_dir / f"{safe}.md"
    lines = [f"# {title}", ""]
    meta_line = "> 网页剪藏 · " + " · ".join(x for x in [author, date] if x)
    if meta_line != "> 网页剪藏 · ":
        lines.append(meta_line)
        lines.append("")
    # 图片放在正文前（正文纯文本，图注位置无法精确对齐）
    for p in img_paths:
        lines.append(f"![[{p.relative_to(VAULT_ROOT).as_posix()}]]")
        lines.append("")
    if pairs:
        for orig, trans in pairs:
            lines.append(orig.strip())
            lines.append("")
            if trans:
                lines.append(f"> {trans}")
                lines.append("")
    else:
        lines.append(text)
        lines.append("")
    lines.append(f"原文：[{url}]({url})")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ 笔记已生成：{out}（图片 {len(img_paths)} 张）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="网页链接（普通文章 / 公众号 / 知乎 / CSDN 等）")
    ap.add_argument("--out-dir", help="笔记输出目录（默认 Link to Notes/笔记）")
    args = ap.parse_args()
    try:
        clip(args.url, args.out_dir)
    except RuntimeError as e:
        print(f"✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()


# ---------- 本地翻译（Ollama，零 API） ----------

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3:8b"      # 本地模型（也可用 gemma4）


def is_chinese(text):
    """CJK 字符占比 >10% 判中文"""
    cjk = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    return cjk / max(len(text), 1) > 0.1


def translate_block(text, model=OLLAMA_MODEL):
    """调本地 Ollama 翻译一段英文 → 中文"""
    import urllib.request
    prompt = ("You are a professional translator. Translate the following English text "
              "into Simplified Chinese. Keep technical terms accurate and tone natural. "
              "Output ONLY the Chinese translation, no explanation.\n\n" + text)
    body = json.dumps({"model": model, "prompt": prompt,
                       "stream": False, "temperature": 0.3}).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read().decode())
    return (resp.get("response") or "").strip()


def translate_article(text, model=OLLAMA_MODEL):
    """整篇分块翻译，返回 [(原文段, 译文段), ...]"""
    if is_chinese(text):
        return None
    print(f"  · 检测为英文，本地 Ollama（{model}）翻译中…")
    paras = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) > 1800 and cur:
            chunks.append(cur)
            cur = ""
        cur += "\n\n" + p if cur else p
    if cur:
        chunks.append(cur)
    pairs = []
    for i, c in enumerate(chunks):
        try:
            t = translate_block(c, model)
            pairs.append((c, t))
            print(f"  · 块 {i + 1}/{len(chunks)} 翻译完成（{len(c)}字）")
        except Exception as e:
            print(f"  ⚠ 块 {i + 1} 翻译失败（{e}），保留原文")
            pairs.append((c, None))
    return pairs
