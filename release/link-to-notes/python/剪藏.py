#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  剪藏：Link to Notes 统一编排入口
#
#  粘贴任意平台链接 → 自动识别平台 → 分派对应剪藏链路
#    · xhslink.cn / xiaohongshu.com  → 小红书（图文+视频）
#    · v.douyin.com / douyin.com     → 抖音（视频+图文）
#    · bilibili.com / b23.tv / BV号  → B站（视频）
#    · 其他 http(s)                  → 网页剪藏（v2.1，暂提示）
#
#  零云原则：全本地处理，不调用任何云 API
#
#  用法：
#    python3 剪藏.py "https://xhslink.cn/o/xxxx"
#    python3 剪藏.py "https://v.douyin.com/xxxx"
#    python3 剪藏.py "BV1xxxx"
# ============================================================
import re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name, file):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def detect_platform(url):
    """URL → 平台标识"""
    if re.search(r"xhslink\.cn|xiaohongshu\.com", url):
        return "xiaohongshu"
    if re.search(r"douyin\.com", url):
        return "douyin"
    if re.search(r"bilibili\.com|b23\.tv|BV[0-9A-Za-z]{10}", url):
        return "bilibili"
    if re.search(r"youtube\.com|youtu\.be", url):
        return "youtube"
    return "web"


def clip(url, out_dir=None, min_speech=0.15):
    """统一剪藏：按平台分派"""
    plat = detect_platform(url)
    print(f"▶ 识别平台：{plat}")

    if plat == "xiaohongshu":
        xhs = load("小红书剪藏", "小红书剪藏.py")
        nid, note_url = xhs.note_id_from(url)
        if not nid:
            raise RuntimeError("小红书链接解析失败")
        note = xhs.fetch_note(note_url)
        if note.get("type") == "video":
            xhs.clip_video(note, note_url, Path(out_dir) if out_dir else xhs.NOTE_DIR,
                           min_speech)
        else:
            xhs.clip_image(note, note_url, Path(out_dir) if out_dir else xhs.NOTE_DIR)
        return

    if plat == "douyin":
        # 社区发布版不含抖音（cookie 钥匙串弹窗体验问题）；个人版含完整模块
        if not (HERE / "抖音剪藏.py").is_file():
            raise RuntimeError("本版本（社区版）不含抖音剪藏：抖音剪藏需浏览器 cookie，会弹系统密码窗，"
                               "个人版请从 GitHub 源码构建。支持：小红书 / B站 / YouTube / 网页文章")
        dy = load("抖音剪藏", "抖音剪藏.py")
        final = dy.expand_url(url)
        if "/note/" in final:
            dy.clip_note(final, "chrome")
        else:
            dy.clip(final, "chrome", min_speech)
        return

    if plat == "bilibili":
        # b23.tv 短链先展开
        if "b23.tv" in url:
            import subprocess as _sp
            r = _sp.run(["curl", "-s", "-o", "/dev/null", "-w", "%{url_effective}", "-L", url],
                        capture_output=True, text=True, timeout=30)
            final = r.stdout or ""
            if "/opus/" in final:
                bili_img = load("b站图文", "b站图文.py")
                bili_img.clip(final, out_dir)
                return
            m = re.search(r"BV[0-9A-Za-z]{10}", final)
            if m:
                url = m.group(0)
                print(f"  · 短链展开 → {url}")
            else:
                raise RuntimeError("b23.tv 短链展开失败")
        elif "/opus/" in url:
            bili_img = load("b站图文", "b站图文.py")
            bili_img.clip(url, out_dir)
            return
        import os as _os
        vroot = _os.environ.get("OBSIDIAN_VAULT_ROOT", str(HERE.parent.parent.parent))
        dl = str(Path(vroot) / "Link to Notes" / "下载")
        sys.argv = ["b站全流程.py", url, "--mode", "standard", "--dir", dl]
        if out_dir:
            sys.argv += ["--out-dir", out_dir]
        try:
            bili = load("b站全流程", "b站全流程.py")
            bili.main()
        except SystemExit:
            pass
        return

    if plat == "youtube":
        yt = load("youtube剪藏", "youtube剪藏.py")
        yt.clip(url, out_dir)
        return

    if plat == "web":
        web = load("网页剪藏", "网页剪藏.py")
        web.clip(url, out_dir)
        return

    raise RuntimeError(f"未知平台：{plat}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="任意平台链接（B站/抖音/小红书）")
    ap.add_argument("--out-dir", help="笔记输出目录")
    ap.add_argument("--min-speech", type=float, default=0.15, help="语音占比阈值（默认 0.15）")
    args = ap.parse_args()
    try:
        clip(args.url, args.out_dir, args.min_speech)
    except RuntimeError as e:
        print(f"✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
