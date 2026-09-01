#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  b站图文：B站图文动态（/opus/）→ Markdown 笔记
#
#  零云原则：全本地处理
#    · 解析 __INITIAL_STATE__：标题/作者/图片
#    · 图片去 @ 缩略后缀下载原图
#
#  用法：
#    python3 b站图文.py "https://www.bilibili.com/opus/xxxx"
# ============================================================
import argparse, json, os, re, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_ROOT") or HERE.parent.parent.parent)
os.environ.setdefault("OBSIDIAN_VAULT_ROOT", str(VAULT_ROOT))

DL_DIR = VAULT_ROOT / "Link to Notes" / "下载"
NOTE_DIR = VAULT_ROOT / "Link to Notes" / "笔记"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def expand_short_url(url, timeout=20):
    """跟随重定向展开短链（b23.tv 等）→ 正式 bilibili.com 地址"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl()


def parse_opus(html):
    """解析 __INITIAL_STATE__ → (标题, 作者, 图片URL列表, 时间)"""
    m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?})\s*;', html, re.S)
    if not m:
        return None
    js = re.sub(r'undefined', 'null', m.group(1))
    js = re.sub(r',\s*}', '}', js)
    js = re.sub(r',\s*]', ']', js)
    data = json.loads(js)
    detail = data.get("detail") or {}
    mods = detail.get("modules") or []
    title = "B站图文动态"
    author = ""
    ts = ""
    for mod in mods:
        if not isinstance(mod, dict):
            continue
        mt = mod.get("module_title") or {}
        if mt.get("text"):
            title = mt["text"].strip()
        ma = mod.get("module_author") or {}
        if ma.get("name"):
            author = ma["name"]
        if ma.get("pub_time"):
            ts = ma["pub_time"]
    # 图片：hdslb 域名 + bfs/new_dyn
    imgs = []
    for u in re.findall(r'//i0?\.hdslb\.com/bfs/new_dyn/[^"\'\\\s@]+', html):
        full = "https:" + u
        if full not in imgs:
            imgs.append(full)
    # 时间兜底：页面可见文本
    if not ts:
        m2 = re.search(r'(\d{4}年\d{2}月\d{2}日 \d{2}:\d{2})', html)
        if m2:
            ts = m2.group(1)
    return {"title": title, "author": author, "images": imgs, "time": ts}


def clip(url, out_dir=None):
    # b23.tv 等短链 → 先展开（图片下载的 Referer 必须是 bilibili.com 域，否则图床 403）
    if "bilibili.com" not in url:
        try:
            final = expand_short_url(url)
            print(f"  · 短链展开：{url} → {final[:60]}…")
            url = final
        except Exception:
            pass
    print(f"▶ B站图文动态：{url}")
    html = fetch(url)
    info = parse_opus(html)
    if not info:
        raise RuntimeError("图文动态解析失败（页面无 __INITIAL_STATE__）")
    print(f"  标题：{info['title']}（作者 {info['author'] or '未知'}，图片 {len(info['images'])} 张）")
    img_paths = []
    for i, u in enumerate(info["images"]):
        safe = re.sub(r'[\\/:*?"<>|#]', "", info["title"])[:30] or "图文"
        dest = DL_DIR / f"{safe}-{i + 1}.png"
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": url})
            dest.write_bytes(urllib.request.urlopen(req, timeout=60).read())
            img_paths.append(dest)
        except Exception as e:
            print(f"  ⚠ 图片{i + 1}下载失败：{e}")
    out_dir = Path(out_dir) if out_dir else NOTE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|#]', "", info["title"])[:50] or "B站图文动态"
    out = out_dir / f"{safe}.md"
    lines = [f"# {info['title']}", ""]
    meta = "> B站图文笔记" + (f" · {info['author']}" if info["author"] else "") + \
           (f" · {info['time']}" if info["time"] else "")
    lines.append(meta)
    lines.append("")
    for p in img_paths:
        lines.append(f"![[{p.relative_to(VAULT_ROOT).as_posix()}]]")
        lines.append("")
    lines.append(f"原文：[{url}]({url})")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ 笔记已生成：{out}（图片 {len(img_paths)} 张）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="B站图文动态链接（bilibili.com/opus/xxx）")
    ap.add_argument("--out-dir", help="笔记输出目录（默认 Link to Notes/笔记）")
    args = ap.parse_args()
    try:
        clip(args.url, args.out_dir)
    except RuntimeError as e:
        print(f"✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
