#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  轮播生成：扫描剪藏视频 → 自动抽封面 → 生成卡片轮播 HTML
#
#  用法：
#    python3 轮播生成.py                      # 扫描 Link to Notes/下载 全部视频
#    python3 轮播生成.py --dir 目录            # 指定视频目录
#    python3 轮播生成.py --out 轮播墙.md       # 输出到指定笔记（默认覆盖 轮播墙.md）
#    python3 轮播生成.py --dry-run             # 只打印计划不生成
#    python3 轮播生成.py --images "图片目录"   # 图片轮播（目录内图片 → 轮播 HTML）
#    python3 轮播生成.py --sections "文档.md" [--single]  # 图文笔记轮播（推荐）
# ============================================================
import argparse, os, re, subprocess, sys, time
from pathlib import Path

VAULT_ROOT = Path(os.environ.get("OBSIDIAN_VAULT_ROOT") or Path(__file__).resolve().parent.parent.parent)
DL_DIR = VAULT_ROOT / "Link to Notes" / "下载"
COVER_DIR = DL_DIR / "covers"
FFMPEG = "/opt/homebrew/Cellar/ffmpeg-full/8.1.2_2/bin/ffmpeg"

PLATFORMS = [
    ("youtu", "YouTube"), ("douyin", "抖音"), ("xhslink", "小红书"),
    ("xiaohongshu", "小红书"), ("Kimi", "B站"), ("访谈", "B站"), ("B站", "B站"),
    ("NVIDIA", "YouTube"), ("LLM", "YouTube"),
]


def guess_platform(title):
    for kw, name in PLATFORMS:
        if kw in title:
            return name
    return "剪藏"


def make_cover(video, force=False):
    """ffmpeg 抽视频中段一帧做封面 → covers/{stem}.jpg"""
    cover = COVER_DIR / f"{video.stem}.jpg"
    if cover.is_file() and not force:
        return cover
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    # 抽中段帧
    r = subprocess.run(
        [FFMPEG, "-y", "-i", str(video), "-ss", "2", "-frames:v", "1",
         "-vf", "scale=440:-2", str(cover)],
        capture_output=True)
    return cover if cover.is_file() else None


def generate(video_dir, out_path, dry_run=False):
    videos = sorted([p for p in Path(video_dir).glob("*.mp4")
                     if "字幕" not in p.name and p.stem != "vocals"])
    # 去重（标题前 40 字符相同视为同一视频）
    seen = set()
    uniq = []
    for v in videos:
        key = v.stem[:35]
        if key not in seen:
            seen.add(key)
            uniq.append(v)
    print(f"· 发现 {len(videos)} 个视频（去重后 {len(uniq)} 个）")
    if dry_run:
        for v in uniq:
            print(f"  - {v.stem[:40]} [{guess_platform(v.name)}]")
        return

    cards = []
    ok = 0
    for v in uniq:
        cover = make_cover(v)
        title = v.stem[:38]
        plat = guess_platform(v.name)
        if cover:
            rel = cover.relative_to(VAULT_ROOT).as_posix()
            img = f'<img src="{rel}">'
        else:
            img = ""
        cards.append(
            f'  <div class="carousel-card"><a href="{v.name}">{img}'
            f'<div class="carousel-title">{title}</div>'
            f'<div class="carousel-meta">{plat} · {time.strftime("%m.%d", time.localtime(v.stat().st_mtime))}</div></a></div>')
        ok += 1

    content = [
        "# 剪藏轮播墙",
        "",
        f"> 自动生成 · {len(uniq)} 个视频 · Link to Notes",
        "",
        '<div class="carousel">',
        *cards,
        "</div>",
        "",
    ]
    out = Path(out_path)
    out.write_text("\n".join(content) + "\n", encoding="utf-8")
    print(f"✅ 轮播墙已生成：{out}（{ok} 张卡片）")


def generate_images(img_dir, out_path=None, dry_run=False):
    """图片轮播：扫描目录图片 → 生成轮播 HTML 块"""
    exts = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
    imgs = sorted([p for p in Path(img_dir).iterdir() if p.suffix.lower() in exts])
    if not imgs:
        print(f"· 目录无图片：{img_dir}")
        return
    print(f"· 发现 {len(imgs)} 张图片")
    cards = []
    for i, img in enumerate(imgs, 1):
        rel = img.relative_to(VAULT_ROOT).as_posix()
        label = img.stem[:38]
        cards.append(f'  <div class="carousel-card"><img src="{rel}"><div class="carousel-title">{label}</div></div>')
    block = '<div class="carousel">\n' + "\n".join(cards) + "\n</div>"
    if dry_run:
        print(block)
        return
    if out_path:
        Path(out_path).write_text(block + "\n", encoding="utf-8")
        print(f"✅ 轮播 HTML 已写入：{out_path}")
    else:
        print(block)


def generate_sections(md_path, dry_run=False, single=False):
    """图文笔记生成：按章节分组（<N> / ## / 一：），每章一个轮播（--single 则整篇一个轮播）
    轮播边界：<N> / ## 标题 / 一：标题；步骤行（1，/ 2.）是卡片配文
    卡片 = 媒体 + 最近文字配文（多图共享）；纯文字段 → 白底文字卡；前言 → 「前言」文字卡
    输出：{原文档名}图文笔记.md（文件名=页内标题）；多轮播标题 = ### （N）轮播名；底部原文存档"""
    md = Path(md_path)
    text = md.read_text(encoding="utf-8")
    import re as _re
    lines = text.split('\n')
    items = []              # ("sec", 轮播序号, 轮播名) / ("img", 附件名, 配文) / ("text", 步骤, [正文行])
    # 轮播边界：<N> / ## 标题 / 一：标题；步骤行（1，/ 2.）是卡片配文，不是边界
    sec_re = _re.compile(r'^\s*(?:#{1,4}\s+|<\s*\d+\s*>\s*|[一二三四五六七八九十]+[：:、])')
    step_re = _re.compile(r'^(?:\d{1,2})\s*[.、：:，,]\s*')
    media_re = _re.compile(r'!\[\[(.+?\.(?:png|jpe?g|webp|gif|mov|mp4|webm|m4v))\]\]')
    cur_caption, cur_step, cur_body = None, None, []

    def flush_text():
        """正文行 → 文字卡（步骤=cur_step）；无正文则丢弃（文字已被图片用作配文）"""
        nonlocal cur_body
        if cur_body:
            items.append(("text", cur_step or "", cur_body))
        cur_body = []

    for l in lines:
        t = l.strip()
        if not t or t.startswith(('📅', '---')):
            continue
        m = media_re.search(l)
        if sec_re.match(t):
            flush_text()
            cur_caption, cur_step = None, None
            num_m = _re.search(r'<\s*(\d+)\s*>', t)
            title = media_re.sub('', t).strip()
            title = _re.sub(r'^<\s*\d+\s*>\s*', '', title)     # <N> 前缀只做轮播序号，不进标题
            items.append(("sec", int(num_m.group(1)) if num_m else None, title))
            inner = media_re.sub('', t).strip()
            if step_re.match(inner):                            # "## 1. 下载与安装：" 兼作步骤
                cur_step = cur_caption = inner
                if m:                                           # 边界行内嵌媒体 → 立即出图文卡
                    items.append(("img", m.group(1), cur_caption))
            continue
        if step_re.match(t):                                    # 步骤行 → 配文（含序号，多图共享）
            flush_text()
            cur_step = cur_caption = media_re.sub('', t).strip()
            if m:                                               # 步骤行内嵌媒体（"3，xxx![[3-2.png]]"）
                items.append(("img", m.group(1), cur_caption))
            continue
        if m:                                                   # 图片行 → 图文卡（配文=最近文字/共享）
            if cur_body:
                tail = ' '.join(cur_body)
                cur_caption = (cur_caption + ' ' + tail).strip() if cur_caption else tail
            cur_body, cur_step = [], None
            items.append(("img", m.group(1), cur_caption or ""))
            continue
        if t.startswith('前言'):                                # 前言行 → 文字卡步骤「前言」
            flush_text()
            cur_step = '前言'
            body0 = _re.sub(r'^前言[：:;；、，,]?\s*', '', t)
            cur_caption = body0 or t
            cur_body = [body0] if body0 else []
            continue
        cur_body.append(t)                                      # 普通文字行 → 正文
    flush_text()
    # 按轮播边界分组
    groups = []                                                 # [(轮播序号, 轮播名, [卡片items])]
    cur_num, cur_title, cur_group = None, None, []
    for it in items:
        if it[0] == "sec":
            if cur_group:
                groups.append((cur_num, cur_title, cur_group))
            cur_num, cur_title, cur_group = it[1], it[2], []
        else:
            cur_group.append(it)
    if cur_group:
        groups.append((cur_num, cur_title, cur_group))
    groups = [g for g in groups if g[2]]
    print(f"· 解析出 {len(groups)} 个轮播（{sum(len(c) for _, _, c in groups)} 张卡）")
    doc_dir = md.parent
    blocks = []

    def media_card(name, cap):
        """图卡/视频卡（点击弹原图+触控板翻页：由 Link to Notes 插件 JS 灯箱实现，勿包 <a href="#..."> 锚点——
        Obsidian 会拦截 fragment 导致 HTML 渲染破损）"""
        img_path = doc_dir / name
        if not img_path.is_file():
            # 文档目录递归查找（附件/ 子目录），再全库按名查找（与 Obsidian wikilink 语义一致）
            for sub in doc_dir.rglob(name.split('/')[-1]):
                img_path = sub
                break
        if not img_path.is_file():
            for sub in VAULT_ROOT.rglob(name.split('/')[-1]):
                img_path = sub
                break
        if not img_path.is_file():
            return None
        rel = img_path.relative_to(VAULT_ROOT).as_posix()
        label = cap if cap else name[:30]
        if img_path.suffix.lower() in ('.mov', '.mp4', '.webm', '.m4v'):
            return f'  <div class="carousel-card"><video src="{rel}" muted playsinline preload="metadata"></video><div class="carousel-title">{label}</div></div>'
        return f'  <div class="carousel-card"><img src="{rel}"><div class="carousel-title">{label}</div></div>'

    def text_card(step, body):
        step = _re.sub(r'[#*`]', '', step or '').strip()
        if len(step) > 30:
            step = step[:30] + "…"
        # 正文逐行处理：``` 围栏 → <pre class="card-code"><code> 代码块（HTML 块内无法解析 markdown 围栏）
        parts, code_lines, in_code = [], [], False
        for l in body:
            if l.strip() == '```':
                if in_code:
                    parts.append('<pre class="card-code"><code>' + '\n'.join(code_lines) + '</code></pre>')
                    code_lines, in_code = [], False
                else:
                    in_code = True
            elif in_code:
                code_lines.append(l)
            elif l.strip():
                parts.append(l)
        if in_code and code_lines:
            parts.append('<pre class="card-code"><code>' + '\n'.join(code_lines) + '</code></pre>')
        body_text = ' '.join(parts).strip()
        inner = f'<span class="card-step">{step}</span>' if step else ''
        if body_text:
            inner += body_text
        return f'  <div class="carousel-card text-card"><div class="carousel-text">{inner}</div></div>'

    def group_html(cards_items):
        htmls = []
        for it in cards_items:
            if it[0] == "img":
                c = media_card(it[1], it[2])
                if c:
                    htmls.append(c)
            else:
                htmls.append(text_card(it[1], it[2]))
        return htmls

    if single:
        all_cards = []
        for _, _, g in groups:
            all_cards.extend(group_html(g))
        if all_cards:
            blocks.append('<div class="carousel">')
            blocks.extend(all_cards)
            blocks.append("</div>")
            blocks.append("")
    else:
        for num, title, g in groups:
            cards = group_html(g)
            if cards:
                if title:
                    head = f"### （{num}）{title}" if num else f"### {title}"
                    blocks.append(head)
                    blocks.append("")
                blocks.append('<div class="carousel">')
                blocks.extend(cards)
                blocks.append("</div>")
                blocks.append("")
    html = "\n".join(blocks)
    if dry_run:
        print(html[:1500])
        return
    # 文件名与页内标题统一：{文档名}图文笔记.md；无前言文字行/章节标题，直接放卡片
    out = md.with_name(md.stem + "图文笔记.md")
    archive = f"---\n\n📄 原文存档：[[{md.name}]]\n"
    out.write_text(f"# {md.stem}图文笔记\n\n" + html + archive, encoding="utf-8")
    print(f"✅ 图文笔记已生成：{out}（{'整篇单轮播' if single else str(len(groups)) + ' 个章节轮播'} + 原文存档）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DL_DIR), help="视频目录（默认 Link to Notes/下载）")
    ap.add_argument("--out", default=str(VAULT_ROOT / "轮播墙.md"), help="输出笔记路径")
    ap.add_argument("--dry-run", action="store_true", help="只列出视频不生成")
    ap.add_argument("--images", help="图片轮播模式：指定图片目录，生成轮播 HTML 块")
    ap.add_argument("--sections", help="多轮播模式：指定 md 文档，按章节生成多个轮播")
    ap.add_argument("--single", action="store_true", help="配合 --sections：整篇合并为一个轮播（--sections 文档.md --single）")
    args = ap.parse_args()
    try:
        if args.sections:
            generate_sections(args.sections, args.dry_run, args.single)
            return
        if args.images:
            generate_images(args.images, args.out if args.out and args.out != str(VAULT_ROOT / "轮播墙.md") else None,
                            args.dry_run)
        else:
            generate(args.dir, args.out, args.dry_run)
    except Exception as e:
        print(f"✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
